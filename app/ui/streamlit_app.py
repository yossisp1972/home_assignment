import os
import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://api:8000")
CITIES = ["Rome", "London", "Tel Aviv", "Budapest", "Lisbon"]

st.set_page_config(page_title="Weather Trip Agent", layout="wide")
st.title("On-Prem Weather & Travel Agent")
st.caption("Local weather intelligence, activity recommendations, and trip planning")

city = st.sidebar.selectbox("City", CITIES)
try:
    rows = requests.get(f"{API}/weather/{city}", timeout=15).json()
    if isinstance(rows, list) and rows:
        df = pd.DataFrame(rows)
        st.subheader(f"7-day forecast: {city}")
        st.line_chart(df.set_index("date")[["temp_min", "temp_max"]])
        st.bar_chart(df.set_index("date")[["rain_probability"]])
        st.dataframe(df, use_container_width=True)
        st.info(rows[0]["recommendation"])
    else:
        st.warning("Weather has not been synchronized yet.")
except Exception as exc:
    st.warning(f"API not ready: {exc}")

st.divider()
st.subheader("Ask the local travel agent")
question = st.text_input("Question", placeholder="What can I do tomorrow in Rome?")
if st.button("Ask") and question:
    try:
        with st.spinner("Thinking locally..."):
            r = requests.post(f"{API}/agent/chat", json={"question": question}, timeout=180)
            r.raise_for_status()
            st.write(r.json()["answer"])
    except Exception as exc:
        st.error(str(exc))
