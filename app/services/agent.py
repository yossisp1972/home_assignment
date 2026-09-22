from datetime import date, timedelta

from sqlalchemy import and_, func, select

from app.db.base import SessionLocal
from app.models.entities import CityKnowledge, Event, WeatherForecast
from app.services.ollama import generate


SUPPORTED_CITIES = ["Rome", "London", "Tel Aviv", "Budapest", "Lisbon"]


def detect_city(question: str) -> str | None:
    q = question.lower()
    return next((city for city in SUPPORTED_CITIES if city.lower() in q), None)


def classify_context(question: str) -> tuple[bool, bool, bool]:
    """Choose only the local data needed for the question.

    This keeps prompts small enough for CPU-only local inference while still
    grounding weather, tourism and event answers in PostgreSQL.
    """
    q = question.lower()

    weather_terms = (
        "weather", "forecast", "temperature", "rain", "wind", "sunny",
        "tomorrow", "today", "outdoor", "run", "running",
    )
    tourism_terms = (
        "trip", "itinerary", "visit", "tourism", "attraction", "history",
        "shopping", "dining", "restaurant", "places", "things to do",
        "activity", "activities",
    )
    event_terms = (
        "event", "events", "concert", "concerts", "sport", "sports",
        "game", "games", "match", "matches", "show", "shows",
    )

    use_weather = any(term in q for term in weather_terms)
    use_tourism = any(term in q for term in tourism_terms)
    use_events = any(term in q for term in event_terms)

    # Broad planning questions benefit from both weather and city knowledge.
    if use_tourism:
        use_weather = True

    # If the intent is unclear, provide a bounded mix rather than no context.
    if not any((use_weather, use_tourism, use_events)):
        use_weather = use_tourism = True

    return use_weather, use_tourism, use_events


def latest_weather_statement(city: str | None = None):
    latest_query = select(
        WeatherForecast.city.label("city"),
        WeatherForecast.forecast_date.label("forecast_date"),
        func.max(WeatherForecast.collected_at).label("max_collected_at"),
    )

    if city:
        latest_query = latest_query.where(WeatherForecast.city == city)

    latest = (
        latest_query
        .group_by(WeatherForecast.city, WeatherForecast.forecast_date)
        .subquery()
    )

    return (
        select(WeatherForecast)
        .join(
            latest,
            and_(
                WeatherForecast.city == latest.c.city,
                WeatherForecast.forecast_date == latest.c.forecast_date,
                WeatherForecast.collected_at == latest.c.max_collected_at,
            ),
        )
        .order_by(WeatherForecast.city, WeatherForecast.forecast_date)
    )


def retrieve_context(question: str) -> tuple[str, str | None]:
    city = detect_city(question)
    use_weather, use_tourism, use_events = classify_context(question)
    chunks: list[str] = []

    with SessionLocal() as db:
        if use_weather:
            for weather in db.scalars(latest_weather_statement(city)):
                chunks.append(
                    "WEATHER "
                    f"{weather.city} {weather.forecast_date}: "
                    f"temperature {weather.temp_min}-{weather.temp_max} C, "
                    f"rain probability {weather.rain_probability}%, "
                    f"wind {weather.wind_speed} km/h, "
                    f"weather code {weather.weather_code}. "
                    f"Recommendation: {weather.recommendation or ''}"
                )

        if use_tourism:
            knowledge_stmt = select(CityKnowledge)
            if city:
                knowledge_stmt = knowledge_stmt.where(CityKnowledge.city == city)
            knowledge_stmt = knowledge_stmt.order_by(
                CityKnowledge.city,
                CityKnowledge.category,
                CityKnowledge.title,
            ).limit(15)

            for knowledge in db.scalars(knowledge_stmt):
                chunks.append(
                    f"CITY {knowledge.city} [{knowledge.category}] "
                    f"{knowledge.title}: {knowledge.content}"
                )

        if use_events:
            events_stmt = select(Event).where(
                Event.event_date >= date.today(),
                Event.event_date <= date.today() + timedelta(days=30),
            )
            if city:
                events_stmt = events_stmt.where(Event.city == city)
            events_stmt = events_stmt.order_by(Event.event_date).limit(10)

            for event in db.scalars(events_stmt):
                chunks.append(
                    f"EVENT {event.city} {event.event_date} [{event.category}] "
                    f"{event.title} at {event.venue or 'Not specified'}: "
                    f"{event.description or ''}"
                )

    return "\n".join(chunks), city


async def answer(question: str) -> str:
    context, city = retrieve_context(question)

    if not context.strip():
        return "No synchronized local information is available for that question yet."

    detected_city = city or "not explicitly specified"
    today = date.today().isoformat()

    prompt = f"""You are a local weather and travel assistant running fully on-prem.
Today's date is {today}.
Detected city: {detected_city}.

Answer the user's question directly and concisely.
Do not describe your reasoning process.
Do not mention how context was created or retrieved.
Do not say phrases such as "we are given", "the user asks", or "looking at the context".
Return only the final user-facing answer.

Use only the LOCAL CONTEXT below.
If required current information is missing, say that it has not been synchronized.
Do not invent weather, attractions, restaurants, concerts, sports events, venues, or other facts.
Interpret "today" and "tomorrow" relative to {today}.
For itineraries, organize the answer into a short practical plan and adapt it to the stored weather.

LOCAL CONTEXT:
{context}

USER QUESTION:
{question}

FINAL ANSWER:
"""

    return await generate(prompt)
