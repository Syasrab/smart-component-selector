import os
import time
import requests

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

_cached_token = None
_cached_token_expiry = 0  # unix timestamp


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

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    response.raise_for_status()
    payload = response.json()

    _cached_token = payload["access_token"]
    _cached_token_expiry = time.time() + payload.get("expires_in", 600)
    return _cached_token


def search_by_keyword(keyword, record_count=10):
    """Search DigiKey's catalog by keyword (e.g. 'PIR motion sensor', 'nRF52832').
    Returns a list of simplified dicts: mpn, manufacturer, description, price_usd,
    quantity_available, datasheet_url, parameters (dict of spec name -> value)."""
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

    response = requests.post(SEARCH_URL, headers=headers, json=body)
    response.raise_for_status()
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

        results.append({
            "mpn": product.get("ManufacturerProductNumber"),
            "manufacturer": (product.get("Manufacturer") or {}).get("Name"),
            "description": (product.get("Description") or {}).get("ProductDescription"),
            "price_usd": price,
            "quantity_available": product.get("QuantityAvailable"),
            "datasheet_url": product.get("DatasheetUrl"),
            "parameters": parameters,
        })

    return results


if __name__ == "__main__":
    # Quick smoke test - run this file directly to confirm your credentials work.
    results = search_by_keyword("nRF52832", record_count=3)
    for r in results:
        print(f"{r['mpn']} | {r['manufacturer']} | ${r['price_usd']}")