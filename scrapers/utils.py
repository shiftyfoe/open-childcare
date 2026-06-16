import json
from datetime import date
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

BOT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

DEFAULT_HEADERS = {
    "User-Agent": BOT_UA,
    "Accept-Language": "en-SG,en;q=0.9",
}


def make_client() -> httpx.Client:
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30,
    )


def write_dataset(path: Path, data: list | dict) -> None:
    """Write data to path, a dated archive, and a -latest copy."""
    today = date.today().strftime("%Y-%m-%d")
    content = json.dumps(data, indent=2, ensure_ascii=False)
    dated = path.parent / f"{path.stem}-{today}.json"
    latest = path.parent / f"{path.stem}-latest.json"
    for p in (dated, latest):
        p.write_text(content)


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)
def fetch(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.get(url)
    resp.raise_for_status()
    return resp
