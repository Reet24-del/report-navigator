"""Run the required entry point on generated input with outbound sockets denied."""

import json
import socket

from predict import main
from test_tables import make_grid_pdf


def test_offline_cli(tmp_path, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Scoring must not call a network service")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(make_grid_pdf())
    questions = tmp_path / "questions.jsonl"
    questions.write_text(
        '{"id":"Q1","question":"How many people were killed in North District in 2027?"}\n'
    )
    output = tmp_path / "answers.jsonl"
    assert (
        main(
            ["--pdf", str(pdf), "--questions", str(questions), "--output", str(output)]
        )
        == 0
    )
    assert json.loads(output.read_text())["answer"] == "73"
