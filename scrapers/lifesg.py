"""
Scrapes the LifeSG preschool search using Playwright to intercept API calls.
robots.txt: only /app-security and /digital-services/ are blocked; preschool-search is open.
Strategy: navigate to the search page, capture the XHR/fetch calls, then paginate directly.
Output: data/lifesg_preschools.json
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, Route, Request

OUT_PATH = Path("data/lifesg_preschools.json")
SEARCH_URL = "https://www.life.gov.sg/services-tools/preschool-search"


async def discover_api(headless: bool = True) -> dict:
    """Navigate to LifeSG preschool search and capture the first API call."""
    captured: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-SG",
        )
        page = await context.new_page()

        async def handle_response(response):
            url = response.url
            # Capture JSON responses that look like search/listing APIs
            if (
                "api" in url.lower() or "preschool" in url.lower() or "search" in url.lower() or "centre" in url.lower()
            ) and "life.gov.sg" in url:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        body = await response.json()
                        captured.append({"url": url, "status": response.status, "body": body})
                        print(f"[API] Captured: {url}")
                except Exception as e:
                    print(f"[API] Failed to parse {url}: {e}")

        page.on("response", handle_response)

        print(f"Navigating to {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)  # wait for SPA to hydrate and fire initial XHR

        # Accept any consent dialogs
        try:
            consent_btn = page.locator("button:has-text('Accept'), button:has-text('Agree'), button:has-text('Continue'), button:has-text('OK')")
            if await consent_btn.count() > 0:
                await consent_btn.first.click()
                await page.wait_for_timeout(3000)
        except Exception:
            pass

        # Scroll down to trigger lazy-loaded content
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(5000)
        await browser.close()

    return {"captured": captured}


async def run_api_direct(api_url: str, params: dict) -> list[dict]:
    """Once we have the API URL, fetch all pages directly."""
    import httpx
    from scrapers.utils import make_client

    results = []
    client = make_client()

    page_num = 1
    while True:
        p = {**params, "page": page_num, "pageSize": 50}
        resp = client.get(api_url, params=p)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("data", data.get("results", data.get("items", [])))
        if not items:
            break
        results.extend(items)
        print(f"Page {page_num}: got {len(items)} items (total so far: {len(results)})")

        total = data.get("total", data.get("totalCount", data.get("count", None)))
        if total and len(results) >= total:
            break
        if len(items) < p["pageSize"]:
            break
        page_num += 1

    return results


async def main():
    OUT_PATH.parent.mkdir(exist_ok=True)

    print("Step 1: Discovering API endpoints via browser...")
    result = await discover_api()

    captured = result["captured"]
    if not captured:
        print("No API calls captured. Saving browser discovery result for manual inspection.")
        OUT_PATH.with_suffix(".discovery.json").write_text(
            json.dumps(result, indent=2, default=str)
        )
        return

    print(f"\nCaptured {len(captured)} API calls:")
    for c in captured:
        print(f"  {c['status']} {c['url']}")

    # Save discovery for inspection
    OUT_PATH.with_suffix(".discovery.json").write_text(
        json.dumps(captured, indent=2, default=str)
    )
    print(f"\nDiscovery saved to {OUT_PATH.with_suffix('.discovery.json')}")


if __name__ == "__main__":
    asyncio.run(main())
