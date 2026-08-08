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

st.title("🔧 Smart Component Selector")
st.caption(
    "Free-text hardware requirements -> live DigiKey parts -> AI-ranked picks with "
    "tradeoffs -> exportable BOM. Nothing here is hardcoded - every run pulls real, "
    "currently priced, in-stock parts."
)

# --- Sidebar: settings and environment check --------------------------------

with st.sidebar:
    st.header("Settings")
    record_count = st.slider(
        "Candidates to pull per category", min_value=3, max_value=10, value=5,
        help="How many DigiKey results to fetch per component category before AI ranking.",
    )

    st.markdown("---")
    st.subheader("API keys")

    def _key_status(var_name):
        return "✅ set" if os.environ.get(var_name) else "❌ missing"

    st.markdown(f"`DIGIKEY_CLIENT_ID` - {_key_status('DIGIKEY_CLIENT_ID')}")
    st.markdown(f"`DIGIKEY_CLIENT_SECRET` - {_key_status('DIGIKEY_CLIENT_SECRET')}")
    st.markdown(f"`GEMINI_API_KEY` - {_key_status('GEMINI_API_KEY')}")
    st.caption("Set these as environment variables before launching Streamlit.")

    st.markdown("---")
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

        st.success(f"Done - identified {len(categories)} component categories.")

        for c in categories:
            category = c["category"]
            cat_result = report.get(category, {})
            picks = cat_result.get("picks", [])

            status_icon = "✅" if picks else "⚠️"
            with st.expander(f"{status_icon} {category}  -  \"{c['search_keyword']}\""):
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

        st.subheader("⚡ Power budget check")
        st.caption("Best-effort - only checks quiescent/standby draw against the regulator's rated output.")
        st.code(power_budget_text, language=None)

        st.subheader("📄 Bill of materials")
        if os.path.exists(bom_file):
            with open(bom_file, "rb") as f:
                st.download_button(
                    "Download BOM (CSV)", f, file_name=os.path.basename(bom_file),
                    mime="text/csv",
                )
        else:
            st.warning("BOM file was not created.")

    with st.expander("Pipeline log (console output)"):
        st.code(log_buffer.getvalue() or "(no output captured)")