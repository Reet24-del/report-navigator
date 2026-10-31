# V2 implementation and critical review

## Status

Approved offline V2 implemented. No V3 local Gemma work was added. The supplied
participant guide's scoring constraints take precedence over the early hosted
prototype: the scoring entry point is offline, CPU-only and builds its own index
from the input report. The Streamlit frontend is a separate teammate deliverable.

## Implementation record

| Change | What was implemented and why |
|---|---|
| Package layout | Moved code into src/report_navigator; kept the backend public import compatible with the frontend contract. |
| Contracts | Added table cells/rows, exact numerical results and strict submission records; existing UI result fields remain available. |
| Native tables | Regular line detection preserves coloured grid rows. Merged headings accompany each extracted row and source cell coordinates. |
| Borderless/OCR tables | Positional row recovery groups words, carries parent headers and maps year tokens to individual columns. It is heuristic. |
| OCR | Local Tesseract with declared model and checksum. Recognition runs in a timed child process with one OpenMP thread, bounded raster size and temporary grid-line preprocessing. |
| Retrieval | BM25Plus plus explicit entity constraints ranks table-row candidates. Runtime uses only the run PDF and question text. |
| Question parsing | Generic year, measure, entity, category and scope constraints. No fixed cities, report pages, report year or question IDs determine answers. |
| Offline solver | Matches the requested cell; rejects ranks, rates, wrong years and narrower road-class/category counts. Similarly supported conflicting values abstain. |
| UI service | Existing ask/render/load calls remain. A predict method exposes exact counts, source records and heuristic confidence. |
| Submission CLI | predict.py accepts the required arguments, bypasses persistent report caches and writes exactly one validated JSONL record per input ID. |
| Reproduction | train.py exports generic configuration and OCR asset hash. There is no statistical training or saved report-derived model in V2. |
| Evaluation | Separate module implements EM, citation accuracy, composite score, hallucination rate and confidence ranking diagnostics. Gold fields are discarded by the prediction reader. |
| Packaging | Pinned requirements, Sloths manifest, required README headings, smoke test, decisions/error documents and original OCR license. Challenge datasets and extracted caches are excluded. |

## Verification completed

- 83 automated checks passed on Python 3.11.15, including actual OCR, synthetic
  multi-level scanned headers, year changes, wrong entities, conflicting cells,
  subtotal/measure confusion, exact JSONL schema and a socket-denied CLI smoke.
- Ruff formatting and basic error/import/unused-symbol checks passed.
- The reproduction command completed and produced only generic settings/hash.
- On all 50 provided development questions: EM 1.00, citation accuracy 1.00,
  composite score 1.00, and hallucination rate 0/5. These are in-sample results
  after inspecting public failures, not held-out or hidden-report accuracy.
- V2's expanded table-row candidate search covered all 45 answerable questions'
  listed gold pages. V1's 9/45 result used only six plain chunks, so the two
  retrieval rates are not a controlled same-budget comparison.
- Two complete scoring runs produced byte-identical output. The repeat run took
  65.0 seconds on the macOS development laptop. Peak child-process RSS was
  511,164,416 bytes (about 487.5 MiB); this is not aggregate process-tree memory
  and not a measurement inside the organizer's Linux resource sandbox.
- The scorer indexed 260 of 272 public-report pages. Twelve sparse/unusable pages
  remained unindexed. This is processing coverage, not proof of answer coverage.
- Import inspection confirmed predict.py does not import google.genai.
- A rasterized copy of the public city table recovered the sampled requested
  count. A denser rasterized vehicle table still abstained because OCR merged
  numbers and corrupted labels. Synthetic OCR success does not establish dense
  scan robustness.
- Required files and README heading word counts were checked; direct application
  dependencies are pinned. No official evaluator schema/validation run was made.

## Critical findings still open

1. **High: hidden-report generalization remains unmeasured.** All public labels
   were used for error diagnosis. The strong public result is not an unbiased
   validation estimate. New paraphrases, labels and layouts can fail.
2. **High: dense, low-resolution scanned tables remain weak.** Header recovery
   cannot repair digits or names that OCR did not read. The system should abstain
   rather than fabricate repairs from known public answers.
3. **Medium: confidence is not calibrated.** Values are heuristic evidence levels.
   No confidence bonus is claimed, and BM25 scores are not treated as probabilities.
4. **Medium: native table finding has no per-call hard subprocess timeout.** OCR
   does, and ingestion checks its total budget between pages, but a pathological
   native page could exceed the intended deadline. Exact Linux sandbox behavior
   has not been tested.
5. **Medium: local Gemma is absent.** V2 does not establish Gemma prize eligibility.
   The retained hosted adapter is isolated and prohibited in the scoring path.
6. **Medium: questions outside exact-count table logic may abstain.** Arbitrary
   prose answers, arithmetic, percentages and multiple-year questions are not
   handled by this version.
7. **Low: documentation names are incomplete.** Sloths is recorded; the two
   teammates' names still need to be supplied for the README. Dependencies are
   directly pinned, but transitive resolutions are not fully locked.

## Integrity review

The project contains no challenge PDF, JSONL dataset, extracted report cache or
entity-to-answer lookup. All row values and physical page citations are computed
from the scoring PDF at runtime. Pretrained OCR weights are public, declared and
small enough for the model-file limit. Test tables use invented values/entities.
Data-derived verification artifacts are kept outside the submission tree.

## Next approval boundary

V2 ends here. Improving dense scans or adding a small local Gemma backend requires
a concrete V3 proposal, memory/runtime checks and the user's approval before
implementation. The actual evaluator schema check should be run by the team
before spending any of its limited validation runs.
