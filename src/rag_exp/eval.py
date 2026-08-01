"""Stage 9 — eval: the golden-query retrieval harness (spec Part H · ADR-004).

Answers ONE question — *did we fetch the right chunks?* — and turns it into four
numbers so every chunk/embed/retrieval change becomes measurable (walkthrough:
docs/explainers/evaluation.md). This is retrieval **quality**; retrieval **safety**
is the separate, mandatory cross-tenant leak test in tests/ (never mix the two).

How it runs (ADR-004):

  1. Re-chunk the corpus from source in-process, at the SAME config the index was
     built at (default 512/0). Chunking is deterministic, so this reproduces exactly
     the chunk ids that are in ./.chroma — which is what lets us resolve a golden
     quote to the live chunk ids without a "get all rows" call on the store.
  2. For each golden row, resolve its verbatim `relevant_quote` to the set of live
     chunks that CONTAIN it (whitespace-normalized) — the relevant set R. A quote
     that matches zero chunks is a HARD ERROR (a typo'd answer key, not a 0 score).
  3. Fire the query through the real guarded `Retriever.retrieve` as `root` (full
     corpus, so entitlements don't confound quality) and score the ranked hits:
     hit-rate@k · recall@k · MRR · nDCG@k. Report the mean over the golden set.

The golden set anchors relevance to SOURCE TEXT, never chunk ids: ids are an artifact
of the chunk size we sweep, so an id-keyed set silently rots on a re-chunk. A quote is
a property of the book — author once, valid across every sweep (ADR-004 §1).

Run it:  uv run python -m rag_exp.eval
Requires a built index first:  uv run python -m rag_exp.index
"""

import json
import logging
from dataclasses import dataclass
from math import log2
from pathlib import Path

from rag_exp.chunk import Chunk, chunk_documents
from rag_exp.config import CHUNK_OVERLAP, CHUNK_SIZE, PROJECT_ROOT, K
from rag_exp.ingest import load_products
from rag_exp.retrieve import Retriever

logger = logging.getLogger(__name__)

GOLDEN_PATH: Path = PROJECT_ROOT / "eval" / "golden.json"


# ── Relevance resolution (quote → live chunk ids) ────────────────────────────────


def _norm(text: str) -> str:
    """Collapse every run of whitespace to a single space.

    Absorbs Gutenberg's hard line-wraps (a quote is stored split across lines) so a
    one-line quote still matches. Deliberately does NOT touch case, punctuation, or
    `_italic_` markup — so quotes must be lifted verbatim from the source, never typed
    from memory (docs/explainers/evaluation.md).
    """
    return " ".join(text.split())


def resolve_relevant(quote: str, normed_chunks: list[tuple[str, str]]) -> set[str]:
    """Return the ids of chunks whose (normalized) text contains `quote`.

    `normed_chunks` is `[(chunk_id, normalized_text), ...]` for the whole live corpus.
    Raises `ValueError` if the quote matches nothing: an unresolvable quote is a broken
    golden row (bad answer key), and a silent 0 would masquerade as a retrieval failure.
    """
    needle = _norm(quote)
    relevant = {cid for cid, text in normed_chunks if needle in text}
    if not relevant:
        raise ValueError(
            f"golden quote resolved to 0 chunks (typo'd / not verbatim / straddles a "
            f"chunk boundary?): {quote!r}"
        )
    return relevant


# ── The four metrics — pure functions over (retrieved ids, relevant set, k) ───────
#
# `retrieved` is the ranked list of chunk ids, best first (the store returns distinct
# ids). Each function truncates to the top-k itself, so they are self-contained and
# unit-testable. `relevant` (R) is non-empty by construction (resolve_relevant raises).


