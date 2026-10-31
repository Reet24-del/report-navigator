"""Render the original physical PDF page; never a model-generated reconstruction."""

import pymupdf

from .schemas import BackendError


def render_page(pdf_bytes: bytes, pdf_page: int) -> bytes:
    if type(pdf_page) is not int or pdf_page < 1:
        raise BackendError("invalid_page", "Choose a physical PDF page starting at 1.")
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            if pdf_page > len(document):
                raise BackendError(
                    "invalid_page", "The requested page is outside this report."
                )
            page = document[pdf_page - 1]
            # Bound raster dimensions even for unusual, extremely large page sizes.
            scale = min(1.75, 1800 / max(page.rect.width, page.rect.height, 1))
            return page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), alpha=False
            ).tobytes("png")
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise BackendError(
            "page_render_failed", "The source page could not be rendered."
        ) from None
