import json
import os
import urllib.request
from datetime import date
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import ConnectionError as CffiConnectionError, HTTPError as CffiHTTPError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

BOT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

DEFAULT_HEADERS = {
    "User-Agent": BOT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-SG,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def make_client() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.timeout = 30
    session.impersonate = "chrome136"
    return session


# --- Jina Reader fallback ---

_jina_keys: list[str] = []
_jina_key_idx: int = 0


def _next_jina_key() -> str | None:
    """Round-robin over keys from JINA_API_KEYS (comma-separated) or JINA_API_KEY."""
    global _jina_keys, _jina_key_idx
    if not _jina_keys:
        raw = os.environ.get("JINA_API_KEYS") or os.environ.get("JINA_API_KEY") or ""
        _jina_keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not _jina_keys:
        return None
    key = _jina_keys[_jina_key_idx % len(_jina_keys)]
    _jina_key_idx += 1
    return key


class _JinaResponse:
    """Minimal Response-like wrapper around a Jina Reader result."""

    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> dict:
        return json.loads(self._text)


def fetch_jina(url: str, api_key: str | None = None) -> _JinaResponse:
    """Fetch URL via Jina Reader (r.jina.ai), returning an HTML response wrapper."""
    jina_url = f"https://r.jina.ai/{url}"
    headers: dict[str, str] = {"X-Return-Format": "html", "Accept": "text/html"}
    key = api_key or _next_jina_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(jina_url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return _JinaResponse(resp.read().decode("utf-8"))


# --- Plain urllib fetch ---

def fetch_plain(url: str, headers: dict | None = None) -> str:
    """Fetch URL with stdlib urllib — avoids curl_cffi TLS fingerprint that some sites block."""
    req_headers = {"User-Agent": BOT_UA, "Accept-Language": "en-SG,en;q=0.9"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def write_dataset(path: Path, data: list | dict) -> None:
    """Write data to path, a dated archive, and a -latest copy."""
    today = date.today().strftime("%Y-%m-%d")
    content = json.dumps(data, indent=2, ensure_ascii=False)
    dated = path.parent / f"{path.stem}-{today}.json"
    latest = path.parent / f"{path.stem}-latest.json"
    for p in (dated, latest):
        p.write_text(content)


@retry(
    retry=retry_if_exception_type((CffiHTTPError, CffiConnectionError)),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)
def fetch(session: requests.Session, url: str, *, jina_fallback: bool = True) -> requests.Response | _JinaResponse:
    try:
        resp = session.get(url)
        resp.raise_for_status()
        return resp
    except CffiHTTPError as exc:
        if jina_fallback and exc.response is not None and exc.response.status_code == 403:
            print(f"[jina fallback] 403 on {url}")
            return fetch_jina(url)
        raise
