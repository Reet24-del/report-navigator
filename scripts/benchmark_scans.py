"""Generate invented reports at runtime; never ship derived challenge data."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from backend import Settings, load_report  # noqa: E402


def make_case(seed=0, *, scanned=True, wrapped=False, dense=False):
    year = 2032 + seed % 5
    values = [731 + seed * 13, 83 + seed * 7, 957 + seed * 11]
    labels = ["North River District", "South Lake District", "West Hill District"]
    years = [year - 1, year] if dense else [year]
    width = 620 if dense else 560
    columns = [30, 200] + [
        200 + i * ((width - 230) / (3 * len(years)))
        for i in range(1, 3 * len(years) + 1)
    ]
    bounds = [65, 110, 160, 210, 260]
    with pymupdf.open() as doc:
        page = doc.new_page(width=width, height=310)
        page.insert_text(
            (30, 35),
            f"Road accidents in districts during {' and '.join(map(str, years))}",
            fontsize=11,
        )
        for y in bounds:
            page.draw_line((columns[0], y), (columns[-1], y))
        for x in columns:
            page.draw_line((x, bounds[0]), (x, bounds[-1]))
        page.insert_text((35, 90), "District", fontsize=9)
        for m, measure in enumerate(["Accidents", "Killed", "Injured"]):
            for j, y in enumerate(years):
                c = 1 + m * len(years) + j
                page.insert_text((columns[c] + 4, 84), measure, fontsize=8)
                page.insert_text((columns[c] + 4, 99), str(y), fontsize=8)
        for r, label in enumerate(labels):
            top = bounds[r + 1]
            if wrapped:
                page.insert_text((35, top + 17), label.rsplit(" ", 1)[0], fontsize=9)
                page.insert_text((35, top + 32), "District", fontsize=9)
            else:
                page.insert_text((35, top + 27), label, fontsize=9)
            for m, value in enumerate(values):
                for j, y in enumerate(years):
                    c = 1 + m * len(years) + j
                    page.insert_text(
                        (columns[c] + 4, top + 27), str(value + r * 17 + j), fontsize=9
                    )
        if scanned:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            with pymupdf.open() as scan:
                target = scan.new_page(width=width, height=310)
                target.insert_image(target.rect, pixmap=pix)
                pdf = scan.tobytes()
        else:
            pdf = doc.tobytes()
    questions = [
        (
            f"How many people were {verb} in {labels[0]} in {year}?",
            str(values[m] + len(years) - 1),
        )
        for m, verb in [(1, "killed"), (2, "injured")]
    ]
    questions.append(
        (f"How many people were killed in Unknown District in {year}?", "NOT_FOUND")
    )
    return pdf, questions


def benchmark(seed=0):
    results = []
    for scanned, wrapped, dense in [
        (False, False, True),
        (True, False, True),
        (True, True, False),
        (True, True, True),
    ]:
        pdf, questions = make_case(seed, scanned=scanned, wrapped=wrapped, dense=dense)
        started = time.monotonic()
        nav = load_report(pdf, "synthetic.pdf", settings=Settings(cache_enabled=False))
        answers = [nav.predict(q) for q, _ in questions]
        results.append(
            {
                "scanned": scanned,
                "wrapped": wrapped,
                "dense": dense,
                "correct": sum(
                    a.answer == expected
                    and (a.page == 1 if expected != "NOT_FOUND" else a.page is None)
                    for a, (_, expected) in zip(answers, questions)
                ),
                "incorrect_answers": sum(
                    a.answer not in {expected, "NOT_FOUND"}
                    for a, (_, expected) in zip(answers, questions)
                ),
                "abstentions": sum(a.answer == "NOT_FOUND" for a in answers),
                "total": len(questions),
                "seconds": round(time.monotonic() - started, 3),
                "answers": [a.answer for a in answers],
                "warnings": list(nav.report_info.warnings),
            }
        )
    return {
        "seed": seed,
        "cases": results,
        "correct": sum(r["correct"] for r in results),
        "total": sum(r["total"] for r in results),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
