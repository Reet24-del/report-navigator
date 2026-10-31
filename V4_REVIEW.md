# V4 implementation and critical review

Approved V4 scope implemented on 31 October 2026. Publication is authorized
separately by the user; GitHub commit history records the published snapshot.
No Streamlit files, public answer schemas, provider settings or scoring entry
points were changed. No new dependency, model or network call was introduced.

## Exact implementation

1. scripts/benchmark_scans.py generates invented native/scanned table PDFs at
   runtime, runs the real backend with report cache disabled, and writes explicit
   answer/citation checks, abstentions, wrong answers and timing to a chosen output
   path. Generated data and results belong outside the repository. Example:
   `python scripts/benchmark_scans.py --seed 0 --output /tmp/v4-benchmark.json`.
2. src/report_navigator/table_quality.py collapses line-pixel runs, checks token
   containment and numeric-column completeness, rejects conflicts/changed labels,
   and maps crop OCR coordinates back to the source page. It never repairs digits
   from expected answers or splits an ambiguous numeric token.
3. ocr.py captures grid geometry before existing line removal. Only incomplete
   numeric body rows get optional full-width crop OCR. The crop preserves column
   positions. Accepted recovery must be complete and agree with stable original
   cells and entity tokens. Prose blocks are rebuilt from accepted words too.
   Region failures retain the full pass; its atomic checkpoint can survive an
   optional recovery timeout. The parent subprocess timeout remains the hard cap.
4. tables.py uses detected physical row bands to retain wrapped labels, keeps the
   page title outside column headers, and rejects tokens spanning columns or
   incomplete grid rows. Existing native line-table extraction is unchanged.
5. ingest.py reports recovery attempts and timeout fallback through existing
   ReportInfo warnings. Physical page numbering and AnswerResult stay unchanged.
6. config.py adds validated ocr_recovery_enabled=True and ocr_max_regions=6
   (0..12). These are Settings constructor options, not additional .env variables.
   Setting regions to zero disables crop retries; physical-grid grouping remains.
7. storage.py fingerprints both new settings and V4 table/OCR revisions so old
   caches cannot hide extraction changes. Runtime scoring still disables caches.
8. tests/test_table_quality.py, tests/test_ocr.py and tests/test_tables.py cover
   wrapped rows, column-spanning tokens, duplicate/missing cells, coordinate maps,
   conflicts, entity changes, real crop OCR with a simulated merged first-pass
   token, timeout checkpoints, prose consistency and cache invalidation.
9. docs/decisions.md and docs/error_analysis.md record evidence and limitations.

## Validation

- Python 3.11: 112 tests passed in 4.29 seconds. Five existing PyMuPDF/SWIG
  deprecation warnings remain. Ruff E4/E7/E9/F/I and formatting checks passed
  for all ten changed Python files.
- Four synthetic layouts, seed 0: V3 8/12 -> V4 12/12. Seed 19 (same layouts,
  different values/year, evaluated after implementation): 8/12 -> 12/12.
  Each seed has eight answerable and four absent-entity questions; correct
  answerable results improved from four to eight. No incorrect non-abstaining
  answers were added. Benchmark totals include correct physical-page checks.
- Local synthetic runtime totals were approximately 1.6 seconds per seed in both
  versions. The difference is too small and noisy to claim a speed improvement.
- Actual crop recognition passes the fault-injected merged-token test. Ordinary
  generated benchmark gains came from geometry grouping, not observed crop retry
  gains. This distinction matters when describing the implementation to judges.
- The full public report produced 50 byte-identical predictions versus V3,
  SHA256 2cbededae25551654e337b4770383a6de6f62d5da0a47518527a2373b283ddeb,
  in 64.16 seconds locally, indexing 260/272 pages. Importing predict.py does not
  load google.genai, and the socket-denied offline smoke test still passes.
- Rasterized real pages 101/241 were compared using an isolated V3 source copy.
  Counts were unchanged: page 101 has 13 correct, three wrong, one abstention
  across 17 public questions; page 241 abstains on all twelve. These one-page
  diagnostics omit alternative gold source pages and are not official evaluation.

## Critical review

**High — complete OCR rows can still contain wrong digits.** Layout validity is
not truth verification. V4 cannot identify a well-formed but misread single-cell
number, and the page-101 diagnostic demonstrates this risk. Confidence remains
heuristic. Never claim all scanned answers are reliable or that 12/12 synthetic
performance estimates hidden-report accuracy.

**High — dense real tables remain unresolved.** The new path assumes a clear
rectangular grid, a label column followed by numeric columns and enough complete
rows for the existing aligned-table parser. Multiple separate grids, serial
number columns, blank cells, skew, faint lines and category-heavy headers can
cause abstention or bypass the new path. The page-241 diagnostic did not improve.

**Medium — conservative recovery may reject valid corrections.** Original
single-cell digits and label tokens must agree. If the first pass recognized a
wrong but apparently stable token, a correct second pass is rejected. This is an
intentional tradeoff to avoid silently overwriting conflicting evidence. No
character-confidence estimator or second OCR engine was added.

**Medium — timeout bounds are not throughput guarantees.** A slow page can use
its entire OCR allowance. Optional crop attempts share that same cap; timed-out
recovery retains the atomic full-pass result when available. Native table-finder
calls still lack individual process-level timeouts. The exact organizer Linux
2-core/6-GB environment has not been verified.

**Medium — synthetic scope is narrow.** The second seed changes values in the
same templates; it is not an independent unseen-layout test. The crop test injects
a first-pass failure, rather than proving that naturally corrupted scans improve.
No supervised fitting, public-answer lookup or report-specific rule was added.

**Low — frontend verification remains with the teammate.** Existing methods and
schemas are preserved and backend tests pass. Their Streamlit app was not run in
this workspace. New warnings use the existing warnings field and need no contract
change. Cache revision changes can cause one legitimate rebuild after updating.

Review fixes before completion: exclude outside-grid captions from headers;
preserve full-pass checkpoints during recovery timeouts; reject changed entity
labels; rebuild prose blocks after accepting recovered table words. No Gemma
model, local inference or prize-eligibility claim was added in V4.
