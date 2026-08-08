"""
Export the final component_advisor report to a CSV bill of materials.

This is what turns the pipeline from a console demo into something a
recruiter (or you, on a real project) can actually open in Excel/Sheets
and use.
"""

import csv
from components_db import get_components_by_category

FIELDNAMES = [
    "category", "rank", "mpn", "manufacturer", "price_usd",
    "quantity_available", "reason", "requirement", "tradeoffs", "concerns",
]


def export_bom_to_csv(report, categories_lookup=None, filename="bom_output.csv"):
    """
    report: dict of category -> {"picks": [...], "tradeoffs": str, "concerns": str}
            as returned by component_advisor.advise_all()
    categories_lookup: optional dict of category -> requirement text, so the
            CSV includes the original requirement for context
    filename: output path
    """
    categories_lookup = categories_lookup or {}

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for category, result in report.items():
            requirement = categories_lookup.get(category, "")
            picks = result.get("picks", [])

            if not picks:
                writer.writerow({
                    "category": category,
                    "rank": "",
                    "mpn": "",
                    "manufacturer": "",
                    "price_usd": "",
                    "quantity_available": "",
                    "reason": "NO CANDIDATES FOUND",
                    "requirement": requirement,
                    "tradeoffs": "",
                    "concerns": result.get("concerns", ""),
                })
                continue

            # Look up full part details (price, stock) from the local DB
            # so the CSV is self-contained without re-querying DigiKey.
            candidates = {row["mpn"]: row for row in get_components_by_category(category)}

            for rank, pick in enumerate(picks, start=1):
                mpn = pick.get("mpn", "")
                row = candidates.get(mpn)
                writer.writerow({
                    "category": category,
                    "rank": rank,
                    "mpn": mpn,
                    "manufacturer": row["manufacturer"] if row else "",
                    "price_usd": row["price_usd"] if row else "",
                    "quantity_available": row["quantity_available"] if row else "",
                    "reason": pick.get("reason", ""),
                    "requirement": requirement,
                    # Only show tradeoffs/concerns once per category, on the top pick,
                    # to avoid repeating the same paragraph on every row.
                    "tradeoffs": result.get("tradeoffs", "") if rank == 1 else "",
                    "concerns": result.get("concerns", "") if rank == 1 else "",
                })

    print(f"BOM exported to {filename}")
    return filename