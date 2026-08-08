"""
Streamlit UI for the Smart Component Selector pipeline.

Run locally with:
    streamlit run app.py

Requires DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET, and GEMINI_API_KEY.
Locally these can be plain environment variables. On Streamlit Community
Cloud, set them instead under your app's Settings -> Secrets (they show up
via st.secrets, not the OS environment) - the block below copies them into
os.environ so the rest of the codebase doesn't need to know the difference.
"""

import contextlib
import io
import os

import pandas as pd
import streamlit as st

# Bridge Streamlit Cloud secrets into plain environment variables, since
# digikey_client.py and the Gemini client both read os.environ directly.
# Wrapped in try/except because locally, if you're using OS env vars and
# have no .streamlit/secrets.toml at all, accessing st.secrets can raise.
try:
    for _key in ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET", "GEMINI_API_KEY"):
        if _key not in os.environ and _key in st.secrets:
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass

from run_pipeline import run

st.set_page_config(page_title="Smart Component Selector", page_icon="🔧", layout="wide")

# ==============================================================================
# Theme: PCB / datasheet aesthetic.
# Deep soldermask green background, copper trace accents, silkscreen off-white
# text, monospace headers. Colors here match .streamlit/config.toml so widgets
# Streamlit themes natively (buttons, sliders) and elements it doesn't theme
# (dividers, badges, fonts) stay visually consistent with them.
# ==============================================================================

COPPER = "#C6803D"
COPPER_BRIGHT = "#E2A65C"
BG = "#0B0E0D"
SURFACE = "#141917"
TRACE_LINE = "#2A322D"
TEXT = "#EDEDE3"
TEXT_MUTED = "#8F9C96"
GOOD = "#7FBF6A"
WARN = "#C1543A"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

    html, body, [class*="css"] {{
        font-family: 'IBM Plex Sans', sans-serif;
    }}

    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
        font-family: 'IBM Plex Mono', monospace !important;
        letter-spacing: -0.01em;
    }}

    code, .stCode, .stCode * {{
        font-family: 'IBM Plex Mono', monospace !important;
    }}

    .eyebrow {{
        font-family: 'IBM Plex Mono', monospace;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.72rem;
        color: {COPPER};
        margin-bottom: 0.3rem;
    }}

    .trace-divider {{
        width: 100%;
        height: 12px;
        margin: 1.4rem 0;
    }}

    .badge {{
        display: inline-block;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        padding: 0.12rem 0.5rem;
        border-radius: 3px;
    }}
    .badge-good {{ background: {GOOD}; color: {BG}; }}
    .badge-bad {{ background: {WARN}; color: {TEXT}; }}
    .badge-copper {{ background: {COPPER}; color: {BG}; }}

    [data-testid="stExpander"] {{
        border: 1px solid {TRACE_LINE};
        border-radius: 6px;
        background: {SURFACE};
    }}
    [data-testid="stExpander"] summary {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.95rem;
    }}

    [data-testid="stSidebar"] {{
        border-right: 1px solid {TRACE_LINE};
    }}

    .stButton > button {{
        font-family: 'IBM Plex Mono', monospace;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.85rem;
    }}

    [data-testid="stMetricValue"] {{
        font-family: 'IBM Plex Mono', monospace;
    }}
