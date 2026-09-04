"""Serving the built React app from the API process (single-origin deploy).

Skipped entirely when `frontend/dist` has not been built -- the mount is
conditional, and a backend-only checkout is a legitimate state.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import _DIST, _INDEX, _safe_asset, app

pytestmark = pytest.mark.skipif(
    not _INDEX.is_file(), reason="frontend/dist not built"
)

client = TestClient(app)


def test_root_serves_the_app_shell():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_unknown_path_falls_back_to_the_shell():
    """Client-side routes must not 404 on a hard refresh."""
    resp = client.get("/some/client/route")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_api_routes_still_win():
    assert client.get("/api/health").json()["status"] == "ok"


def test_unknown_api_path_404s_as_json_not_html():
    """The catch-all must not swallow API mistakes into a 200 HTML page."""
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.parametrize(
    "attack",
    [
        "../../../etc/passwd",
        "../../backend/.env",
        "..%2f..%2f.env",
        "....//....//.env",
    ],
)
def test_traversal_never_escapes_the_build_directory(attack):
    """A path outside dist resolves to None, so the shell is served instead."""
    assert _safe_asset(attack) is None
    resp = client.get(f"/{attack}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_real_assets_are_served():
    asset = next((_DIST / "assets").glob("*.js"), None)
    if asset is None:
        pytest.skip("no built js asset")
    resp = client.get(f"/assets/{asset.name}")
    assert resp.status_code == 200
    assert resp.content == asset.read_bytes()


def test_safe_asset_rejects_the_root_itself():
    assert _safe_asset("") is None
    assert _safe_asset(".") is None


def test_head_on_the_shell_is_allowed():
    """Platform probes use HEAD; FastAPI does not add it to a GET route, and a
    405 there can make a host read the service as unhealthy."""
    assert client.head("/").status_code == 200
