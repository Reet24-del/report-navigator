"""Exercise the HTTP contract without external network requests."""

import json

import pytest
from fastapi.testclient import TestClient
from test_documents import make_pdf
from test_tables import make_grid_pdf

from api.documents import DocumentStore
from api.main import create_app
from backend import Settings, load_report


@pytest.fixture
def client():
    with TestClient(
        create_app(settings=Settings(ocr_enabled=False, cache_enabled=False))
    ) as client:
        yield client


def upload(client, content=None, mode="offline"):
    return client.post(
        "/documents",
        files={"file": ("invented.pdf", content or make_grid_pdf(), "application/pdf")},
        data={"mode": mode},
    )


def test_judge_offline_workflow(client):
    assert client.get("/health").json()["status"] == "ok"
    created = upload(client)
    assert created.status_code == 201
    token = created.json()["access_id"]
    assert token != created.json()["report"]["document_id"]
    assert client.get(f"/documents/{token}").json()["mode"] == "offline"
    answer = client.post(
        f"/documents/{token}/ask",
        json={"question": "How many people were killed in North District in 2027?"},
    )
    assert answer.status_code == 200
    assert answer.json()["answer"] == "73 [E1]"
    page = answer.json()["citations"][0]["pdf_page"]
    image = client.get(f"/documents/{token}/pages/{page}")
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")
    assert image.headers["cache-control"] == "no-store"
    assert client.delete(f"/documents/{token}").status_code == 204
    assert client.get(f"/documents/{token}").status_code == 404


def test_docs_and_identical_specs(client):
    docs = client.get("/docs")
    assert docs.status_code == 200 and "SwaggerUIBundle" in docs.text
    spec = client.get("/openapi.json").json()
    assert spec == client.get("/swagger.json").json()
    for route in [
        "/health",
        "/documents",
        "/documents/{id}",
        "/documents/{id}/ask",
        "/documents/{id}/pages/{page}",
    ]:
        assert route in spec["paths"]
    upload_schema = spec["paths"]["/documents"]["post"]["requestBody"]["content"]
    assert "multipart/form-data" in upload_schema
    assert (
        "image/png"
        in spec["paths"]["/documents/{id}/pages/{page}"]["get"]["responses"]["200"][
            "content"
        ]
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": "x" * 2001},
        {"question": "RSA", "extra": True},
    ],
)
def test_invalid_questions(client, body):
    assert client.post("/documents/unknown/ask", json=body).status_code == 422


def test_invalid_upload_and_missing_document(client):
    assert client.post("/documents").status_code == 422
    assert upload(client, b"not PDF").status_code == 400
    assert upload(client, mode="invalid").status_code == 422
    assert client.get("/documents/unknown").status_code == 404
    assert client.get("/documents/unknown/pages/0").status_code == 422
    assert upload(client, mode="hosted").status_code == 503


def test_capacity_and_random_ids_isolate_uploads(client):
    first = upload(client).json()["access_id"]
    second = upload(client).json()["access_id"]
    assert first != second
    assert upload(client).status_code == 503
    client.delete(f"/documents/{first}")
    assert client.get(f"/documents/{second}").status_code == 200
    assert upload(client).status_code == 201


def test_idle_expiry_and_busy_response():
    clock = [0.0]
    store = DocumentStore(ttl_seconds=10, clock=lambda: clock[0])
    with TestClient(
        create_app(settings=Settings(ocr_enabled=False), store=store)
    ) as client:
        token = upload(client).json()["access_id"]
        clock[0] = 11
        assert client.get(f"/documents/{token}").status_code == 404
        with store.operation():
            assert upload(client).status_code == 429
    assert not store.entries


def test_oversize_body_is_rejected_before_ingestion():
    app = create_app(settings=Settings(max_pdf_bytes=100, ocr_enabled=False))
    with TestClient(app) as client:
        assert upload(client, b"x" * 101).status_code == 413
        response = client.post(
            "/documents",
            content=b"x" * (1024 * 1024 + 101),
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 413


def test_hosted_citations_and_provider_errors_are_safe():
    quote = "RSA uses a public key for encryption and a private key for decryption."

    class Generator:
        def generate(self, prompt):
            payload = json.loads(prompt)
            assert quote in payload["evidence"][0]["excerpts"][0]
            return json.dumps(
                {
                    "status": "answered",
                    "answer": quote + " [E1]",
                    "citations": [{"evidence_id": "E1", "quote": quote}],
                }
            )

    def loader(content, filename, *, settings):
        return load_report(content, filename, settings=settings, generator=Generator())

    store = DocumentStore()
    with TestClient(
        create_app(
            settings=Settings(api_key="fake", ocr_enabled=False),
            loader=loader,
            store=store,
        )
    ) as client:
        token = upload(client, make_pdf([quote]), mode="hosted").json()["access_id"]
        result = client.post(
            f"/documents/{token}/ask", json={"question": "Explain RSA"}
        )
        assert result.json()["citations"][0]["pdf_page"] == 1
        store.hosted_requests = 60
        assert (
            client.post(
                f"/documents/{token}/ask", json={"question": "Explain RSA"}
            ).status_code
            == 429
        )


def test_internal_errors_do_not_expose_details():
    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE SECRET")

    with TestClient(
        create_app(settings=Settings(), loader=broken), raise_server_exceptions=False
    ) as client:
        result = upload(client)
        assert result.status_code == 500
        assert "PRIVATE" not in result.text