def hit_rate_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """1.0 if ANY relevant chunk is in the top-k, else 0.0 — 'did retrieval work at all?'"""
    return 1.0 if any(cid in relevant for cid in retrieved[:k]) else 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the relevant set found in the top-k — coverage, rank-blind.

    Capped by k when |R| > k (perfect retrieval of 8 relevant chunks at k=5 is 5/8),
    so only compare recall across runs at the same k.
    """
    found = len(set(retrieved[:k]) & relevant)
    return found / len(relevant)


def first_relevant_rank(retrieved: list[str], relevant: set[str], k: int) -> int | None:
    """1-indexed rank of the first relevant hit in the top-k, or None if none landed.

    The primitive behind MRR and the report's rank column — computed directly so we never
    reverse a reciprocal back into a rank through floating point.
    """
    for rank, cid in enumerate(retrieved[:k], start=1):
        if cid in relevant:
            return rank
    return None


def reciprocal_rank(retrieved: list[str], relevant: set[str], k: int) -> float:
    """1 / rank of the FIRST relevant hit in the top-k, else 0.0 (the per-query MRR term).

    Rank-aware and top-weighted: rank 1 → 1.0, rank 2 → 0.5, rank 5 → 0.2. The mean over
    the golden set is MRR — 'is the best answer near the top?' (≥ 0.6 feels snappy).
    """
    rank = first_relevant_rank(retrieved, relevant, k)
    return 1.0 / rank if rank is not None else 0.0


def _dcg(rels: list[int]) -> float:
    """Discounted cumulative gain: Σ rel_i / log2(i+1), i 1-indexed → position 1 pays 1.0."""
    return sum(rel / log2(i + 1) for i, rel in enumerate(rels, start=1))


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Position-weighted ranking quality in [0, 1], normalized against the ideal ranking.

    DCG rewards relevant hits more the higher they rank (log discount); dividing by the
    IDCG (all relevant chunks packed into the top slots) makes queries with different |R|
    comparable, so the mean is meaningful. Binary relevance here (quote in chunk = yes/no),
    so with |R|=1 it reduces to 1/log2(rank+1) — a gentler MRR. IDCG > 0 since |R| ≥ 1.
    """
    gains = [1 if cid in relevant else 0 for cid in retrieved[:k]]
    ideal = [1] * min(len(relevant), k)  # best case: every relevant chunk at the top
    return _dcg(gains) / _dcg(ideal)


# ── Records ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class QueryEval:
    """One golden query's outcome: its metrics plus enough context to read a failure."""

    q: str
    product_id: str
    tier: (
        str  # "exact" | "paraphrase" — the query style, for the per-tier split (ADR-004 / step 11)
    )
    num_relevant: int  # |R| — how many live chunks contained the quote
    first_rank: int | None  # rank of the first relevant hit (None = missed within top-k)
    hit_rate: float
    recall: float
    mrr: float  # the reciprocal-rank term for this query (mean of these = MRR)
    ndcg: float


@dataclass(frozen=True, slots=True)
class TierMeans:
    """The four means over one slice of the golden set (all of it, or one tier)."""

    label: str  # "all", "exact", "paraphrase", …
    count: int  # how many queries this slice covers
    hit_rate: float
    recall: float
    mrr: float
    ndcg: float


def aggregate(label: str, rows: list[QueryEval]) -> TierMeans:
    """Mean the four metrics over `rows` (a whole run or one tier's slice).

    Pure over already-scored `QueryEval`s so it is unit-testable without an index. An
    empty slice yields 0.0 means (via `_mean`) — a tier absent from the golden set reads
    as zero, not a crash.
    """
    return TierMeans(
        label=label,
        count=len(rows),
        hit_rate=_mean([r.hit_rate for r in rows]),
        recall=_mean([r.recall for r in rows]),
        mrr=_mean([r.mrr for r in rows]),
        ndcg=_mean([r.ndcg for r in rows]),
    )


@dataclass(frozen=True, slots=True)
class EvalReport:
    """The whole run: per-query rows + the overall means (the regression gate) + per-tier.

    `overall` is the headline number to track across sweeps; `by_tier` splits it by query
    style (exact vs paraphrase) — the step-11 experiment showing where dense retrieval
    handles paraphrase and where exact-term queries would motivate hybrid/BM25 (ADR-004).
    """

    k: int
    chunk_size: int
    per_query: list[QueryEval]
    overall: TierMeans
    by_tier: dict[str, TierMeans]


# ── The harness ──────────────────────────────────────────────────────────────────


