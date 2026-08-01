"""Metric-correctness tests for the eval harness (spec Part H · step 10).

Pure unit tests over the four metric functions and the quote→relevant resolver — no
index, no model, no I/O. They pin the arithmetic to hand-computed values so a future
refactor can't silently drift the numbers the regression gate reports. (Retrieval
*quality* over the real index is exercised by running `rag_exp.eval`; retrieval
*safety* is `test_access_control.py`. This file is just the math.)
"""

from math import log2

import pytest

from rag_exp.eval import (
    QueryEval,
    _norm,
    aggregate,
    first_relevant_rank,
    hit_rate_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    resolve_relevant,
)

# ── The worked example from docs/explainers/evaluation.md ────────────────────────
# |R| = 1, k = 5, the single relevant chunk ("a") comes back at RANK 3.
# Two metrics say "perfect" (found it, found all of it), two say "mediocre" (buried it).
RANK3 = (["x", "y", "a", "z", "w"], {"a"}, 5)


def test_rank3_hit_and_recall_say_perfect():
    retrieved, relevant, k = RANK3
    assert hit_rate_at_k(retrieved, relevant, k) == 1.0
    assert recall_at_k(retrieved, relevant, k) == 1.0  # 1 of 1 found


def test_rank3_rank_aware_metrics_say_mediocre():
    retrieved, relevant, k = RANK3
    assert first_relevant_rank(retrieved, relevant, k) == 3
    assert reciprocal_rank(retrieved, relevant, k) == pytest.approx(1 / 3)
    # nDCG = DCG/IDCG = (1/log2(4)) / (1/log2(2)) = 0.5/1.0
    assert ndcg_at_k(retrieved, relevant, k) == pytest.approx(0.5)


# ── Rank 1 — everything is perfect ───────────────────────────────────────────────
def test_rank1_all_perfect():
    retrieved, relevant, k = ["a", "b", "c"], {"a"}, 3
    assert hit_rate_at_k(retrieved, relevant, k) == 1.0
    assert recall_at_k(retrieved, relevant, k) == 1.0
    assert first_relevant_rank(retrieved, relevant, k) == 1
    assert reciprocal_rank(retrieved, relevant, k) == 1.0
    assert ndcg_at_k(retrieved, relevant, k) == 1.0


# ── A complete miss — everything is zero, rank is None ───────────────────────────
def test_complete_miss_is_all_zero():
    retrieved, relevant, k = ["x", "y", "z"], {"a"}, 3
    assert hit_rate_at_k(retrieved, relevant, k) == 0.0
    assert recall_at_k(retrieved, relevant, k) == 0.0
    assert reciprocal_rank(retrieved, relevant, k) == 0.0
    assert ndcg_at_k(retrieved, relevant, k) == 0.0
    assert first_relevant_rank(retrieved, relevant, k) is None


# ── |R| > 1 — recall becomes a real fraction; nDCG penalizes the gap ─────────────
def test_multi_relevant_partial_recall_and_ndcg():
    # relevant {a, b, c}; retrieved a (r1), x, b (r3). Found 2 of 3.
    retrieved, relevant, k = ["a", "x", "b"], {"a", "b", "c"}, 3
    assert hit_rate_at_k(retrieved, relevant, k) == 1.0
    assert recall_at_k(retrieved, relevant, k) == pytest.approx(2 / 3)
    assert first_relevant_rank(retrieved, relevant, k) == 1
    assert reciprocal_rank(retrieved, relevant, k) == 1.0
    # DCG = 1/log2(2) + 0 + 1/log2(4) = 1.0 + 0.5 = 1.5
    # IDCG = ideal [1,1,1] = 1/log2(2)+1/log2(3)+1/log2(4) = 1 + 0.6309 + 0.5
    dcg = 1 / log2(2) + 1 / log2(4)
    idcg = 1 / log2(2) + 1 / log2(3) + 1 / log2(4)
    assert ndcg_at_k(retrieved, relevant, k) == pytest.approx(dcg / idcg)


# ── top-k truncation — a hit beyond position k does not count ────────────────────
def test_hit_beyond_k_is_truncated_out():
    # "a" sits at rank 6; k = 5 must not see it.
    retrieved, relevant, k = ["x", "x", "x", "x", "x", "a"], {"a"}, 5
    assert hit_rate_at_k(retrieved, relevant, k) == 0.0
    assert recall_at_k(retrieved, relevant, k) == 0.0
    assert first_relevant_rank(retrieved, relevant, k) is None


# ── recall is capped by k, but a perfectly-ranked top-k still scores nDCG 1.0 ─────
def test_recall_capped_by_k_but_ranking_ideal():
    # 8 relevant, k = 5, top-5 are all relevant → recall 5/8, but ranking is ideal.
    retrieved = ["a", "b", "c", "d", "e"]
    relevant = {"a", "b", "c", "d", "e", "f", "g", "h"}
    k = 5
    assert recall_at_k(retrieved, relevant, k) == pytest.approx(5 / 8)
    assert hit_rate_at_k(retrieved, relevant, k) == 1.0
    # IDCG uses min(|R|, k) = 5 ideal slots, which the top-5 fill → nDCG 1.0.
    assert ndcg_at_k(retrieved, relevant, k) == pytest.approx(1.0)


# ── The resolver: whitespace-normalized containment, hard error on zero ──────────
def test_norm_collapses_whitespace():
    assert _norm("a  b\n c\t d") == "a b c d"


def test_resolve_matches_across_a_line_wrap():
    # The quote is stored split across a newline (Gutenberg hard-wrap); it must still match.
    normed = [
        ("detective:doc:0", _norm("... eclipses and\npredominates the whole of her sex ...")),
        ("science:doc:9", _norm("something entirely unrelated")),
    ]
    got = resolve_relevant("eclipses and predominates the whole", normed)
    assert got == {"detective:doc:0"}


def test_resolve_zero_match_is_hard_error():
    normed = [("detective:doc:0", _norm("nothing to see here"))]
    with pytest.raises(ValueError, match="0 chunks"):
        resolve_relevant("this quote is not present", normed)


# ── Per-tier aggregation (step 11 exact-vs-paraphrase split) ──────────────────────
def _qe(tier: str, hit: float, recall: float, mrr: float, ndcg: float) -> QueryEval:
    """A minimal already-scored QueryEval — only the fields aggregate() averages matter."""
    return QueryEval(
        q="q",
        product_id="p",
        tier=tier,
        num_relevant=1,
        first_rank=None,
        hit_rate=hit,
        recall=recall,
        mrr=mrr,
        ndcg=ndcg,
    )


def test_aggregate_means_and_count():
    rows = [_qe("exact", 1, 1, 1, 1), _qe("exact", 0, 0, 0, 0)]
    m = aggregate("exact", rows)
    assert m.label == "exact"
    assert m.count == 2
    assert (m.hit_rate, m.recall, m.mrr, m.ndcg) == (0.5, 0.5, 0.5, 0.5)


def test_aggregate_empty_slice_is_zero_not_crash():
    # A tier absent from the golden set must read as zero, never divide-by-zero.
    m = aggregate("paraphrase", [])
    assert m.count == 0
    assert (m.hit_rate, m.recall, m.mrr, m.ndcg) == (0.0, 0.0, 0.0, 0.0)
