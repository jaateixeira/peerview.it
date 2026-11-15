"""One site, several addresses (ADR 0021): an alias sends people to the main address."""

from fastapi.testclient import TestClient

from tests.integration.web_fakes import make_harness

MAIN = "https://peerview.example"
ALIAS = "https://peereview.example"


def at(host: str) -> TestClient:
    h = make_harness(base_url=MAIN, aliases=(ALIAS, "https://www.peerview.example"))
    return TestClient(h.app, base_url=f"https://{host}", follow_redirects=False)


def test_an_alias_sends_the_visitor_to_the_same_page_at_the_main_address():
    r = at("peereview.example").get("/login?next=%2Freview%2Fnew&x=a+b")
    assert r.status_code == 308
    assert r.headers["location"] == "https://peerview.example/login?next=%2Freview%2Fnew&x=a+b"
    assert at("WWW.peerview.example").get("/").headers["location"] == "https://peerview.example/"


def test_a_personal_link_survives_the_move_and_is_not_leaked():
    r = at("peereview.example").get("/i/SECRET-token_1")
    assert r.headers["location"] == "https://peerview.example/i/SECRET-token_1"
    assert r.headers["referrer-policy"] == "same-origin"


def test_the_main_address_is_served_as_usual():
    r = at("peerview.example").get("/")
    assert r.status_code == 200 and "peerview.example" in r.text


def test_other_hosts_are_not_redirected():
    # The health check on 127.0.0.1 and names nobody configured are left alone.
    assert at("127.0.0.1:8000").get("/healthz").text == "ok"
    assert at("elsewhere.example").get("/").status_code == 200


def test_the_path_cannot_point_the_redirect_at_another_site():
    r = at("peereview.example").get("//evil.example/x")
    assert r.headers["location"].startswith("https://peerview.example/")


def test_a_form_sent_to_an_alias_is_moved_too_not_processed():
    r = at("peereview.example").post("/login", data={"email": "a@x.fi", "password": "p"})
    assert r.status_code == 308 and r.headers["location"] == "https://peerview.example/login"


def test_without_aliases_nothing_changes():
    h = make_harness(base_url=MAIN)
    client = TestClient(h.app, base_url=ALIAS, follow_redirects=False)
    assert client.get("/").status_code == 200
