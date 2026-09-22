import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st


API_URL = os.getenv("API_URL", "http://api:8000")
CITIES = ["Rome", "London", "Tel Aviv", "Budapest", "Lisbon"]


st.set_page_config(
    page_title="On-Prem Weather & Travel Agent",
    page_icon="🌤️",
    layout="wide",
)


def api_get(path: str, timeout: int = 30):
    response = requests.get(f"{API_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict, timeout: int = 360):
    response = requests.post(
        f"{API_URL}{path}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def get_answer(payload):
    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        for key in ("answer", "response", "message", "result"):
            if payload.get(key):
                return str(payload[key])

    return str(payload)


def check_health():
    try:
        return True, api_get("/health", timeout=5)
    except Exception as exc:
        return False, {"error": str(exc)}


def load_weather(city: str):
    try:
        payload = api_get(f"/weather/{city}", timeout=30)
        return payload if isinstance(payload, list) else [], None
    except Exception as exc:
        return [], str(exc)


if "messages" not in st.session_state:
    st.session_state.messages = []


st.title("🌤️ On-Prem Weather & Travel Agent")
st.caption(
    "Local weather intelligence, activity recommendations and trip planning "
    "using RabbitMQ, PostgreSQL, Ollama and Qwen."
)


with st.sidebar:
    st.header("System")

    healthy, _ = check_health()
    if healthy:
        st.success("API online")
    else:
        st.error("API unavailable")

    st.markdown("### Components")
    st.write("🐇 RabbitMQ")
    st.write("🐘 PostgreSQL")
    st.write("🤖 Ollama / Qwen")
    st.write("⚡ FastAPI")
    st.write("📊 Prometheus")
    st.write("📈 Grafana")

    st.divider()
    st.caption(
        "External internet access is required only during weather synchronization. "
        "Queries use locally stored data and a locally hosted LLM."
    )


dashboard_tab, chat_tab, about_tab = st.tabs(
    ["📊 Weather Dashboard", "💬 Travel Agent", "🏗️ About"]
)


with dashboard_tab:
    left, right = st.columns([3, 1])

    with left:
        selected_city = st.selectbox("Select city", CITIES)

    with right:
        st.write("")
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    weather, error = load_weather(selected_city)

    if error:
        st.error(f"Could not retrieve weather data: {error}")

    elif not weather:
        st.warning("No synchronized weather information is available for this city yet.")

    else:
        df = pd.DataFrame(weather)
        df["forecast_date"] = pd.to_datetime(df["forecast_date"], errors="coerce")
        df = df.sort_values("forecast_date")

        first = df.iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Min temperature", f"{first['temp_min']} °C")
        c2.metric("Max temperature", f"{first['temp_max']} °C")
        c3.metric("Rain probability", f"{first['rain_probability']}%")
        c4.metric("Wind", f"{first['wind_speed']} km/h")

        st.divider()
        st.subheader(f"7-day forecast — {selected_city}")

        chart1, chart2 = st.columns(2)

        with chart1:
            st.markdown("**Temperature forecast**")
            temp_df = df.set_index("forecast_date")[["temp_min", "temp_max"]]
            st.line_chart(temp_df, use_container_width=True)

        with chart2:
            st.markdown("**Rain probability**")
            rain_df = df.set_index("forecast_date")[["rain_probability"]]
            st.bar_chart(rain_df, use_container_width=True)

        recommendation = str(first.get("recommendation", "")).strip()
        if recommendation:
            st.subheader("🤖 Local AI recommendation")
            st.info(recommendation)

        st.subheader("Forecast data")
        display = df[
            [
                "forecast_date",
                "temp_min",
                "temp_max",
                "rain_probability",
                "wind_speed",
                "recommendation",
            ]
        ].copy()
        display["forecast_date"] = display["forecast_date"].dt.strftime("%Y-%m-%d")
        st.dataframe(display, use_container_width=True, hide_index=True)


with chat_tab:
    st.subheader("💬 Ask the local travel agent")
    st.caption(
        "The agent retrieves synchronized weather, tourism and event information "
        "from PostgreSQL and then asks the local Qwen model to answer."
    )

    ex1, ex2 = st.columns(2)
    with ex1:
        st.markdown(
            """
**Weather & activities**
- What is the weather tomorrow in Rome?
- Should I run tomorrow in Tel Aviv?
- What should I do in Budapest if it rains?
"""
        )
    with ex2:
        st.markdown(
            """
**Travel planning**
- Plan a one-day trip in Lisbon based on the weather.
- What can I do this week in London?
- Recommend outdoor activities in Rome.
"""
        )

    st.divider()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input(
        "Ask about weather, tourism, activities or trip planning..."
    )

    if question:
        st.session_state.messages.append({"role": "user", "content": question})

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving local data and asking Qwen..."):
                try:
                    answer = get_answer(
                        api_post(
                            "/agent/chat",
                            {"question": question},
                            timeout=360,
                        )
                    )
                except requests.Timeout:
                    answer = (
                        "The local model exceeded the UI timeout. CPU-only local "
                        "inference can be slow; try again or configure a smaller model."
                    )
                except Exception as exc:
                    answer = f"Agent request failed: {exc}"

            st.markdown(answer)

        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )

    if st.session_state.messages and st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()


with about_tab:
    st.subheader("🏗️ Architecture")
    st.code(
        """
Open-Meteo
    ↓
Weather Producer
    ↓
RabbitMQ ─────────→ DLQ
    ↓
Weather Consumer ─→ Ollama / Qwen
    ↓
PostgreSQL
    ↑
Agent Harness ────→ Ollama / Qwen
    ↓
FastAPI
    ↓
Streamlit

Prometheus → Grafana
""",
        language=None,
    )

    st.subheader("Design goals")
    st.markdown(
        """
- **On-prem capable:** all core components run locally in Docker containers.
- **Local AI:** Ollama hosts an open-weight Qwen model; no external LLM API is required.
- **Reliable ingestion:** RabbitMQ decouples collection from processing and supports retries/DLQ.
- **Offline querying:** synchronized weather and city knowledge remain available without internet access.
- **Observability:** Prometheus exposes application and LLM metrics for Grafana.
"""
    )

    st.caption(f"Page loaded at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
