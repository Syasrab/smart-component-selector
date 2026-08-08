import os
import re
import time
import requests

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

_cached_token = None
_cached_token_expiry = 0  # unix timestamp

# Words/phrases that signal a dev board, breakout board, or eval kit rather
# than a bare component. A recruiter looking at the output should see real
# ICs/parts, not hobbyist boards, unless the requirement explicitly wants one.
DEV_BOARD_KEYWORDS = [
    "breakout", "eval board", "evaluation board", "evaluation kit", "evkit",
    "development board", "devboard", "dev board", "feather", "shield",
    "stemma", "qwiic", "click board", "boosterpack", "arduino shield",
    "carrier board", "pmod", "reference design kit", "demo board",
]

# A token that looks like a specific manufacturer part number (mix of
# letters and digits, at least 4 characters) rather than a generic
# descriptive word. Used to broaden an over-specific search keyword.
_PART_NUMBER_TOKEN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9\-]{4,}$")


def _request_with_retry(method, url, max_retries=4, **kwargs):
    """Wrap a requests call with exponential backoff on 429/5xx responses."""
    response = None
    for attempt in range(max_retries):
        response = method(url, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == max_retries - 1:
                response.raise_for_status()
            wait = 2 ** attempt
            print(f"  DigiKey busy/rate-limited (HTTP {response.status_code}), retrying in {wait}s...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    return response


def get_access_token():
    """2-legged OAuth2 (client_credentials) - no browser login needed.
    Access tokens expire in ~10 minutes, so we cache and refresh automatically."""
    global _cached_token, _cached_token_expiry

    if _cached_token and time.time() < _cached_token_expiry - 30:
        return _cached_token

    client_id = os.environ.get("DIGIKEY_CLIENT_ID")
    client_secret = os.environ.get("DIGIKEY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Set DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET in your environment.")

    response = _request_with_retry(
        requests.post,
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    payload = response.json()

    _cached_token = payload["access_token"]
    _cached_token_expiry = time.time() + payload.get("expires_in", 600)
    return _cached_token


def is_dev_board(description="", series_name=""):
    """Best-effort heuristic: does this look like a breakout/dev/eval board
    rather than a bare component?"""
    text = f"{description or ''} {series_name or ''}".lower()
    return any(keyword in text for keyword in DEV_BOARD_KEYWORDS)


def broaden_keyword(keyword):
    """Strip tokens that look like specific manufacturer part numbers,
    leaving the generic descriptive words behind. Used as a fallback when
    an overly specific keyword returns zero results.
    e.g. 'MCP73871 solar charge controller' -> 'solar charge controller'
    """
    tokens = keyword.split()
    kept = [t for t in tokens if not _PART_NUMBER_TOKEN.match(t)]
    broadened = " ".join(kept).strip()
    return broadened


def search_by_keyword(keyword, record_count=10, filter_dev_boards=True):
    """Search DigiKey's catalog by keyword (e.g. 'PIR motion sensor', 'nRF52832').
    Returns a list of simplified dicts: mpn, manufacturer, description, price_usd,
    quantity_available, datasheet_url, parameters (dict of spec name -> value),
    series, is_dev_board.

    By default, results that look like breakout/dev/eval boards are filtered
    out so the BOM stays focused on bare, production-ready components. If
    filtering would remove every result, the unfiltered list is returned
    instead (better to show something than nothing)."""
    client_id = os.environ.get("DIGIKEY_CLIENT_ID")
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": client_id,
        "X-DIGIKEY-Locale-Site": "US",
        "X-DIGIKEY-Locale-Language": "en",
        "X-DIGIKEY-Locale-Currency": "USD",
        "Content-Type": "application/json",
    }

    body = {
        "Keywords": keyword,
        "Limit": record_count,
        "Offset": 0,
    }

    response = _request_with_retry(requests.post, SEARCH_URL, headers=headers, json=body)
    data = response.json()

    results = []
    for product in data.get("Products", []):
        parameters = {
            p.get("ParameterText"): p.get("ValueText")
            for p in product.get("Parameters", [])
        }
        price = None
        pricing = product.get("ProductVariations", [])
        if pricing:
            price_breaks = pricing[0].get("StandardPricing", [])
            if price_breaks:
                price = price_breaks[0].get("UnitPrice")

        description = (product.get("Description") or {}).get("ProductDescription")
        series_name = (product.get("Series") or {}).get("Name")

        results.append({
            "mpn": product.get("ManufacturerProductNumber"),
            "manufacturer": (product.get("Manufacturer") or {}).get("Name"),
            "description": description,
            "price_usd": price,
            "quantity_available": product.get("QuantityAvailable"),
            "datasheet_url": product.get("DatasheetUrl"),
            "parameters": parameters,
            "series": series_name,
            "is_dev_board": is_dev_board(description, series_name),
        })

    if filter_dev_boards:
        filtered = [r for r in results if not r["is_dev_board"]]
        if filtered:
            excluded = len(results) - len(filtered)
            if excluded:
                print(f"  (filtered out {excluded} dev board/breakout result(s))")
            return filtered
        # Everything looked like a dev board - better to surface them than
        # return nothing, but they're still flagged via is_dev_board=True.
        return results

    return results


if __name__ == "__main__":
    # Quick smoke test - run this file directly to confirm your credentials work.
    results = search_by_keyword("nRF52832", record_count=3)
    for r in results:
        print(f"{r['mpn']} | {r['manufacturer']} | ${r['price_usd']} | dev_board={r['is_dev_board']}")