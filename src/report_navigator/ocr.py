"""Time-bounded local OCR; child processes write only into temporary storage."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pymupdf

from .config import PROJECT_ROOT, Settings
from .schemas import BackendError


class RecognizedPage:
    """Present OCR words/blocks through the small extraction interface we use."""

    def __init__(self, page, payload):
        self.number = page.number
        self.rect = page.rect
        self._label = page.get_label()
        self._payload = payload

    def get_label(self):
        return self._label

    def get_text(self, option, **kwargs):
        return self._payload[option]


def needs_ocr(page, text: str, settings: Settings) -> bool:
    if not text.strip():
        return bool(page.get_images())
    if text.count("\ufffd") > max(2, len(text) * 0.05):
        return True
    area = max(1, page.rect.get_area())
    image_cover = any(
        pymupdf.Rect(image["bbox"]).get_area() / area > 0.7
        for image in page.get_image_info()
    )
    return image_cover and len(text.split()) < 100


def recognize_page(page, settings: Settings, seconds: float):
    if not (settings.tessdata_dir / "eng.traineddata").is_file():
        raise BackendError(
            "ocr_unavailable",
            "Tesseract eng.traineddata is missing from the configured tessdata directory.",
        )
    with tempfile.TemporaryDirectory(prefix="navigator-ocr-") as folder:
        source = Path(folder) / "page.pdf"
        result = Path(folder) / "words.json"
        with pymupdf.open() as single:
            single.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
            single.save(source)
        command = [
            sys.executable,
            "-m",
            "src.report_navigator.ocr",
            "--worker-input",
            str(source),
            "--worker-output",
            str(result),
            "--tessdata",
            str(settings.tessdata_dir.resolve()),
            "--dpi",
            str(settings.ocr_dpi),
        ]
        environment = os.environ.copy()
        environment.update(
            OMP_THREAD_LIMIT="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1"
        )
        try:
            subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=max(0.1, min(settings.ocr_page_seconds, seconds)),
            )
            return json.loads(result.read_text())
        except subprocess.TimeoutExpired:
            raise BackendError(
                "ocr_timeout", "A scanned page exceeded the OCR time budget."
            ) from None
        except (subprocess.CalledProcessError, OSError, ValueError):
            raise BackendError(
                "ocr_failed",
                "A scanned page could not be recognized by the local OCR engine.",
            ) from None


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-input", required=True)
    parser.add_argument("--worker-output", required=True)
    parser.add_argument("--tessdata", required=True)
    parser.add_argument("--dpi", type=int, required=True)
    args = parser.parse_args()
    with pymupdf.open(args.worker_input) as document:
        page = document[0]
        dpi = min(args.dpi, int(5000 * 72 / max(page.rect.width, page.rect.height, 1)))
        pixmap = page.get_pixmap(
            dpi=max(72, dpi), colorspace=pymupdf.csRGB, alpha=False
        )
        pixels = (
            np.frombuffer(pixmap.samples, dtype=np.uint8)
            .reshape(pixmap.height, pixmap.width, 3)
            .copy()
        )
        dark = pixels.mean(axis=2) < 90
        horizontal = np.flatnonzero(dark.mean(axis=1) > 0.6)
        vertical = np.flatnonzero(dark.mean(axis=0) > 0.3)
        for offset in (-1, 0, 1):
            pixels[np.clip(horizontal + offset, 0, pixmap.height - 1), :, :] = 255
            pixels[:, np.clip(vertical + offset, 0, pixmap.width - 1), :] = 255
        clean = pymupdf.Pixmap(
            pymupdf.csRGB, pixmap.width, pixmap.height, pixels.tobytes(), False
        )
        with pymupdf.open() as temporary:
            cleaned_page = temporary.new_page(
                width=page.rect.width, height=page.rect.height
            )
            cleaned_page.insert_image(cleaned_page.rect, pixmap=clean)
            textpage = cleaned_page.get_textpage_ocr(
                language="eng", dpi=max(72, dpi), full=True, tessdata=args.tessdata
            )
            payload = {
                "words": cleaned_page.get_text("words", textpage=textpage),
                "blocks": cleaned_page.get_text("blocks", textpage=textpage, sort=True),
            }
    Path(args.worker_output).write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    _main()
