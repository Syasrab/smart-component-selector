import json
import re
import time
from google import genai
from google.genai import types
from google.genai import errors

from components_db import get_components_by_category, get_categories

MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = """You are a hardware component selection advisor. You will be given several \
component categories, each with a requirement description and a list of real, currently \
available candidate parts (manufacturer, price, stock, and parametric specs from a distributor).

For EACH category, pick the best 2-3 candidates for its requirement. Return ONLY valid JSON \
(no markdown fences, no commentary) matching exactly this shape:
{
  "categories": {
    "<category_id_exactly_as_given>": {
      "picks": [
        {"mpn": "string", "reason": "one sentence on why this is a strong fit"},
        ...
      ],
      "tradeoffs": "2-3 sentences comparing the picks against each other - what you gain and \
give up choosing one over another (price vs power, stock vs specs, etc.)",
      "concerns": "one sentence flagging anything the requirement needs that none of the \
candidates clearly satisfy, or empty string if none"
    },
    ...
  }
}

Only pick from the candidates given for each category. Do not invent parts or specs not shown \
to you. Include every category from the input in your output, using the exact category id given."""


def _build_combined_prompt(categories_with_candidates):
    """categories_with_candidates: list of (category_info, rows) tuples where rows is a
    non-empty list of candidate parts for that category."""
    sections = []
    for category_info, rows in categories_with_candidates:
        candidates_text = "\n".join(
            f"- {row['mpn']} ({row['manufacturer']}): ${row['price_usd']}, "
            f"stock={row['quantity_available']}, specs={row['parameters']}"
            for row in rows
        )
        sections.append(
            f"### Category: {category_info['category']}\n"
            f"Requirement: {category_info['requirement']}\n"
            f"Candidates:\n{candidates_text}"
        )
    return "\n\n".join(sections)


def _retry_delay_seconds(error, default):
    """Best-effort extraction of the server-suggested retry delay (e.g. '53s')
    from a Gemini ClientError's details, falling back to `default` if absent."""
    try:
        violations = error.details.get("error", {}).get("details", [])
        for v in violations:
            delay = v.get("retryDelay")
            if delay:
                match = re.match(r"([\d.]+)", delay)
                if match:
                    return float(match.group(1))
    except (AttributeError, TypeError):
        pass
    return default


def advise_category(category_info, client=None, max_retries=3):
    """Advise on a single category. Kept for standalone/one-off use;
    advise_all() below batches all categories into one request instead,
    which is what run_pipeline.py uses to stay under free-tier quotas."""
    client = client or genai.Client()
    rows = get_components_by_category(category_info["category"])
    if not rows:
        return {"picks": [], "tradeoffs": "", "concerns": "No candidates found in database."}

    prompt = _build_combined_prompt([(category_info, rows)])

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
            parsed = json.loads(response.text.strip())
            return parsed["categories"][category_info["category"]]
        except errors.ServerError:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  Gemini is busy, retrying in {wait}s...")
            time.sleep(wait)
        except errors.ClientError as e:
            if e.code == 429:
                if attempt == max_retries - 1:
                    return {"picks": [], "tradeoffs": "",
                            "concerns": "AI analysis unavailable - Gemini API quota exceeded."}
                wait = _retry_delay_seconds(e, default=2 ** attempt)
                print(f"  Gemini rate-limited, retrying in {wait:.0f}s...")
                time.sleep(wait)
            else:
                raise


def advise_all(client=None, max_retries=4):
    """Sends ALL categories to Gemini in a SINGLE request instead of one
    request per category. A 10-category project used to cost 10 Gemini
    calls; now it costs 1, which matters a lot on the free tier's daily
    request quota.

    Categories with zero candidates are resolved locally without an API
    call at all. If the quota is exhausted, categories that needed AI
    analysis are marked accordingly instead of crashing the whole pipeline -
    so the DigiKey data you already pulled isn't wasted."""
    client = client or genai.Client()
    categories = get_categories()

    report = {}
    categories_with_candidates = []
    for category_info in categories:
        rows = get_components_by_category(category_info["category"])
        if not rows:
            report[category_info["category"]] = {
                "picks": [], "tradeoffs": "", "concerns": "No candidates found in database."
            }
        else:
            categories_with_candidates.append((category_info, rows))

    if not categories_with_candidates:
        return report

    prompt = _build_combined_prompt(categories_with_candidates)
    category_ids = [c["category"] for c, _ in categories_with_candidates]

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
            parsed = json.loads(response.text.strip())
            categories_result = parsed.get("categories", {})
            for category_id in category_ids:
                report[category_id] = categories_result.get(category_id, {
                    "picks": [], "tradeoffs": "",
                    "concerns": "AI response did not include this category.",
                })
            return report

        except errors.ServerError:
            if attempt == max_retries - 1:
                for category_id in category_ids:
                    report.setdefault(category_id, {
                        "picks": [], "tradeoffs": "",
                        "concerns": "AI analysis unavailable - Gemini server error.",
                    })
                return report
            wait = 2 ** attempt
            print(f"  Gemini is busy, retrying in {wait}s...")
            time.sleep(wait)

        except errors.ClientError as e:
            if e.code == 429:
                if attempt == max_retries - 1:
                    print("  Gemini free-tier quota exhausted - AI analysis skipped for "
                          "remaining categories. DigiKey data and BOM export are unaffected.")
                    for category_id in category_ids:
                        report.setdefault(category_id, {
                            "picks": [], "tradeoffs": "",
                            "concerns": "AI analysis unavailable - Gemini API quota exceeded.",
                        })
                    return report
                wait = _retry_delay_seconds(e, default=2 ** attempt)
                print(f"  Gemini rate-limited, retrying in {wait:.0f}s...")
                time.sleep(wait)
            else:
                raise

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