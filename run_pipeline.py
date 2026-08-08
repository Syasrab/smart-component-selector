import sys

from requirement_parser import parse_requirements
from populate_components import populate_from_categories
from component_advisor import advise_all, print_report
from components_db import normalize_category
from export_bom import export_bom_to_csv
from power_budget import build_power_budget_report


def run(prompt_text, record_count=5, bom_filename="bom_output.csv"):
    """Runs the full pipeline. Returns a dict with everything a caller
    (CLI or UI) might need, or None if the pipeline had to stop early
    (e.g. Gemini quota exhausted before any categories were parsed):
        {
            "categories": [...],           # as parsed + normalized
            "report": {...},               # category -> picks/tradeoffs/concerns
            "power_budget": "...",         # printable power budget text
            "bom_file": "bom_output.csv",  # path to the exported CSV
        }
    """
    print("Parsing requirements into component categories...")
    try:
        categories = parse_requirements(prompt_text)
    except RuntimeError as e:
        print(f"\nStopped: {e}")
        return None

    # Normalize category names right away so populate/advise/export all
    # agree on the same category keys, and so the same component type
    # doesn't fragment into near-duplicate categories across runs.
    for c in categories:
        c["category"] = normalize_category(c["category"])

    print(f"Identified {len(categories)} component categories:")
    for c in categories:
        print(f"  - {c['category']}: {c['search_keyword']}")

    print("\nPulling real parts from DigiKey...")
    populate_from_categories(categories, record_count=record_count)

    print("\nRunning AI selection and tradeoff analysis...")
    report = advise_all()
    print_report(report)

    power_budget_text = build_power_budget_report(report)
    print("\n" + power_budget_text)

    categories_lookup = {c["category"]: c["requirement"] for c in categories}
    export_bom_to_csv(report, categories_lookup, filename=bom_filename)

    return {
        "categories": categories,
        "report": report,
        "power_budget": power_budget_text,
        "bom_file": bom_filename,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # python run_pipeline.py requirements.txt
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        print("Paste your project requirements, then press Ctrl+Z then Enter (Windows) "
              "or Ctrl+D (Mac/Linux) when done:\n")
        text = sys.stdin.read()

    if not text.strip():
        print("No requirements text provided.")
        sys.exit(1)

    run(text)