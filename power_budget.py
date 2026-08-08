"""
Best-effort cross-category power budget check.

Honesty note: DigiKey's parametric fields don't reliably include every
current-draw figure a real power budget needs (active/peak current for an
MCU's Wi-Fi TX burst, a solenoid coil's steady-state draw, a sensor's
active-mode current, etc). This check only sums whatever quiescent/standby
current figures ARE present in the parametric data, and compares that
total against the voltage regulator's rated max output current. It's a
sanity check for the "always-on" baseline draw, not a full power budget -
the report says so explicitly rather than pretending otherwise.
"""

import json
import re
from components_db import get_components_by_category

# Word-based (not exact-phrase) matching, since DigiKey's parameter naming
# is inconsistent across categories - "Current - Supply (Max)", "Operating
# Supply Current", "Quiescent Current (Iq)" all describe the same thing in
# a different word order. A key counts as a quiescent-current field if it
# contains "current" plus at least one of these qualifier words.
_QUIESCENT_QUALIFIERS = [
    "quiescent", "iq", "standby", "sleep", "shutdown", "supply", "operating",
]

# Same idea for the regulator's rated max output current.
_OUTPUT_QUALIFIERS = ["output", "limit"]


def _matches_current_param(key_lower, qualifiers):
    return "current" in key_lower and any(q in key_lower for q in qualifiers)

# Matches a number followed by an optional metric prefix and "A" for amps,
# e.g. "900nA", "1.2mA (Max)", "600 mA", "0.25A".
_CURRENT_PATTERN = re.compile(r"([\d.]+)\s*(n|µ|u|m)?a\b", re.IGNORECASE)

_PREFIX_TO_MA = {"": 1000.0, "m": 1.0, "µ": 0.001, "u": 0.001, "n": 0.000001}


def _parse_current_to_ma(value_str):
    if not value_str:
        return None
    match = _CURRENT_PATTERN.search(str(value_str))
    if not match:
        return None
    number = float(match.group(1))
    prefix = (match.group(2) or "").lower().replace("u", "µ")
    return number * _PREFIX_TO_MA.get(prefix, 1000.0)


def _load_parameters(parameters_field):
    if isinstance(parameters_field, dict):
        return parameters_field
    if isinstance(parameters_field, str):
        try:
            return json.loads(parameters_field)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _find_current_ma(parameters_field, qualifiers):
    parameters = _load_parameters(parameters_field)
    for key, value in parameters.items():
        if _matches_current_param(key.lower(), qualifiers):
            parsed = _parse_current_to_ma(value)
            if parsed is not None:
                return parsed
    return None


def _available_current_like_keys(parameters_field):
    """For diagnostics: what parameter keys mention 'current' at all, even
    if we couldn't confidently classify or parse them. Lets you see whether
    the data exists under an unexpected name, or just isn't returned by
    DigiKey's keyword-search endpoint for this part type."""
    parameters = _load_parameters(parameters_field)
    return [f"{k}: {v}" for k, v in parameters.items() if "current" in k.lower()]


def build_power_budget_report(report):
    """
    report: dict of category -> {"picks": [...], ...} as returned by
            component_advisor.advise_all()

    Returns a printable multi-line string summarizing the check.
    """
    quiescent_total_ma = 0.0
    counted_categories = []
    unknown_categories = []
    diagnostics = {}  # category -> list of "Key: Value" strings mentioning current
    regulator_capacity_ma = None
    regulator_category = None

    for category, result in report.items():
        picks = result.get("picks", [])
        if not picks:
            continue

        top_mpn = picks[0].get("mpn")
        rows = {row["mpn"]: row for row in get_components_by_category(category)}
        row = rows.get(top_mpn)
        if not row:
            continue

        if "regulator" in category.lower():
            cap = _find_current_ma(row["parameters"], _OUTPUT_QUALIFIERS)
            if cap is not None:
                regulator_capacity_ma = cap
                regulator_category = category
            continue

        iq = _find_current_ma(row["parameters"], _QUIESCENT_QUALIFIERS)
        if iq is not None:
            quiescent_total_ma += iq
            counted_categories.append(category)
        else:
            unknown_categories.append(category)
            current_like = _available_current_like_keys(row["parameters"])
            if current_like:
                diagnostics[category] = current_like

    lines = []
    lines.append("--- Power Budget Check (best-effort, quiescent draw only) ---")

    if counted_categories:
        lines.append(
            f"Estimated always-on current draw across {len(counted_categories)} "
            f"categories ({', '.join(counted_categories)}): {quiescent_total_ma:.3f} mA"
        )
    else:
        lines.append("No usable quiescent-current figures were found in the distributor parametrics.")

    if regulator_capacity_ma is not None:
        lines.append(f"Regulator ({regulator_category}) rated max output current: {regulator_capacity_ma:.1f} mA")
        if counted_categories:
            if quiescent_total_ma > regulator_capacity_ma:
                lines.append("WARNING: estimated quiescent draw exceeds the regulator's rated output current.")
            else:
                headroom = regulator_capacity_ma - quiescent_total_ma
                lines.append(
                    f"Headroom before hitting the regulator's rated limit: {headroom:.1f} mA "
                    "(this does not include active/peak loads)."
                )
    else:
        lines.append("Could not find a rated output current for the voltage regulator category - skipping capacity check.")

    if unknown_categories:
        lines.append(
            f"No quiescent current data found in distributor parametrics for: "
            f"{', '.join(unknown_categories)}. These are NOT included in the total above - "
            "check their datasheets manually."
        )
        if diagnostics:
            lines.append("")
            lines.append("Diagnostic - these categories DO have a 'current'-related field, "
                          "but it wasn't recognized as quiescent/supply current (worth a look):")
            for category, entries in diagnostics.items():
                for entry in entries:
                    lines.append(f"  [{category}] {entry}")

    lines.append(
        "Note: this checks passive/quiescent draw only, not active operating current "
        "(e.g. Wi-Fi TX bursts, solenoid coil current, active sensor draw). "
        "Use it as a sanity check, not a substitute for a full power budget."
    )

    return "\n".join(lines)