"""Gemensam HTTP-klient med timeout och omförsök."""
from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

log = logging.getLogger(__name__)

_session: requests.Session | None = None


class HamtningsFel(Exception):
    """En källa gick inte att hämta eller gav oväntat svar."""


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers["User-Agent"] = config.USER_AGENT
        retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",))
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def hamta_json(url: str, params: dict | None = None, tillat_404: bool = False):
    """GET och tolka JSON. Returnerar (data, response). Vid 404 och tillat_404: (None, response)."""
    t0 = time.monotonic()
    try:
        r = session().get(url, params=params, timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise HamtningsFel(f"Nätverksfel mot {url}: {e}") from e
    log.debug("GET %s -> %s (%.1fs)", url, r.status_code, time.monotonic() - t0)
    if r.status_code == 404 and tillat_404:
        return None, r
    if r.status_code != 200:
        raise HamtningsFel(f"{url} svarade {r.status_code}: {r.text[:200]}")
    try:
        return r.json(), r
    except ValueError as e:
        raise HamtningsFel(f"{url} gav inte giltig JSON") from e
