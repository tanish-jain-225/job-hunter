"""Unit test suite for jobhunt.web Application Factory and Modular Blueprints."""

from __future__ import annotations

from pathlib import Path
from flask import Flask
from werkzeug.exceptions import NotFound

from jobhunt.web import create_app, handle_exception, get_project_root


def test_create_app_factory():
    """Verify create_app creates a Flask instance with blueprints registered."""
    app_instance = create_app()
    assert isinstance(app_instance, Flask)
    assert app_instance.name == "jobhunt.web"
    # Ensure all 4 blueprints are mounted
    assert "views" in app_instance.blueprints
    assert "jobs" in app_instance.blueprints
    assert "profile" in app_instance.blueprints
    assert "pipeline" in app_instance.blueprints


def test_create_app_custom_folders(tmp_path: Path):
    """Verify create_app accepts custom template and static folders."""
    custom_tmpl = tmp_path / "templates"
    custom_tmpl.mkdir()
    custom_stat = tmp_path / "static"
    custom_stat.mkdir()

    app_instance = create_app(template_folder=custom_tmpl, static_folder=custom_stat)
    assert app_instance.template_folder is not None and Path(app_instance.template_folder) == custom_tmpl
    assert app_instance.static_folder is not None and Path(app_instance.static_folder) == custom_stat


def test_web_handle_exception_http():
    """Verify handle_exception properly formats HTTP errors."""
    app_instance = create_app()
    with app_instance.test_request_context():
        res, code = handle_exception(NotFound("Resource not located"))
        assert code == 404
        assert res.get_json()["status"] == "error"
        assert "Resource not located" in res.get_json()["message"]


def test_web_handle_exception_generic():
    """Verify handle_exception properly formats generic 500 exceptions."""
    app_instance = create_app()
    with app_instance.test_request_context():
        res, code = handle_exception(RuntimeError("Unexpected server failure"))
        assert code == 500
        assert res.get_json()["status"] == "error"
        assert "Internal Error" in res.get_json()["message"]


def test_web_get_project_root():
    """Verify get_project_root returns a valid directory."""
    root = get_project_root()
    assert isinstance(root, Path)
    assert (root / "pyproject.toml").is_file() or (root / "README.md").is_file()
