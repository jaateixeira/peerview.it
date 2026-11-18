import os
import socket
import threading
import time

import pytest
import uvicorn
from tests.unit.test_webpage_plugin import FakePageChecker

import previewit.bootstrap as bootstrap
from previewit.application.web_pages import PageCheck
from previewit.bootstrap import create_app


class Outbox:
    """Captures verification mails so scenarios can open the link."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))

    def link_for(self, email: str) -> str:
        body = next(b for to, _, b in reversed(self.sent) if to == email)
        return next(w for w in body.split() if "/verify?token=" in w)


OUTBOX = Outbox()

# Web pages the scenarios review (ADR 0022): the test server never leaves this machine.
PAGES = FakePageChecker(
    {
        "https://example.org/portfolio": PageCheck(
            "https://example.org/portfolio",
            "https://example.org/portfolio",
            "Maya's design portfolio",
            "Six projects from 2026.",
            "Maya Maker",
            "text/html",
        ),
        "https://example.org/private": "The page asks for a login. Reviewers need a page anyone "
        "can open: use a public address.",
    }
)


@pytest.fixture(scope="session")
def outbox() -> Outbox:
    return OUTBOX


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    bootstrap.build_mailer = lambda _settings: OUTBOX  # type: ignore[assignment]
    bootstrap.build_page_checker = lambda _settings: PAGES  # type: ignore[assignment]
    # The app checks the Origin header of form posts against its own base URL.
    os.environ["PREVIEWIT_BASE_URL"] = f"http://127.0.0.1:{port}"
    # The same server under a second name, to show that an alias leads to the main address.
    os.environ["PREVIEWIT_ALIASES"] = f"http://localhost:{port}"
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        pytest.fail("test server did not start within 5 seconds")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
