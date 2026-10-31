"""Deploy with: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1."""

import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Path, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response

from backend import AnswerResult, BackendError, Settings, load_report

from .contracts import DocumentResponse, ErrorResponse, HealthResponse, QuestionRequest
from .documents import DocumentStore

DESCRIPTION = """Upload a PDF, copy the returned **access_id**, and use it in the document routes.

1. Expand **POST /documents**, click **Try it out**, choose a PDF and a mode, then Execute.
2. Copy **access_id** (not report.document_id) from the response.
3. Use it as **id** in **POST /documents/{id}/ask** and enter your question.
4. Use a citation's **pdf_page** in **GET /documents/{id}/pages/{page}** to inspect the original page.
5. Delete your document when finished.

**offline** supports numerical statistical report questions. **hosted** supports general notes
and explanations using Gemma; it sends your question and retrieved excerpts to Google.
Documents expire after 30 idle minutes and disappear on restart. Keep access IDs private.
This public hackathon demo has limited capacity; 429 means retry and 503 means capacity is full.
"""
ERRORS = {
    code: {"model": ErrorResponse}
    for code in (400, 404, 413, 422, 429, 500, 502, 503, 504)
}


class BodyLimit:
    """Enforce the request cap on received bytes, including chunked uploads."""

    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope.get("headers", [])).get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            response = JSONResponse(
                status_code=413,
                content={
                    "code": "request_too_large",
                    "message": "Request exceeds the upload limit.",
                },
            )
            return await response(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                raise HTTPException(413, "Request exceeds the upload limit.")
            return message

        await self.app(scope, limited_receive, send)


def create_app(*, settings=None, store=None, loader=load_report):
    configured = settings if settings is not None else Settings.from_env()
    # Hosted demo limits are intentionally independent from the offline scorer.
    configured = configured.model_copy(
        update={
            "cache_enabled": False,
            "max_pdf_bytes": min(configured.max_pdf_bytes, 20 * 1024 * 1024),
            "max_pages": min(configured.max_pages, 300),
            "runtime_seconds": min(configured.runtime_seconds, 180),
        }
    )
    registry = store if store is not None else DocumentStore()

    @asynccontextmanager
    async def lifespan(application):
        async def cleanup():
            while True:
                await asyncio.sleep(60)
                registry.prune()

        task = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            registry.clear()

    app = FastAPI(
        title="Report Navigator API · Sloths",
        version="6.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        swagger_ui_parameters={
            "persistAuthorization": False,
            "displayRequestDuration": True,
        },
        responses=ERRORS,
    )
    app.add_middleware(BodyLimit, max_bytes=configured.max_pdf_bytes + 1024 * 1024)

    @app.exception_handler(BackendError)
    async def backend_error(request: Request, error: BackendError):
        status = error.http_status
        if status is None:
            status = (
                502
                if error.code.startswith(("model_", "invalid_model", "empty_model"))
                else 400
            )
        elif status in (401, 403):
            status = (
                503  # Server credential errors are not judge authentication failures.
            )
        return JSONResponse(
            status_code=status, content={"code": error.code, "message": error.message}
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "invalid_request",
                "message": "Check the required fields, mode, question length and positive page number in Swagger.",
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content={"code": "http_error", "message": str(error.detail)},
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "The request failed. No answer was accepted.",
            },
        )

    def describe(token, entry):
        return DocumentResponse(
            access_id=token,
            mode=entry.mode,
            expires_after_idle_seconds=registry.ttl_seconds,
            report=entry.navigator.report_info,
        )

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    @app.get("/health", response_model=HealthResponse, tags=["Service"])
    def health():
        """Check service availability without making a model request."""
        return HealthResponse(hosted_available=bool(configured.api_key))

    @app.post(
        "/documents",
        response_model=DocumentResponse,
        status_code=201,
        tags=["Documents"],
    )
    def upload_document(
        file: Annotated[
            UploadFile, File(description="PDF, maximum 20 MiB and 300 pages.")
        ],
        mode: Annotated[Literal["offline", "hosted"], Form()] = "offline",
    ):
        """Upload and index a PDF. Copy access_id for subsequent requests."""
        try:
            with registry.operation():
                if mode == "hosted" and not configured.api_key:
                    raise BackendError(
                        "missing_api_key",
                        "Hosted mode is unavailable on this deployment. Choose offline.",
                        http_status=503,
                    )
                content = file.file.read(configured.max_pdf_bytes + 1)
                if len(content) > configured.max_pdf_bytes:
                    raise BackendError(
                        "pdf_too_large",
                        "PDF exceeds the 20 MiB upload limit.",
                        http_status=413,
                    )
                registry.check_capacity(len(content))
                navigator = loader(
                    content,
                    file.filename or "document.pdf",
                    settings=configured.model_copy(update={"answer_mode": mode}),
                )
                token = registry.add(navigator, mode, len(content))
                return describe(token, registry.get(token))
        finally:
            file.file.close()

    @app.get("/documents/{id}", response_model=DocumentResponse, tags=["Documents"])
    def document_info(id: str):
        """Read metadata using the access_id returned by upload."""
        return describe(id, registry.get(id))

    @app.post("/documents/{id}/ask", response_model=AnswerResult, tags=["Questions"])
    def ask(id: str, body: QuestionRequest):
        """Answer from this document; citations use 1-based physical PDF pages."""
        with registry.operation():
            entry = registry.get(id)
            if entry.mode == "hosted":
                registry.consume_hosted_request()
            return entry.navigator.ask(body.question)

    @app.get(
        "/documents/{id}/pages/{page}",
        tags=["Evidence"],
        response_class=Response,
        responses={
            200: {
                "description": "Original physical PDF page",
                "content": {"image/png": {}},
            }
        },
    )
    def page_image(id: str, page: Annotated[int, Path(ge=1)]):
        """View a citation's pdf_page as the original rendered PNG."""
        with registry.operation():
            entry = registry.get(id)
            return Response(
                entry.navigator.render_page(page),
                media_type="image/png",
                headers={"Cache-Control": "no-store"},
            )

    @app.delete(
        "/documents/{id}", status_code=204, response_class=Response, tags=["Documents"]
    )
    def delete_document(id: str):
        """Release this document. Expired or unknown access IDs return 404."""
        with registry.operation():
            registry.delete(id)
        return Response(status_code=204)

    @app.get("/swagger.json", include_in_schema=False)
    def swagger_spec():
        return JSONResponse(app.openapi())

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app


app = create_app()
