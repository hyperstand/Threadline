"""M9 web UI: served page, static assets, CSP, and the untrusted-text rule."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from threadline.config import Settings
from threadline.main import UI_DIR, create_app

ROOT = Path(__file__).resolve().parents[2]


def _client(tmp_path, monkeypatch) -> TestClient:
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(THREADLINE_ENV="test", DATABASE_URL=url)
    return TestClient(create_app(settings))


def test_root_serves_the_ui_with_a_strict_csp(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    csp = resp.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp


def test_page_has_the_three_navigable_screens_and_no_inline_code(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        html = client.get("/").text
    for view in ("library", "workspace", "history"):
        assert f'href="#{view}"' in html
    assert '<script src="/ui/app.js"></script>' in html
    assert '<link rel="stylesheet" href="/ui/app.css">' in html
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline <script> would be blocked by the CSP"
    assert ' style="' not in html


@pytest.mark.parametrize(
    ("path", "content_type", "marker"),
    [
        ("/ui/app.js", "javascript", "renderWorkspace"),
        ("/ui/app.css", "text/css", ".badge"),
    ],
)
def test_static_assets_are_served(tmp_path, monkeypatch, path: str, content_type: str, marker: str) -> None:
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get(path)
    assert resp.status_code == 200
    assert content_type in resp.headers["content-type"]
    assert marker in resp.text


def _code_without_comments(script: str) -> str:
    script = re.sub(r"/\*.*?\*/", "", script, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", script, flags=re.MULTILINE)


def test_untrusted_text_is_never_written_as_html() -> None:
    # Document text, questions, and tool output reach the page. They must go through
    # textContent or text nodes. A single innerHTML write would make stored XSS possible.
    script = _code_without_comments((UI_DIR / "app.js").read_text(encoding="utf-8"))
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in script, f"{sink} would render untrusted text as HTML"


def test_script_parses() -> None:
    esprima = pytest.importorskip("esprima")
    script = (UI_DIR / "app.js").read_text(encoding="utf-8")
    esprima.parseScript(script)


def test_ui_files_are_declared_as_package_data() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["threadline"]
    assert {"ui/*.html", "ui/*.css", "ui/*.js"} <= set(patterns)
    for name in ("index.html", "app.css", "app.js"):
        assert (UI_DIR / name).is_file()
