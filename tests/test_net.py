"""Unit tests for URL normalization and SSRF validation."""

import pytest

from utils.net import normalize_url, validate_public_url, UnsafeURLError


class TestNormalizeUrl:
    def test_strips_utm_params(self):
        assert (
            normalize_url("https://shop.com/p/widget?utm_source=x&utm_campaign=y&size=m")
            == "https://shop.com/p/widget?size=m"
        )

    def test_strips_click_ids(self):
        assert normalize_url("https://shop.com/p?fbclid=abc&gclid=def") == "https://shop.com/p"

    def test_strips_fragment_and_trailing_slash(self):
        assert normalize_url("https://Shop.com/p/widget/#reviews") == "https://shop.com/p/widget"

    def test_keeps_meaningful_query(self):
        assert normalize_url("https://shop.com/p?variant=123") == "https://shop.com/p?variant=123"

    def test_removes_default_port(self):
        assert normalize_url("https://shop.com:443/p") == "https://shop.com/p"
        assert normalize_url("http://shop.com:8080/p") == "http://shop.com:8080/p"

    def test_bare_domain_gets_root_path(self):
        assert normalize_url("https://shop.com") == "https://shop.com/"

    def test_same_page_different_tracking_normalizes_identically(self):
        a = normalize_url("https://shop.com/p/x?utm_source=chat&ref=tw")
        b = normalize_url("https://shop.com/p/x")
        assert a == b


class TestValidatePublicUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1/admin",
            "https://localhost/x",
            "http://10.0.0.5/",
            "http://192.168.1.1/router",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://0.0.0.0/",
            "ftp://example.com/file",
            "http://foo.internal/",
        ],
    )
    def test_rejects_internal_targets(self, url):
        with pytest.raises(UnsafeURLError):
            validate_public_url(url)

    def test_accepts_public_ip_literal(self):
        validate_public_url("https://1.1.1.1/")

    def test_rejects_missing_host(self):
        with pytest.raises(UnsafeURLError):
            validate_public_url("https:///path-only")