</style>
""", unsafe_allow_html=True)


def trace_divider():
    """Signature element: a PCB trace line with vias, used instead of a
    generic horizontal rule to separate major sections."""
    st.markdown(
        f"""
        <svg class="trace-divider" viewBox="0 0 800 12" preserveAspectRatio="none">
            <line x1="0" y1="6" x2="800" y2="6" stroke="{TRACE_LINE}" stroke-width="2"/>
            <circle cx="40" cy="6" r="4" fill="{COPPER}"/>
            <circle cx="400" cy="6" r="4" fill="{COPPER}"/>
            <circle cx="760" cy="6" r="4" fill="{COPPER}"/>
        </svg>
        """,
        unsafe_allow_html=True,
    )


def badge(text, kind="copper"):
    return f'<span class="badge badge-{kind}">{text}</span>'


# --- Header -------------------------------------------------------------------

st.markdown('<div class="eyebrow">AI SOURCING PIPELINE // DIGIKEY + GEMINI</div>', unsafe_allow_html=True)
st.title("🔧 Smart Component Selector")
st.caption(
    "Free-text hardware requirements -> live DigiKey parts -> AI-ranked picks with "
    "tradeoffs -> exportable BOM. Nothing here is hardcoded - every run pulls real, "
    "currently priced, in-stock parts."
)

trace_divider()

# --- Sidebar: settings and environment check --------------------------------

with st.sidebar:
    st.markdown('<div class="eyebrow">Settings</div>', unsafe_allow_html=True)
    record_count = st.slider(
        "Candidates to pull per category", min_value=3, max_value=10, value=5,
        help="How many DigiKey results to fetch per component category before AI ranking.",
    )

    st.markdown('<div class="eyebrow" style="margin-top: 1.2rem;">API keys</div>', unsafe_allow_html=True)

    def _key_badge(var_name):
        ok = bool(os.environ.get(var_name))
        return badge("SET", "good") if ok else badge("MISSING", "bad")

    for var_name in ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET", "GEMINI_API_KEY"):
        st.markdown(f"`{var_name}` {_key_badge(var_name)}", unsafe_allow_html=True)

    st.caption("Set these as environment variables locally, or under Settings -> Secrets on Streamlit Cloud.")

    st.markdown('<div class="eyebrow" style="margin-top: 1.2rem;">Quota note</div>', unsafe_allow_html=True)
    st.caption(
        "Gemini's free tier allows 20 requests/day. This app batches every category "
        "into a single AI call per run, so each run only costs 1-2 requests."
    )

# --- Main: requirements input -------------------------------------------------

requirements_text = st.text_area(
    "Describe your hardware project's requirements",
    height=220,
    placeholder=(
        "e.g. A battery-powered crib monitor needs a low-power 32-bit BLE microcontroller, "
        "a PIR motion sensor, an ambient light sensor, a warm white dimmable LED, a "
        "single-cell LiPo charger IC with USB-C input, and a JST-PH battery connector. "
        "Cost-sensitive, target BOM under $15/unit."
    ),
)

keys_missing = not (
    os.environ.get("DIGIKEY_CLIENT_ID")
    and os.environ.get("DIGIKEY_CLIENT_SECRET")
    and os.environ.get("GEMINI_API_KEY")
)

if keys_missing:
    st.warning(
        "One or more required API keys are missing from your environment "
        "(see the sidebar). The pipeline will fail without them."
    )

run_clicked = st.button(
    "Run pipeline", type="primary", disabled=not requirements_text.strip(),
)

# --- Run and display results --------------------------------------------------

if run_clicked:
    log_buffer = io.StringIO()
    result = None

    with st.spinner("Parsing requirements, pulling live DigiKey data, and running AI analysis..."):
        try:
            with contextlib.redirect_stdout(log_buffer):
                result = run(requirements_text, record_count=record_count)
        except Exception as e:
            st.error(f"Pipeline crashed: {e}")

    if result is None:
        st.error(
            "Pipeline stopped before producing a result - most likely a Gemini API "
            "quota or credentials issue. Check the log below for details."
        )
    else:
        categories = result["categories"]
        report = result["report"]
        power_budget_text = result["power_budget"]
        bom_file = result["bom_file"]

        trace_divider()
        st.success(f"Done - identified {len(categories)} component categories.")

        for c in categories:
            category = c["category"]
            cat_result = report.get(category, {})
            picks = cat_result.get("picks", [])

            icon = "✅" if picks else "⚠️"
            with st.expander(f"{category}  -  \"{c['search_keyword']}\"", icon=icon):
                st.markdown(f"**Requirement:** {c['requirement']}")

                if picks:
                    df = pd.DataFrame(picks)
                    df.index = df.index + 1
                    df.index.name = "rank"
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning("No candidates found for this category.")

                if cat_result.get("tradeoffs"):
                    st.markdown(f"**Tradeoffs:** {cat_result['tradeoffs']}")
                if cat_result.get("concerns"):
                    st.markdown(f"**Concerns:** {cat_result['concerns']}")

        trace_divider()

        st.markdown('<div class="eyebrow">Power budget check</div>', unsafe_allow_html=True)
        st.caption("Best-effort - only checks quiescent/standby draw against the regulator's rated output.")
        st.code(power_budget_text, language=None)

        st.markdown('<div class="eyebrow" style="margin-top: 1.2rem;">Bill of materials</div>', unsafe_allow_html=True)
        if os.path.exists(bom_file):
            with open(bom_file, "rb") as f:
                st.download_button(
                    "Download BOM (CSV)", f, file_name=os.path.basename(bom_file),
                    mime="text/csv",
                )
        else:
            st.warning("BOM file was not created.")

    with st.expander("Pipeline log (console output)", icon="📋"):
        st.code(log_buffer.getvalue() or "(no output captured)")