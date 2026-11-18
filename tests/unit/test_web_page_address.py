"""The address of a web page to review (ADR 0022): the rules need no network."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from previewit.application.web_pages import PageUnreachable, normalise_address


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("https://example.org/essay", "https://example.org/essay"),
        ("  HTTPS://Example.ORG/Essay?x=1#part-2 ", "https://example.org/Essay?x=1#part-2"),
        ("example.org/essay", "https://example.org/essay"),  # people paste without the scheme
        ("http://example.org", "http://example.org/"),
        ("https://example.org:443/a", "https://example.org/a"),
        ("http://example.org:80/a", "http://example.org/a"),
        ("https://bücher.example/kapitel", "https://xn--bcher-kva.example/kapitel"),
        ("https://93.184.216.34/page", "https://93.184.216.34/page"),
        ("https://[2606:4700::6810:85e5]/page", "https://[2606:4700::6810:85e5]/page"),
    ],
)
def test_an_address_is_tidied(typed, expected):
    assert normalise_address(typed) == expected


@pytest.mark.parametrize(
    ("typed", "reason"),
    [
        ("", "Paste the address of the web page."),
        ("   ", "Paste the address of the web page."),
        ("ftp://example.org/file", "starts with https://"),
        ("javascript:alert(1)", "starts with https://"),
        ("file:///etc/passwd", "starts with https://"),
        ("https://user:secret@example.org/", "Leave the user name and password out"),
        ("https://localhost/admin", "not on the public internet"),
        ("https://intranet/", "not on the public internet"),
        ("https://printer.local/", "not on the public internet"),
        ("https://db.internal/", "not on the public internet"),
        ("https://router.home.arpa/", "not on the public internet"),
        ("http://127.0.0.1/", "not on the public internet"),
        ("http://10.0.0.8/", "not on the public internet"),
        ("http://169.254.169.254/latest/meta-data/", "not on the public internet"),
        ("http://[::1]/", "not on the public internet"),
        ("http://[::ffff:127.0.0.1]/", "not on the public internet"),
        ("http://100.64.0.1/", "not on the public internet"),
        ("https://example.org:8443/", "usual ports"),
        ("https://example.org:22/", "usual ports"),
        ("https://example.org:99999/", "cannot read"),
        ("https:///no-host", "cannot read"),
        ("https://exa mple.org/", "cannot read"),
        ("https://example.org/" + "a" * 2100, "too long"),
    ],
)
def test_an_address_reviewers_cannot_open_is_refused(typed, reason):
    with pytest.raises(PageUnreachable) as refused:
        normalise_address(typed)
    assert reason in str(refused.value)


_LABEL = st.from_regex(r"[a-z][a-z0-9-]{0,10}[a-z0-9]", fullmatch=True)


@given(
    host=st.lists(_LABEL, min_size=2, max_size=3).map(".".join),
    path=st.from_regex(r"(/[A-Za-z0-9._~-]{0,8}){0,3}", fullmatch=True),
    scheme=st.sampled_from(["http", "https", "HTTPS", ""]),
)
def test_tidying_twice_changes_nothing_and_keeps_the_web(host, path, scheme):
    typed = f"{scheme}://{host}{path}" if scheme else f"{host}{path}"
    once = normalise_address(typed)
    assert normalise_address(once) == once
    assert once.startswith(("https://", "http://"))
