import json
import time
from google import genai
from google.genai import types
from google.genai import errors

MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = """You are a hardware requirements analyst. Given a free-text hardware project \
requirements description, identify each distinct type of ELECTRONIC component needed to build it \
(e.g. microcontroller, sensor, LED, power management IC, connector, switch). Ignore mechanical, \
enclosure, tooling, or regulatory items - only components sourceable from an electronics \
distributor like DigiKey.

Return ONLY valid JSON (no markdown fences, no commentary) matching exactly this shape:
{
  "components": [
    {
      "category": "short_snake_case_id",
      "search_keyword": "concise DigiKey search term",
      "requirement": "1-3 sentence plain-English summary of what this component must satisfy"
    },
    ...
  ]
}

Guidance for search_keyword: prefer specific component types or reference part numbers over vague \
words like "module" or "sensor kit" - DigiKey's catalog is mostly bare components and ICs, not \
hobbyist modules. If the text names a reference part (e.g. "TP4057" or "nRF52832"), use it or a \
close variant as the keyword.

Guidance for category: keep it short, unique, and descriptive (e.g. "microcontroller_ble", \
"pir_motion_sensor", "lipo_charger_ic")."""


def parse_requirements(prompt_text, client=None, max_retries=3):
    client = client or genai.Client()
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
            parsed = json.loads(response.text.strip())
            return parsed["components"]
        except errors.ServerError:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"Gemini is busy, retrying in {wait}s...")
            time.sleep(wait)


if __name__ == "__main__":
    example = (
        "I need a battery-powered crib monitor with a low-power 32-bit BLE microcontroller, "
        "a PIR motion sensor, an ambient light sensor, a warm white dimmable LED, "
        "a single-cell LiPo charger IC with USB-C input, and a JST-PH battery connector."
    )
    components = parse_requirements(example)
    for c in components:
        print(c)