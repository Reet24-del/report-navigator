# Decisions

1. **Offline scoring first.** The participant guide prohibits network/GPU use and
   allows 2 CPU cores, 6 GB RAM and 20 minutes including ingestion. The scoring
   entry point uses table logic and local OCR, not the retained cloud adapter.
2. **Structured rows instead of plain chunks.** V1 top-six chunks found a listed
   gold page for 9/45 answerable questions. Table titles and merged headers had
   been separated from rows. V2 keeps them together and searches candidate rows.
   The larger V2 candidate set is not directly comparable to V1's six-chunk limit.
3. **Regular line detection.** On the provided coloured tables, strict line
   detection merged many rows; regular line detection recovered their grid.
   Positional fallback is heuristic and may fail on dense scanned layouts.
4. **BM25 without embeddings.** Exact entities, years and column meanings are
   important here. Fixing representation addressed observed failures. Embeddings
   remain an evidence-dependent upgrade if paraphrase recall remains weak.
5. **No first-number heuristic.** The solver selects a requested measure and year,
   rejects ranking/percentage cells and narrower road-class subtotals, and checks
   similarly supported candidates for conflicting values before answering.
6. **Selective OCR.** The declared 4 MB Tesseract English asset runs locally via
   PyMuPDF. Each child process has a timeout and one OpenMP thread. Native text
   is preferred, and original evidence pages are never altered by preprocessing.
7. **Separate evaluation.** Only id/question are retained from input JSONL.
   Gold answers/pages/qtype are read only by the evaluator, never prediction.
   Confidence remains a documented heuristic, not claimed probability calibration.
8. **No report artifacts in the submission.** The scoring command disables disk
   report cache reuse and builds its index from --pdf on each run. Only generic
   configuration and the declared public OCR weights may be shipped.
9. **Compatibility.** Streamlit can continue importing load_report from backend.
   The implementation now lives in src/report_navigator to follow the guide.
   Offline ask returns a numeric answer with a source, rather than an LLM essay.

## V3 — bounded hosted diagnostics, offline scoring preserved

The approved V3 scope improves only the optional hosted Gemma demo and its
failure diagnosis. Google documents gemma-4-26b-a4b-it and gemma-4-31b-it on the
Gemini API (https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api). The first
is retained; there is no silent substitution with Gemini or another Gemma model.

BackendError now carries optional numeric HTTP status while keeping raw provider
exceptions private. The application owns all retries: SDK retries stay disabled,
with exponential backoff plus jitter for transport errors and server failures.
The default two-call budget includes citation repair; configuration permits at
most three. Each real SDK call is clipped to the remaining 45-second default
answer deadline. 429 is deliberately not automatically retried because current
safe error mapping cannot reliably distinguish depleted quota from temporary
rate limiting. Permanent client errors also stop immediately.

The diagnostic progressively tests four request profiles with synthetic evidence
only, stopping on failure and validating the final answer and quotation. It is
explicitly invoked and is not part of offline evaluation or normal unit tests.
This version adds neither local model weights nor vision, retrieval changes,
embeddings, vector databases, or automatic cloud fallback in the scorer.

## V4 — physical row geometry and selective OCR recovery

V4 addresses a measured failure in rasterized tables with wrapped entity names.
Grid-line pixel runs are collapsed into physical boundaries before line removal.
Only sufficiently spaced grids with at least four row and column lines activate
this path. Detected body-row boundaries keep wrapped labels with their values;
text above the physical grid is excluded from column headings. Numeric tokens
must occupy separate expected numeric columns. Ambiguous tokens are rejected,
never split into guessed digits.

An incomplete body row can receive a second full-width row-strip OCR pass, capped
at six attempts per page (validated maximum twelve, zero disables attempts).
Recovery must populate all expected numeric columns, preserve entity-label tokens
and agree with each unambiguous original numeric reading. Coordinates map back
to the original physical page. Accepted words also rebuild prose blocks, avoiding
stale first-pass numeric evidence alongside corrected table rows.

The existing OCR subprocess is the single timeout owner: both passes share its
25-second default cap and the ingestion deadline. An atomic full-pass checkpoint
can survive a killed optional recovery pass. Crop-specific recognition failures
are skipped. A first-pass timeout without a checkpoint still reports OCR timeout.
No model, dependency, cloud call, solver rule or frontend answer contract changed.
Cache fingerprints include V4 extraction revisions and recovery settings.

The synthetic benchmark generates PDFs at runtime, outside the source package.
Seed 0 was used for implementation; seed 19 was checked afterwards using the same
layouts and different numbers/year. Neither is a representative held-out report
benchmark. Recovery itself is exercised with actual OCR plus deliberate first-pass
fault injection. Results on two rasterized organizer pages did not improve; this
version must not be presented as solving dense scanned reports generally.
