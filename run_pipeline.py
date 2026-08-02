import sys

from requirement_parser import parse_requirements
from populate_components import populate_from_categories
from component_advisor import advise_all, print_report


def run(prompt_text, record_count=5):
    print("Parsing requirements into component categories...")
    categories = parse_requirements(prompt_text)
    print(f"Identified {len(categories)} component categories:")
    for c in categories:
        print(f"  - {c['category']}: {c['search_keyword']}")

    print("\nPulling real parts from DigiKey...")
    populate_from_categories(categories, record_count=record_count)

    print("\nRunning AI selection and tradeoff analysis...")
    report = advise_all()
    print_report(report)
    return report


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