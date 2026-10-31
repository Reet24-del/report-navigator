"""Time-bounded local OCR; child processes write only into temporary storage."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from statistics import median

import numpy as np
import pymupdf

from .config import PROJECT_ROOT, Settings
from .schemas import BackendError
from .table_quality import (
    consistent_recovery,
    data_band,
    line_centers,
    numeric_cells,
    remap_words,
)


class RecognizedPage:
    """Present OCR words/blocks through the small extraction interface we use."""

    def __init__(self, page, payload):
        self.number = page.number
        self.rect = page.rect
        self._label = page.get_label()
        self._payload = payload
        self.grid_rows = payload.get("grid_rows", [])
        self.grid_columns = payload.get("grid_columns", [])

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
            "--seconds",
            str(max(0.1, min(settings.ocr_page_seconds, seconds))),
            "--max-regions",
            str(settings.ocr_max_regions if settings.ocr_recovery_enabled else 0),
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
            # A completed first pass can survive a killed optional recovery pass.
            try:
                payload = json.loads(result.read_text())
                if payload.get("words") and payload.get("blocks"):
                    payload["recovery_timed_out"] = True
                    return payload
            except (OSError, ValueError):
                pass
            raise BackendError(
                "ocr_timeout", "A scanned page exceeded the OCR time budget."
            ) from None
        except (subprocess.CalledProcessError, OSError, ValueError):
            raise BackendError(
                "ocr_failed",
                "A scanned page could not be recognized by the local OCR engine.",
            ) from None


def recover_regions(
    words, pixels, row_pixels, column_pixels, rect, tessdata, dpi, max_regions, deadline
):
    """Retry only incomplete body rows; all work stays inside one timed child."""
    height, width = pixels.shape[:2]
    columns = [x / width * rect.width for x in column_pixels]
    output = list(words)
    attempts = 0
    for top, bottom in zip(row_pixels, row_pixels[1:]):
        if attempts >= max_regions or time.monotonic() >= deadline - 0.25:
            break
        y0, y1 = top / height * rect.height, bottom / height * rect.height
        original = [w for w in words if y0 <= (w[1] + w[3]) / 2 < y1]
        if not data_band(original, columns):
            continue
        cells = numeric_cells(original, columns)
        if cells is not None and set(cells) == set(range(1, len(columns) - 1)):
            continue
        attempts += 1
        # Full-width row strips preserve labels and original column positions.
        lo, hi = max(0, int(top) + 2), min(height, int(bottom) - 1)
        crop = pixels[lo:hi].copy()
        if not crop.size:
            continue
        pix = pymupdf.Pixmap(pymupdf.csRGB, width, hi - lo, crop.tobytes(), False)
        try:
            with pymupdf.open() as document:
                target = document.new_page(
                    width=rect.width, height=(hi - lo) / height * rect.height
                )
                target.insert_image(target.rect, pixmap=pix)
                tp = target.get_textpage_ocr(
                    language="eng", dpi=dpi, full=True, tessdata=tessdata
                )
                recovered = remap_words(
                    target.get_text("words", textpage=tp),
                    (0, lo / height * rect.height),
                )
        except (RuntimeError, ValueError):
            continue
        if consistent_recovery(original, recovered, columns):
            original_ids = {id(w) for w in original}
            output = [w for w in output if id(w) not in original_ids] + recovered
    return output, attempts


def blocks_from_words(words):
    """Keep prose evidence consistent with accepted recovered table tokens."""
    if not words:
        return []
    height = median(max(1, w[3] - w[1]) for w in words)
    lines = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        center = (word[1] + word[3]) / 2
        if lines and abs(center - lines[-1][0]) < height * 0.45:
            lines[-1][1].append(word)
        else:
            lines.append((center, [word]))
    return [
        (
            min(w[0] for w in line),
            min(w[1] for w in line),
            max(w[2] for w in line),
            max(w[3] for w in line),
            " ".join(w[4] for w in sorted(line, key=lambda w: w[0])),
            i,
            0,
        )
        for i, (_, line) in enumerate(lines)
    ]


def _write_payload(destination, payload):
    temporary = destination.with_suffix(".partial")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(destination)


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-input", required=True)
    parser.add_argument("--worker-output", required=True)
    parser.add_argument("--tessdata", required=True)
    parser.add_argument("--dpi", type=int, required=True)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--max-regions", type=int, required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + args.seconds
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
        grid_rows = line_centers(horizontal)
        grid_columns = line_centers(vertical)
        # Only use an actual rectangular grid, with minimum physical spacing.
        valid_grid = (
            len(grid_rows) >= 4
            and len(grid_columns) >= 4
            and min(np.diff(grid_rows)) > 12
            and min(np.diff(grid_columns)) > 12
        )
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
            if valid_grid:
                rows = [y / pixmap.height * page.rect.height for y in grid_rows]
                columns = [x / pixmap.width * page.rect.width for x in grid_columns]
                payload.update(grid_rows=rows, grid_columns=columns)
                _write_payload(Path(args.worker_output), payload)
                recovered, attempted = recover_regions(
                    payload["words"],
                    pixels,
                    grid_rows,
                    grid_columns,
                    page.rect,
                    args.tessdata,
                    args.dpi,
                    args.max_regions,
                    deadline,
                )
                if recovered != payload["words"]:
                    payload["blocks"] = blocks_from_words(recovered)
                payload["words"] = recovered
                payload["recovery_attempted"] = attempted
    _write_payload(Path(args.worker_output), payload)


if __name__ == "__main__":
    _main()
