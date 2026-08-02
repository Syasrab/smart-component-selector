import json
import os
from google import genai
from google.genai import types

from main import init_db, get_candidates, rank_rows

MODEL = "gemini-3.6-flash"  # free-tier model

SYSTEM_PROMPT = """You convert plain-English microcontroller requirements into JSON for querying a \
SQLite database. The database table "microcontrollers" has these columns: name, family, core, \
clock_mhz, flash_kb, ram_kb, voltage, digital_io, adc_bit, has_wifi, has_bluetooth, price_usd, \
in_stock, stop_current_ua.

Return ONLY valid JSON (no markdown fences, no commentary) matching exactly this shape:
{
  "filters": {
    "min_flash_kb": number,
    "min_ram_kb": number,
    "min_io": number,
    "needs_wifi": boolean,
    "needs_bluetooth": boolean,
    "max_price_usd": number or null
  },
  "weights": {
    "price_usd": number,
    "digital_io": number,
    "flash_kb": number,
    "stop_current_ua": number
  },
  "unsupported_requirements": ["short phrase", ...],
  "notes": "one sentence explaining filter/weight choices"
}

Rules:
- filters are HARD cutoffs: only set a filter when the user gave a specific minimum/maximum. \
Otherwise use 0 for minimums, false for booleans, null for max_price_usd.
- weights are SOFT priorities used to rank the chips that already passed the filters. \
Negative weight = minimize that column (e.g. price, stop_current_ua). Positive weight = \
maximize it (e.g. digital_io, flash_kb). Infer weight magnitude from emphasis words like \
"cheap", "cost-sensitive", "low power", "as much memory as possible". If the user gives no \
signal for a column, set its weight to 0.
- If the user mentions a requirement this schema/database has no column for (PWM channel \
count, ADC channel count, package/footprint size, BLE OTA DFU, toolchain), do NOT invent a \
filter for it. Instead add a short phrase describing it to "unsupported_requirements".
"""


def ai_parse_requirements(prompt_text, client=None):
    client = client or genai.Client()  # reads GEMINI_API_KEY from env by default
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text.strip())


def run_selector(prompt_text, client=None):
    init_db()
    parsed = ai_parse_requirements(prompt_text, client=client)

    filters = parsed["filters"]
    weights = parsed["weights"]

    rows = get_candidates(**filters)
    ranked = rank_rows(rows, weights=weights)

    print(f"Interpreted requirements: {parsed['notes']}")
    if parsed.get("unsupported_requirements"):
        print("Not filterable yet (missing DB columns): " + ", ".join(parsed["unsupported_requirements"]))

    print(f"\n{len(rows)} chips meet the hard requirements:")
    for row, score in ranked:
        print(f"  {row['name']}: score={score:.2f}, price=${row['price_usd']}, "
              f"flash={row['flash_kb']}KB, ram={row['ram_kb']}KB, io={row['digital_io']}")

    return ranked


if __name__ == "__main__":
    example_prompt = (
        "I need a low-power 32-bit MCU, at least 4 digital IO pins, "
        "keep it as cheap as possible, no wifi or bluetooth needed."
    )
    if not os.environ.get("GEMINI_API_KEY"):
        print("Set GEMINI_API_KEY in your environment before running this file.")
    else:
        run_selector(example_prompt)