import json
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
    session.impersonate = "chrome131"
    return session


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
def fetch(session: requests.Session, url: str) -> requests.Response:
    resp = session.get(url)
    resp.raise_for_status()
    return resp
