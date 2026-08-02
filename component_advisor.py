import json
import time
from google import genai
from google.genai import types
from google.genai import errors

from components_db import get_components_by_category, get_categories

MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = """You are a hardware component selection advisor. You will be given a \
component requirement description and a list of real, currently available candidate parts \
(with manufacturer, price, stock, and parametric specs from a distributor).

Pick the best 2-3 candidates for the requirement. Return ONLY valid JSON (no markdown \
fences, no commentary) matching exactly this shape:
{
  "picks": [
    {"mpn": "string", "reason": "one sentence on why this is a strong fit"},
    ...
  ],
  "tradeoffs": "2-3 sentences comparing the picks against each other - what you gain and \
give up choosing one over another (price vs power, stock vs specs, etc.)",
  "concerns": "one sentence flagging anything the requirement needs that none of the \
candidates clearly satisfy, or empty string if none"
}

Only pick from the candidates given. Do not invent parts or specs not shown to you."""


def advise_category(category_info, client=None, max_retries=3):
    """category_info: dict with keys category, search_keyword, requirement (from get_categories())."""
    client = client or genai.Client()
    rows = get_components_by_category(category_info["category"])
    if not rows:
        return {"picks": [], "tradeoffs": "", "concerns": "No candidates found in database."}

    candidates_text = "\n".join(
        f"- {row['mpn']} ({row['manufacturer']}): ${row['price_usd']}, "
        f"stock={row['quantity_available']}, specs={row['parameters']}"
        for row in rows
    )
    prompt = f"Requirement:\n{category_info['requirement']}\n\nCandidates:\n{candidates_text}"

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
            return json.loads(response.text.strip())
        except errors.ServerError:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  Gemini is busy, retrying in {wait}s...")
            time.sleep(wait)


def advise_all(client=None):
    """Reads whatever categories were saved by the last populate step and advises on each."""
    categories = get_categories()
    report = {}
    for category_info in categories:
        print(f"Analyzing category: {category_info['category']}...")
        report[category_info["category"]] = advise_category(category_info, client=client)
    return report


def print_report(report):
    for category, result in report.items():
        print(f"\n=== {category} ===")
        for pick in result.get("picks", []):
            print(f"  - {pick['mpn']}: {pick['reason']}")
        if result.get("tradeoffs"):
            print(f"  Tradeoffs: {result['tradeoffs']}")
        if result.get("concerns"):
            print(f"  Concerns: {result['concerns']}")


if __name__ == "__main__":
    report = advise_all()
    print_report(report)