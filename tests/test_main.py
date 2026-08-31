"""Unit test for jobhunt.__main__ entrypoint."""

from __future__ import annotations

import runpy


def test_main_execution(monkeypatch):
    called = []

    def mock_main():
        called.append(True)

    monkeypatch.setattr("jobhunt.cli.main", mock_main)
    runpy.run_module("jobhunt.__main__", run_name="__main__")
    assert called == [True]
