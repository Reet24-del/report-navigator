# Report Navigator — Sloths

Offline question answering over government statistics PDFs, with exact integer
answers, physical-page citations and selective OCR. The Streamlit frontend is
being developed separately. V2 does not include a local Gemma model.

## Problem understanding

Journalists and officials need exact figures from long reports containing tables,
not plausible explanations. We retrieve evidence, identify the requested entity,
year and measure, and return the supported cell or NOT_FOUND. The scoring report
is unseen, so the system builds its index from the supplied PDF at runtime and
must cope with scanned pages without internet access.

## Approach

Python 3.11, PyMuPDF, local Tesseract and BM25Plus form the scoring pipeline.
Native tables preserve merged headings, row labels and cell coordinates. OCR
runs selectively in a time-bounded child process using a declared English model;
long grid lines are removed only from the temporary recognition image. Positional
recovery handles some borderless/scanned tables. BM25 and entity constraints
retrieve candidate rows. The solver enforces measure, year, geography and category
constraints, rejects ranks/rates/subtotals, and abstains on unresolved conflicts.

The cloud Gemma adapter from V1 remains isolated for optional manual development.
`predict.py` is always offline, bypasses persistent report caches, and does not
import or call the cloud SDK. No embeddings or vector database are used.

## Validation

The supplied 50 questions were used for development and error diagnosis; their
final score is in-sample, not a held-out generalization estimate. Synthetic PDFs
with invented entities, years and values test general rules, document isolation,
unknown questions, output validation and scanned tables. Outbound socket calls
are denied in the CLI smoke test. Repeatability and runtime are measured locally.
Gold answers, gold pages and qtype labels never enter prediction or retrieval.

## Results

The latest measured public development run matched all 50 answers and accepted
citations: exact match 1.00, citation accuracy 1.00, composite score 1.00, and
hallucination rate 0/5 on public unanswerable questions. It took about 65 seconds
on the development laptop. These figures are not hidden evaluator results and
were obtained after inspecting public failures. No official validation run has
been submitted. Detailed limitations are recorded in docs/error_analysis.md.

## How to run

Use a Python 3.11 environment, install pinned dependencies, and keep the declared
OCR asset at models/tessdata/eng.traineddata. The provided challenge data must stay
outside the repository. The train entry point reproduces generic configuration;
this deterministic pipeline does not fit a statistical model or save report data.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python train.py --data-dir /path/to/public/p5-report-qa-rag --out models/
python predict.py --pdf /path/to/report.pdf --questions /path/to/questions.jsonl --output /tmp/answers.jsonl
python -m pytest -q
```

For a scoring input containing only id and question, output contains exactly id,
answer, page and confidence. Numbers contain no commas or units. NOT_FOUND has a
null page. Confidence is an uncalibrated evidence-strength heuristic in [0, 1].

For local evaluation only:

```bash
python -m src.report_navigator.evaluation --gold /path/to/questions_with_answers.jsonl --predictions /tmp/answers.jsonl --output /tmp/metrics.json
```

## Use of AI tools

OpenAI Codex assisted with architecture, implementation, tests, documentation and
error analysis under version-by-version approval. Public-data failures were
inspected and corrected with general extraction rules. Teammates may use other
assistants; their tools and contributions must be added before final submission.
AI-generated code was reviewed and tested, and limitations are explicitly reported.

## Data & licences

Only the organizer-provided P5 PDF and questions are used for development. Challenge
data, pre-extracted text, tables, caches and answer lookups are excluded from the
repository and runtime assets. The declared Tesseract fast English model is from
tesseract-ocr/tessdata_fast under Apache-2.0; its original license and checksum are
included in models/. PyMuPDF is dual-licensed under AGPL-3.0 or an Artifex commercial
license; other dependencies retain their published licenses. No project-wide
license has been selected on behalf of the team.

## Team

Registered team slug: **sloths**. Backend integration is handled by the repository
owner, Reet24-del. A second member owns Streamlit and a third owns independent
validation and presentation. The two teammates' names have not yet been supplied
and must be filled in before the final submission. Repository owner:
https://github.com/Reet24-del/report-navigator.

### V3 optional Gemma demo check

Run `python scripts/check_gemma.py` to diagnose the hosted Gemma connection using
synthetic evidence. The ignored local `.env` accepts GEMINI_API_KEY and the
settings documented in `.env.example`. Keep ANSWER_MODE=offline for scoring.
The diagnostic makes up to four live requests under a shared 45-second default
budget; ordinary tests use mocks and make no cloud requests. The existing key
passed the V3 live test. Hosted demo success is separate from offline scoring
and does not establish eligibility for the Gemma category. See
BACKEND_INTEGRATION.md and V3_REVIEW.md for contracts, limits and verification.
