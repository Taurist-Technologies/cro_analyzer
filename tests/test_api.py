"""API-level tests using FastAPI's TestClient (no network, no Redis needed)."""

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_root_describes_pdp_service():
    r = client.get("/")
    assert r.status_code == 200
    assert "PDP" in r.json()["focus"] or "Product" in r.json()["focus"]


def test_analyze_rejects_private_url():
    r = client.post("/analyze", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert r.status_code == 400
    assert "rejected" in r.json()["detail"].lower()


def test_analyze_async_rejects_localhost():
    r = client.post("/analyze/async", json={"url": "http://localhost:8000/"})
    assert r.status_code == 400


def test_analyze_rejects_bad_scheme():
    r = client.post("/analyze", json={"url": "ftp://example.com/x"})
    # Pydantic HttpUrl rejects at validation (422) before our guard
    assert r.status_code in (400, 422)


class TestAuth:
    @pytest.fixture(autouse=True)
    def _enable_auth(self, monkeypatch):
        monkeypatch.setattr(settings, "API_AUTH_KEY", "secret-key")

    def test_missing_key_is_401(self):
        r = client.post("/analyze/async", json={"url": "https://example.com/p"})
        assert r.status_code == 401

    def test_wrong_key_is_401(self):
        r = client.post(
            "/analyze/async",
            json={"url": "https://example.com/p"},
            headers={"X-API-Key": "nope"},
        )
        assert r.status_code == 401

    def test_health_stays_open(self):
        assert client.get("/health").status_code == 200
