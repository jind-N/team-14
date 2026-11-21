import json
from collections import Counter
from datetime import datetime, timezone

import streamlit as st

st.set_page_config(page_title="Footprint Receipt", page_icon="🔎")

st.title("Footprint Receipt")
st.write(
    "A local-first privacy audit. This first version looks for Google Search "
    "activity in a My Activity JSON export."
)
st.info(
    "The built-in example is fake. Search terms are counted but never shown. "
    "This prototype does not delete anything."
)

demo_records = [
    {"header": "Search", "time": "2025-01-05T09:00:00Z"},
    {"header": "Search", "time": "2025-01-05T18:00:00Z"},
    {"header": "Search", "time": "2025-01-08T10:00:00Z"},
]


def count_search_days(records):
    if not isinstance(records, list):
        raise ValueError("This JSON file does not have the expected list format.")

    days = Counter()

    for record in records:
        if not isinstance(record, dict) or record.get("header") != "Search":
            continue

        timestamp = record.get("time")
        if not isinstance(timestamp, str):
            continue

        try:
            date = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
            if date.tzinfo is not None:
                date = date.astimezone(timezone.utc)
            days[date.date().isoformat()] += 1
        except (ValueError, OverflowError):
            continue

    return days


uploaded_file = st.file_uploader(
    "Choose a Google Search MyActivity.json file",
    type=["json"],
)

if uploaded_file is None:
    records = demo_records
    source = "Synthetic demo data"
else:
    source = "Uploaded Google Search export"
    try:
        records = json.load(uploaded_file)
    except (json.JSONDecodeError, UnicodeDecodeError):
        st.error("That file could not be read as JSON.")
        st.stop()

try:
    days = count_search_days(records)
except ValueError as error:
    st.error(str(error))
    st.stop()

if not days:
    st.warning(
        "No Google Search records were recognized in this file. "
        "That does not prove the platform has no data about you."
    )
    st.stop()

total = sum(days.values())
first_day = min(days)
last_day = max(days)

st.caption(f"Source: {source}")
st.metric("Search activity records found", total)
st.write(f"Date range in this file: **{first_day} to {last_day} (UTC)**")

chart_data = {
    "Day": list(days.keys()),
    "Records": list(days.values()),
}
st.bar_chart(chart_data, x="Day", y="Records")

report = f"""# Footprint Receipt

**Source:** {source}

**Evidence:** Found {total} Google Search activity records in this file,
from {first_day} to {last_day} (UTC). Search terms are not included in this report.

## Suggested action

Visit [Google My Activity](https://myactivity.google.com/), filter by date
and product, and review your Search activity. You can also review the
Web & App Activity auto-delete setting.

## Important limitation

This report describes only the file you selected. It does not confirm what
Google currently stores, and it does not delete data.
"""

st.markdown(report)
st.download_button(
    "Download privacy action receipt",
    report,
    file_name="footprint-receipt.md",
    mime="text/markdown",
)