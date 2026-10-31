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
