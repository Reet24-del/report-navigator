"""Public request and response contracts used to generate Swagger documentation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend import ReportInfo


class QuestionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"question": "How does RSA work according to these notes?"}]
        },
    )
    question: str = Field(min_length=1, max_length=2000)


class DocumentResponse(BaseModel):
    access_id: str = Field(
        description="Random document access token. Keep private; use it as {id} in document routes."
    )
    mode: Literal["offline", "hosted"]
    expires_after_idle_seconds: int
    report: ReportInfo


class ErrorResponse(BaseModel):
    code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = "6.0.0"
    hosted_available: bool
