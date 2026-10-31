"""Validated contracts shared by the backend and its Streamlit caller."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BackendError(Exception):
    """An actionable error safe to display without provider response details."""

    def __init__(self, code: str, message: str, *, http_status: int | None = None):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class TableCell(Contract):
    header: str
    value: str
    bbox: tuple[float, float, float, float] | None = None


class TableRow(Contract):
    table_id: str
    title: str
    label: str
    cells: tuple[TableCell, ...]


class Chunk(Contract):
    chunk_id: str
    document_id: str
    pdf_page: int = Field(ge=1)
    page_label: str | None = None
    text: str = Field(min_length=1)
    bboxes: tuple[tuple[float, float, float, float], ...] = ()
    extraction_method: Literal["native", "ocr"] = "native"
    table: TableRow | None = None


class ReportInfo(Contract):
    document_id: str
    filename: str
    page_count: int = Field(ge=1)
    searchable_pages: int = Field(ge=1)
    ocr_pages: int = 0
    unprocessed_pages: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()
    supported_features: tuple[str, ...] = (
        "text_answers",
        "page_viewer",
        "offline_numbers",
        "ocr",
    )


class Evidence(Contract):
    evidence_id: str
    pdf_page: int = Field(ge=1)
    page_label: str | None = None
    chunks: tuple[Chunk, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(chunk.text for chunk in self.chunks)


class Citation(Contract):
    evidence_id: str
    pdf_page: int = Field(ge=1)
    page_label: str | None = None
    source_type: Literal["text", "page_image"] = "text"
    quote: str | None = None


class AnswerResult(Contract):
    document_id: str
    status: Literal["answered", "insufficient_evidence"]
    answer: str = Field(min_length=1)
    citations: tuple[Citation, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def check_citations(self) -> "AnswerResult":
        if self.status == "answered" and not self.citations:
            raise ValueError("An answered result requires a citation.")
        if self.status == "insufficient_evidence" and self.citations:
            raise ValueError("An insufficient-evidence result must not have citations.")
        return self


class ModelCitation(Contract):
    evidence_id: str = Field(pattern=r"^E[1-9]\d*$")
    quote: str = Field(min_length=1, max_length=4000)


class ModelAnswer(Contract):
    """The model selects evidence IDs; it cannot supply authoritative page numbers."""

    status: Literal["answered", "insufficient_evidence"]
    answer: str = Field(min_length=1, max_length=12000)
    citations: tuple[ModelCitation, ...] = Field(max_length=12)


class NumericAnswer(Contract):
    answer: str = Field(pattern=r"^(?:[0-9]+|NOT_FOUND)$")
    page: int | None = Field(default=None, ge=1)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    source: Chunk | None = None
    reason: str


class SubmissionRecord(Contract):
    id: str = Field(min_length=1, strict=True)
    answer: str = Field(pattern=r"^(?:[0-9]+|NOT_FOUND)$", strict=True)
    page: int | None = Field(default=None, ge=1, strict=True)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_page(self) -> "SubmissionRecord":
        if (self.answer == "NOT_FOUND") != (self.page is None):
            raise ValueError(
                "NOT_FOUND needs a null page; an integer answer needs a page."
            )
        return self
