# V6 API review

The FastAPI transport calls the same Python backend used by Streamlit. It does
not alter predict.py, the numerical solver, or the offline scoring contract.
Swagger UI at /docs supports PDF upload, question submission and source-page
retrieval. /openapi.json and /swagger.json expose the same generated specification.

## Implementation and review

- api/contracts.py reuses backend report and answer schemas, forbids extra question
  fields, and documents the random access_id separately from the PDF content hash.
- api/documents.py stores two active documents at most, with 40 MiB aggregate input
  bytes and 30-minute idle expiry. A periodic sweep and request-time checks expire
  entries. Restart loses state; this is a single-worker demonstration service.
- A shared nonblocking semaphore serializes expensive PyMuPDF operations and
  protects capacity admission; busy requests return 429 rather than queueing work.
- Persistent extraction caches are disabled for the API. Uploads are limited to
  20 MiB/300 pages and ingestion uses a 180-second runtime budget. Multipart
  temporary files close after ingestion. Request-body limits include framing.
- Exceptions expose safe messages, not provider responses or credentials.
  Responses disable browser caching. Access IDs are bearer-like secrets, not an
  account authentication system. Uvicorn access logs are disabled to avoid logging
  document-token paths. Hosted mode is explicit and requires a server-side key.
- The hosted demo limits model attempts to 60 per process. This resets on restart
  and is not a persistent billing or abuse protection system.
- Docker installs Tesseract and runs as an unprivileged user. Its build context
  uses an allowlist; secrets, datasets and generated report caches are excluded.

## Local validation

147 automated tests passed, including 12 API tests for upload/ask/page/delete,
invalid inputs, request limits, capacity, expiry, document isolation, model
citations, missing credentials and safe unexpected failures. Ruff checks passed.
Existing numerical and frontend tests also passed. A local interactive Swagger
browser verification and public deployment verification are recorded separately.
Docker is unavailable on the development laptop, so a local container build was
not claimed; the Render build must validate the container on the deployment host.

## Limits

Upload-byte limits do not strictly bound decompressed PDF/index memory. A complex
PDF can still exhaust a small free instance. Serial operation limits concurrency
but does not provide multi-user service guarantees. A free host can sleep and
restart, invalidating document IDs. Swagger UI uses its upstream CDN assets and
requires browser internet access. Citation provenance is checked, not complete
semantic correctness. Full production authentication, durable storage, distributed
workers and persistent quotas are outside this hackathon version.
