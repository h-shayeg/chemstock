"""Download GHS hazard data for a CAS number from PubChem.

Two requests, both public and free (PubChem asks for at most 5 per second):

1. PUG REST: the compound id (CID) that belongs to the CAS number.
2. PUG View: the "GHS Classification" section of that compound.

The network part is a small function (``Transport``) so tests can replace it
and never touch the internet.
"""

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chemstock.config import get_settings
from chemstock.ghs import GhsData, GhsStatus, parse_ghs

DEFAULT_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest"
MAX_RESPONSE_BYTES = 5_000_000  # a GHS record is well under 1 MB
USER_AGENT = "chemstock (+https://github.com/h-shayeg/chemstock)"

# Takes a URL, returns (HTTP status, body). Raises OSError if the server
# cannot be reached at all.
Transport = Callable[[str], tuple[int, bytes]]


class PubChemUnavailable(Exception):
    """PubChem could not be reached or gave an unexpected answer. Try later."""


@dataclass(frozen=True)
class GhsLookup:
    status: GhsStatus
    cid: int | None
    data: GhsData | None


def urllib_transport(timeout: float) -> Transport:
    """The real network access, with the standard library only."""

    def fetch(url: str) -> tuple[int, bytes]:
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            try:
                return error.code, error.read(MAX_RESPONSE_BYTES + 1)
            finally:
                error.close()

    return fetch


class PubChemClient:
    def __init__(self, transport: Transport, base_url: str = DEFAULT_BASE_URL):
        self._transport = transport
        self._base_url = base_url.rstrip("/")

    def _get_json(self, url: str) -> dict[str, Any] | None:
        """The JSON answer, or None for "not found" (HTTP 404)."""
        try:
            status, body = self._transport(url)
        except (OSError, http.client.HTTPException) as error:
            raise PubChemUnavailable(f"PubChem is not reachable: {error}") from None
        if status == 404:
            return None
        if status != 200:
            raise PubChemUnavailable(f"PubChem answered with HTTP {status}")
        if len(body) > MAX_RESPONSE_BYTES:
            raise PubChemUnavailable("PubChem's answer was unexpectedly large")
        try:
            data = json.loads(body)
        except ValueError:
            raise PubChemUnavailable("PubChem's answer was not valid JSON") from None
        if not isinstance(data, dict):
            raise PubChemUnavailable("PubChem's answer had an unexpected shape")
        return data

    def find_cid(self, cas_number: str) -> int | None:
        """The PubChem compound id for a CAS number (the best match), or None."""
        name = urllib.parse.quote(cas_number, safe="")
        data = self._get_json(f"{self._base_url}/pug/compound/name/{name}/cids/JSON")
        if data is None:
            return None
        cids = data.get("IdentifierList", {}).get("CID", [])
        if not cids or not isinstance(cids[0], int) or cids[0] <= 0:
            return None
        return cids[0]

    def lookup_ghs(self, cas_number: str) -> GhsLookup:
        """Everything PubChem says about the GHS classification of a CAS number."""
        cid = self.find_cid(cas_number)
        if cid is None:
            return GhsLookup(GhsStatus.NOT_FOUND, None, None)
        record = self._get_json(
            f"{self._base_url}/pug_view/data/compound/{cid}/JSON"
            "?heading=GHS+Classification"
        )
        if record is None:
            return GhsLookup(GhsStatus.NO_DATA, cid, None)
        data = parse_ghs(record)
        if data.hazard_statements:
            status = GhsStatus.CLASSIFIED
        elif data.reported:
            status = GhsStatus.NOT_CLASSIFIED
        else:
            status = GhsStatus.NO_DATA
        return GhsLookup(status, cid, data)


def get_pubchem_client() -> PubChemClient:
    """FastAPI dependency: the real client. Tests replace it with a fake one."""
    settings = get_settings()
    return PubChemClient(
        urllib_transport(settings.pubchem_timeout_seconds), settings.pubchem_base_url
    )
