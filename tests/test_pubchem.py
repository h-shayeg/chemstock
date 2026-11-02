import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from chemstock.ghs import GhsStatus
from chemstock.pubchem import (
    PubChemClient,
    PubChemUnavailable,
    urllib_transport,
)

DATA = Path(__file__).parent / "data"
BASE = "https://pubchem.example/rest"
NOT_FOUND = json.dumps({"Fault": {"Code": "PUGREST.NotFound"}}).encode()


def cid_url(cas: str) -> str:
    return f"{BASE}/pug/compound/name/{cas}/cids/JSON"


def ghs_url(cid: int) -> str:
    return f"{BASE}/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification"


def cids(*numbers: int) -> bytes:
    return json.dumps({"IdentifierList": {"CID": list(numbers)}}).encode()


class FakeTransport:
    """Answers from a table, and remembers which URLs were asked for."""

    def __init__(self, answers: dict[str, tuple[int, bytes]]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, bytes]:
        self.calls.append(url)
        return self.answers.get(url, (404, NOT_FOUND))


def client(answers: dict[str, tuple[int, bytes]]) -> PubChemClient:
    return PubChemClient(FakeTransport(answers), base_url=BASE)


ACETONE = {
    cid_url("67-64-1"): (200, cids(180)),
    ghs_url(180): (200, (DATA / "pubchem_acetone_ghs.json").read_bytes()),
}


def test_a_classified_chemical() -> None:
    transport = FakeTransport(ACETONE)

    result = PubChemClient(transport, base_url=BASE).lookup_ghs("67-64-1")

    assert result.status is GhsStatus.CLASSIFIED
    assert result.cid == 180
    assert result.data is not None
    assert [s.code for s in result.data.hazard_statements] == ["H225", "H319", "H336"]
    assert transport.calls == [cid_url("67-64-1"), ghs_url(180)]


def test_a_chemical_without_hazards() -> None:
    result = client(
        {
            cid_url("57-50-1"): (200, cids(5988, 12345)),  # the first CID is used
            ghs_url(5988): (200, (DATA / "pubchem_sucrose_ghs.json").read_bytes()),
        }
    ).lookup_ghs("57-50-1")

    assert result.status is GhsStatus.NOT_CLASSIFIED
    assert result.cid == 5988


def test_an_unknown_cas_number_needs_one_request_only() -> None:
    transport = FakeTransport({})

    result = PubChemClient(transport, base_url=BASE).lookup_ghs("9999-99-9")

    assert (result.status, result.cid, result.data) == (GhsStatus.NOT_FOUND, None, None)
    assert transport.calls == [cid_url("9999-99-9")]


def test_an_empty_cid_list_means_not_found() -> None:
    result = client({cid_url("50-00-0"): (200, cids())}).lookup_ghs("50-00-0")

    assert result.status is GhsStatus.NOT_FOUND


def test_a_compound_without_ghs_section_has_no_data() -> None:
    result = client({cid_url("50-00-0"): (200, cids(712))}).lookup_ghs("50-00-0")

    assert (result.status, result.cid, result.data) == (GhsStatus.NO_DATA, 712, None)


def test_an_empty_ghs_answer_has_no_data() -> None:
    empty = json.dumps({"Record": {"RecordNumber": 712}}).encode()
    answers = {cid_url("50-00-0"): (200, cids(712)), ghs_url(712): (200, empty)}

    result = client(answers).lookup_ghs("50-00-0")

    assert result.status is GhsStatus.NO_DATA


@pytest.mark.parametrize(
    "answer",
    [
        (503, b'{"Fault": {"Code": "PUGREST.ServerBusy"}}'),
        (500, b""),
        (200, b"<html>maintenance</html>"),
        (200, b"[1, 2, 3]"),
        (200, b"x" * 5_000_001),
    ],
    ids=["busy", "server error", "not json", "not an object", "too large"],
)
def test_bad_answers_mean_pubchem_is_unavailable(answer: tuple[int, bytes]) -> None:
    with pytest.raises(PubChemUnavailable):
        client({cid_url("67-64-1"): answer}).lookup_ghs("67-64-1")


def test_a_network_error_means_pubchem_is_unavailable() -> None:
    def broken(url: str) -> tuple[int, bytes]:
        raise OSError("connection refused")

    with pytest.raises(PubChemUnavailable, match="not reachable"):
        PubChemClient(broken, base_url=BASE).lookup_ghs("67-64-1")


def test_a_trailing_slash_in_the_base_url_is_ignored() -> None:
    transport = FakeTransport(ACETONE)

    PubChemClient(transport, base_url=BASE + "/").lookup_ghs("67-64-1")

    assert transport.calls[0] == cid_url("67-64-1")


# --- the real transport, against a tiny local web server ---------------------


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (name required by http.server)
        found = self.path == "/found"
        body = b'{"ok": true}' if found else NOT_FOUND
        self.send_response(200 if found else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.server.user_agent = self.headers["User-Agent"]  # type: ignore[attr-defined]

    def log_message(self, *args: object) -> None:  # keep the test output clean
        pass


@pytest.fixture(autouse=True)
def _no_proxy_for_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    # A proxy set on the machine (for example for PubChem) must not catch the
    # requests to the local test server.
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")


@pytest.fixture
def local_server() -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_urllib_transport_returns_status_and_body(
    local_server: ThreadingHTTPServer,
) -> None:
    fetch = urllib_transport(timeout=5)
    base = f"http://127.0.0.1:{local_server.server_address[1]}"

    assert fetch(f"{base}/found") == (200, b'{"ok": true}')
    assert fetch(f"{base}/missing") == (404, NOT_FOUND)
    assert "chemstock" in local_server.user_agent  # type: ignore[attr-defined]


def test_urllib_transport_raises_os_error_when_nothing_listens() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    server.server_close()  # the port is free now: nobody answers

    with pytest.raises(OSError):
        urllib_transport(timeout=5)(f"http://127.0.0.1:{port}/found")
