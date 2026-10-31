# V3 implementation and critical review

Approved scope: reliable optional hosted Gemma diagnostics and bounded requests.
Implemented on 31 October 2026. Publication is authorized by the user;
GitHub commit history records the published snapshot.

## Changes and reasons

- config.py restricts hosted model IDs to the two officially documented Gemma 4
  choices, reads GEMMA_DEADLINE_SECONDS and GEMMA_MAX_ATTEMPTS, and retains offline
  defaults. Existing local .env credentials were not edited or packaged.
- schemas.py adds optional numeric http_status to BackendError without changing
  the answer/citation schema or existing two-argument exception callers.
- answering.py preserves safe HTTP status, rejects empty text, and owns the retry
  budget. SDK retries remain disabled. Provider and JSON-repair calls share a
  maximum of three attempts (default two). Transport/server failures use bounded
  exponential backoff with jitter; 429 stops for quota inspection. Real SDK call
  timeouts are clipped to the remaining overall 45-second default budget.
- scripts/check_gemma.py runs explicit synthetic-only diagnostics in four stages:
  bare request, system instructions, thinking configuration, grounded request.
  It stops at the first failure and prints only safe fields. The final stage
  checks the expected number as a complete token and verifies exact quotations.
- tests/test_answers.py and tests/test_gemma_check.py cover the SDK boundary,
  empty responses, numeric status privacy, retry/repair budgets, deadlines,
  model validation, diagnostic progression, and incorrect/fabricated evidence.
- .env.example, README.md, BACKEND_INTEGRATION.md and docs/decisions.md explain
  configuration, teammate integration and the separation from offline scoring.

## Verification

Python 3.11: 97 tests passed, with five existing PyMuPDF/SWIG deprecation warnings.
Ruff E4/E7/E9/F/I checks passed for all changed Python files. Formatting applied.

An initial four-stage live diagnostic with an explicit 2048-token ceiling passed
in 10.915 seconds. A final stricter bare-request diagnostic (no generation config)
returned HTTP 500 at its first stage. A separate final call through the actual
configured generate_answer path passed and returned:

"In 2025, the sample programme covered 125 districts [E1]."

The exact supporting quote was "The sample programme covered 125 districts in
2025." and the backend assigned physical page 1. Both live successes used the
existing key and gemma-4-26b-a4b-it. The key was never printed. The earlier error
cannot be conclusively attributed to outage, default generation settings or
another provider-side cause. We retained explicit production settings that
worked, and improved error/retry handling; we did not claim to fix Google's service.

Final sanitized evidence is saved outside the source package in
../v2-verification/gemma-v3-check.json (bare request failure) and
../v2-verification/gemma-v3-grounded.json (configured answer success).

The offline public regression wrote 50 records in 66.74 seconds and indexed
260/272 pages. Its output is byte-identical to V2, SHA256:
2cbededae25551654e337b4770383a6de6f62d5da0a47518527a2373b283ddeb.
Importing predict.py did not load google.genai. Public samples remain an
in-sample regression, not evidence of hidden-set accuracy or Linux sandbox timing.

## Critical review and remaining limits

1. Hosted service reliability remains external. The bare-request HTTP 500 is
   unresolved. A replacement key is not indicated: the existing key successfully
   generated the configured answer. Change credentials only for an explicit
   invalid/blocked/leaked key or other confirmed credential issue. Project quota
   or access issues generally require project-level diagnosis.
2. Quote validation establishes source existence and page mapping, not complete
   semantic entailment of every claim. A model can still misinterpret an actual
   quote. V3 did not add an independent semantic verifier.
3. The overall deadline clips real transport timeouts and checks elapsed time;
   it is not a process-level hard kill. Client cleanup/scheduling can add overhead.
   Injected custom generators must implement their own blocking timeout.
4. The bare diagnostic does not retry automatically. It is designed to isolate
   the first failure without multiplying live calls; the actual answer path owns
   bounded transient retries. Quota errors never trigger blind retry loops.
5. No local Gemma, vision, new retrieval, embeddings or vector database was added.
   Hosted success does not establish eligibility for the Gemma category. Scoring
   remains offline and cannot use this API path.
6. The Streamlit UI is maintained by the teammate. V3 supplies integration
   instructions and preserves navigator.ask(), but their app has not been tested
   here. Hosted mode must be selected explicitly and accurately labelled.

Review fixes applied before completion: diagnostic expected-answer matching now
uses word boundaries (1125 is rejected), a bare request actually omits generation
config, and additional tests cover empty output and remaining-deadline clipping.
