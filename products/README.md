# Corpus — three mock licensed "products"

Three folders, three products. Each holds public-domain Project Gutenberg `.txt` files and stands in for a separately *licensed* body of content:

| Folder | `product_id` | Distinct vocabulary |
|---|---|---|
| `detective/` | `detective` | Sherlock Holmes — "deduction", "Baker Street" |
| `shakespeare/` | `shakespeare` | Shakespeare — "thou art", the sonnets |
| `science/` | `science` | Darwin et al. — "natural selection" |

The vocabularies are deliberately distinct so a cross-product leak is **eyeball-obvious** in retrieval output.

**At ingest (Phase 1):**
- `product_id` is derived from the **folder name** — drop a file in `science/` and every chunk from it is stamped `science`.
- Gutenberg license headers/footers (the `*** START/END OF THE PROJECT GUTENBERG EBOOK ***` boilerplate) are trimmed.
- That `product_id` metadata is what the entitlement filter matches on — it *is* the security boundary. See `docs/SECURITY.md`.

The `.txt` files are added during Phase 1 corpus prep (not committed yet). Each folder's `README.md` says what to drop there.