def _load_golden(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        raise ValueError(f"golden set is empty: {path}")
    return rows


def _live_chunks(chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Re-chunk the corpus from source, deterministically reproducing the indexed ids."""
    return chunk_documents(load_products(), chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_eval(
    golden_path: Path = GOLDEN_PATH,
    k: int = K,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    retriever: Retriever | None = None,
) -> EvalReport:
    """Score every golden query and return the per-query + mean metrics.

    `chunk_size`/`chunk_overlap` MUST match the config the live index was built at, or
    the re-chunked ids won't line up with the store's and every query scores ~0. They
    are parameters (not hardcoded) so the ADR-004 sweeps can re-embed + re-eval at a new
    size in lockstep. `retriever` is injectable so tests/sweeps can pass a fake or an
    alternate store; the default wires the real bge-small + persisted ./.chroma.
    """
    golden = _load_golden(golden_path)
    chunks = _live_chunks(chunk_size, chunk_overlap)
    normed = [(c.id, _norm(c.text)) for c in chunks]
    logger.info("eval: %d golden rows over %d live chunks (k=%d)", len(golden), len(chunks), k)

    retriever = retriever if retriever is not None else Retriever()

    per_query: list[QueryEval] = []
    for row in golden:
        relevant = resolve_relevant(row["relevant_quote"], normed)
        hits = retriever.retrieve(row["user"], row["q"], k=k)
        retrieved = [h.id for h in hits]

        per_query.append(
            QueryEval(
                q=row["q"],
                product_id=row["product_id"],
                tier=row.get("tier", "untagged"),
                num_relevant=len(relevant),
                first_rank=first_relevant_rank(retrieved, relevant, k),
                hit_rate=hit_rate_at_k(retrieved, relevant, k),
                recall=recall_at_k(retrieved, relevant, k),
                mrr=reciprocal_rank(retrieved, relevant, k),
                ndcg=ndcg_at_k(retrieved, relevant, k),
            )
        )

    tiers = sorted({r.tier for r in per_query})
    return EvalReport(
        k=k,
        chunk_size=chunk_size,
        per_query=per_query,
        overall=aggregate("all", per_query),
        by_tier={t: aggregate(t, [r for r in per_query if r.tier == t]) for t in tiers},
    )


# ── Reporting ────────────────────────────────────────────────────────────────────

WIDTH = 96


def _fmt_means(m: TierMeans, k: int) -> str:
    """One aligned means line — reused for the overall row and each per-tier row."""
    return (
        f"hit-rate@{k}={m.hit_rate:.3f}   recall@{k}={m.recall:.3f}   "
        f"MRR={m.mrr:.3f}   nDCG@{k}={m.ndcg:.3f}"
    )


def _format_report(report: EvalReport) -> str:
    """Render a per-query table + the overall means + the exact/paraphrase split."""
    lines = [
        "=" * WIDTH,
        f"  RETRIEVAL EVAL   k={report.k}   chunk_size={report.chunk_size}   "
        f"golden queries={len(report.per_query)}",
        "  quality only (user=root, full corpus) — safety is the separate cross-tenant test",
        "=" * WIDTH,
        "  rank   hit  recall    mrr   ndcg  tier        product      query",
        "  " + "-" * (WIDTH - 4),
    ]
    for r in report.per_query:
        rank = str(r.first_rank) if r.first_rank is not None else "—"
        miss = "" if r.first_rank is not None else "  ← MISS"
        q = r.q if len(r.q) <= 34 else r.q[:33] + "…"
        lines.append(
            f"  {rank:>4}  {r.hit_rate:>4.0f}  {r.recall:>6.2f}  {r.mrr:>5.2f}  "
            f"{r.ndcg:>5.2f}  {r.tier:<10}  {r.product_id:<11}  {q}{miss}"
        )
    lines += [
        "  " + "-" * (WIDTH - 4),
        f"  MEAN over all {report.overall.count} queries:   {_fmt_means(report.overall, report.k)}",
        "  by query tier (exact = lexical overlap w/ the quote · paraphrase = NL question):",
    ]
    for tier in sorted(report.by_tier):
        m = report.by_tier[tier]
        lines.append(f"    {m.label:<11} (n={m.count:>2}):   {_fmt_means(m, report.k)}")
    lines += [
        "=" * WIDTH,
        "  These numbers mean little in absolute terms — compare the DELTA across runs.",
        "  Re-run after any chunk/embed/retrieval change; a drop = investigate before commit.",
    ]
    return "\n".join(lines)


def main() -> None:
    """CLI entry — `uv run python -m rag_exp.eval`."""
    logging.basicConfig(level=logging.WARNING)  # keep pipeline INFO chatter out of the report
    report = run_eval()
    print(_format_report(report))


if __name__ == "__main__":
    main()
