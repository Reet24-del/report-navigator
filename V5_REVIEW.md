# V5 review: general document QA

V5 extends the explicit hosted mode to study notes and explanatory PDFs. It does
not add a local language model or change the numerical scoring solver. No new
runtime dependency, API key or paid infrastructure is introduced.

## Implementation

Existing ingestion already creates overlapping, page-bound text chunks with
physical page metadata. This was retained rather than duplicated. Hosted
retrieval now filters generic question verbs, bounds context to six original
chunks and 18,000 characters, limits each page to two chunks, and skips strongly
overlapping excerpts. Offline retrieval and predict() are unchanged.

The Gemma system instruction now covers definitions, explanations and comparisons.
Excerpts are separate JSON strings, preventing artificial text joins in the
prompt. Existing validation requires exact agreement between inline evidence IDs
and citation records, an exact normalized quote inside one actual chunk, and
backend-assigned physical page numbers. evidence.py required no modification:
it already renders the original physical page correctly.

Offline theory questions now explain that hosted mode is needed, rather than
implying the PDF necessarily lacks evidence. Hosted mode labels disclose network
use. A document-and-mode scoped question widget prevents Streamlit restoring a
stale browser question after mode changes; previous answer state is also cleared.

## Verification

- Full automated suite: 135 passed. After the final widget-key adjustment, the
  affected frontend suite was repeated: 10 passed.
- Ruff basic correctness and import checks passed for changed Python files.
- Synthetic three-page cryptography notes test verifies exact quotation and
  physical page 2; unrelated questions make no model call.
- Invalid and cross-excerpt quotes are rejected; missing credentials raise a
  configuration error rather than being reported as missing evidence.
- One live hosted request compared RSA and symmetric encryption from invented
  notes. It answered with a verified quote on physical page 1, using the existing
  key and configured Gemma model. No user notes were transmitted for this test.
- Browser checks use the already installed Playwright Chromium because the Browser
  plugin is not available. See the adjacent output evidence for local UI checks.

## Critical limits

Exact quotes establish source provenance, not logical entailment of every claim.
A model can misinterpret a real passage. Prompt injection is addressed through
system instructions and data separation, but the controlled test does not prove
empirical resistance. BM25 can miss paraphrases; per-page/context limits can omit
needed passages. Whole-document summaries, image understanding, handwriting and
mathematical notation are not guaranteed. The new synthetic/live checks do not
establish unseen-document accuracy or benchmark the user's cryptography notes.

No FastAPI server is introduced in V5. HTTP routes and Swagger remain a separate
pending version. V5 was published together with V6 in commit 8850331d2bb1d95913537515b664e5fdc4251974.
Public Streamlit release verification is recorded separately from local results.

Public Streamlit verification passed after reboot: offline theory guidance, mode
reset, and hosted notes answer with a physical page citation. V6 provides the
separate live HTTP API and interactive Swagger documentation.
