"""Regression tests for review-flagged URL edge cases."""

from utils.net import normalize_url


def test_ipv6_literal_stays_bracketed():
    # Bug: brackets were stripped, producing an invalid host that broke
    # downstream SSRF validation.
    assert normalize_url("http://[2606:4700::1]/p") == "http://[2606:4700::1]/p"


def test_ipv6_with_port_preserved():
    assert normalize_url("http://[2606:4700::1]:8080/p") == "http://[2606:4700::1]:8080/p"


def test_malformed_port_does_not_raise():
    # Previously raised an unhandled ValueError from parts.port
    out = normalize_url("http://example.com:notaport/p")
    assert out.startswith("http://example.com")
