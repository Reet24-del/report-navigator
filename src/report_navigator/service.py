"""The document-scoped interface called directly by Streamlit."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .answering import TextGenerator
from .config import Settings
from .evidence import render_page
from .ingest import document_hash, extract_pdf, validate_pdf
from .query import parse_question
from .retrieval import SearchIndex, build_index, retrieve_candidates, retrieve_general
from .schemas import AnswerResult, BackendError, Citation, NumericAnswer, ReportInfo
from .solver import solve
from .storage import read_cache, write_cache


@dataclass(frozen=True)
class Navigator:
    report_info: ReportInfo
    _pdf_bytes: bytes = field(repr=False)
    _index: SearchIndex = field(repr=False)
    _settings: Settings = field(repr=False)
    _generator: "TextGenerator | None" = field(default=None, repr=False)

    def predict(self, question: str) -> NumericAnswer:
        self._validate_question(question)
        return solve(
            question,
            retrieve_candidates(question, self._index, self._settings.candidate_count),
        )

    def _validate_question(self, question):
        if not isinstance(question, str) or not question.strip():
            raise BackendError("invalid_question", "Enter a non-empty question.")
        if len(question) > self._settings.max_question_chars:
            raise BackendError(
                "question_too_long", "The question exceeds the configured length limit."
            )

    def ask(self, question: str, use_page_images: bool = False) -> AnswerResult:
        self._validate_question(question)
        if use_page_images:
            raise BackendError(
                "unsupported_feature",
                "Image-assisted Gemma answering is not implemented in the offline V2 pipeline.",
            )
        if self._generator is None and self._settings.answer_mode == "offline":
            query = parse_question(question)
            if not query.supported or not query.measure:
                return AnswerResult(
                    document_id=self.report_info.document_id,
                    status="insufficient_evidence",
                    answer=(
                        "Offline report QA supports numerical report questions. "
                        "For definitions, explanations or questions about study notes, "
                        "choose Hosted Gemma demo in Report settings. "
                        "That mode requires internet and sends retrieved excerpts to Google."
                    ),
                    warnings=self.report_info.warnings,
                )
            if query.supported and query.measure and not query.entity:
                return AnswerResult(
                    document_id=self.report_info.document_id,
                    status="insufficient_evidence",
                    answer="Please specify the country, state or city in your question.",
                    warnings=self.report_info.warnings,
                )
            prediction = self.predict(question)
            if prediction.answer == "NOT_FOUND":
                return AnswerResult(
                    document_id=self.report_info.document_id,
                    status="insufficient_evidence",
                    answer="I couldn't find sufficient evidence in the indexed report pages.",
                    warnings=self.report_info.warnings,
                )
            source = prediction.source
            citation = Citation(
                evidence_id="E1",
                pdf_page=source.pdf_page,
                page_label=source.page_label,
                quote=source.text,
            )
            return AnswerResult(
                document_id=self.report_info.document_id,
                status="answered",
                answer=f"{prediction.answer} [E1]",
                citations=(citation,),
                warnings=self.report_info.warnings,
            )
        # General document QA is explicit and is never called by predict.py.
        from .answering import assemble_evidence, generate_answer

        matches = retrieve_general(question, self._index)
        evidence = assemble_evidence(matches)
        answer = generate_answer(
            question.strip(),
            evidence,
            self.report_info.document_id,
            self._settings,
            self._generator,
        )
        return answer.model_copy(update={"warnings": self.report_info.warnings})

    def render_page(self, pdf_page: int) -> bytes:
        return render_page(self._pdf_bytes, pdf_page)


def load_report(
    pdf_bytes: bytes,
    filename: str,
    *,
    settings: Settings | None = None,
    generator: "TextGenerator | None" = None,
) -> Navigator:
    """Load a report without requiring a model key until an answer needs inference."""
    settings = settings if settings is not None else Settings.from_env()
    if not isinstance(filename, str):
        raise BackendError(
            "invalid_filename", "Supply a filename for the uploaded report."
        )
    filename = Path(filename).name or "report.pdf"
    page_count = validate_pdf(pdf_bytes, settings)
    document_id = document_hash(pdf_bytes)
    cached = (
        read_cache(document_id, page_count, filename, settings)
        if settings.cache_enabled
        else None
    )
    if cached is None:
        info, chunks = extract_pdf(pdf_bytes, filename, settings)
        if settings.cache_enabled:
            try:
                write_cache(pdf_bytes, info, chunks, settings)
            except OSError:
                info = info.model_copy(
                    update={
                        "warnings": info.warnings
                        + (
                            "The local cache could not be saved; this session can still use the report.",
                        )
                    }
                )
    else:
        info, chunks = cached
    return Navigator(info, pdf_bytes, build_index(chunks), settings, generator)
