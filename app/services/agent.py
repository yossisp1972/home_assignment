from datetime import date, timedelta

from sqlalchemy import and_, func, select

from app.db.base import SessionLocal
from app.models.entities import CityKnowledge, Event, WeatherForecast
from app.services.ollama import generate


CITY_NAMES = ["Rome", "London", "Tel Aviv", "Budapest", "Lisbon"]


def detect_city(question: str) -> str | None:
    q = question.lower()
    return next((city for city in CITY_NAMES if city.lower() in q), None)


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

    stmt = (
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

    return stmt


def retrieve_context(question: str) -> str:
    city = detect_city(question)

    with SessionLocal() as db:
        chunks = []

        weather_stmt = latest_weather_statement(city)
        knowledge_stmt = select(CityKnowledge).limit(30)
        events_stmt = (
            select(Event)
            .where(
                Event.event_date >= date.today(),
                Event.event_date <= date.today() + timedelta(days=30),
            )
            .order_by(Event.event_date)
            .limit(30)
        )

        if city:
            knowledge_stmt = (
                select(CityKnowledge)
                .where(CityKnowledge.city == city)
                .limit(30)
            )
            events_stmt = (
                select(Event)
                .where(
                    Event.city == city,
                    Event.event_date >= date.today(),
                    Event.event_date <= date.today() + timedelta(days=30),
                )
                .order_by(Event.event_date)
                .limit(30)
            )

        for weather in db.scalars(weather_stmt):
            chunks.append(
                "WEATHER "
                f"{weather.city} {weather.forecast_date}: "
                f"{weather.temp_min}-{weather.temp_max}C, "
                f"rain {weather.rain_probability}%, "
                f"wind {weather.wind_speed} km/h. "
                f"Recommendation: {weather.recommendation}"
            )

        for knowledge in db.scalars(knowledge_stmt):
            chunks.append(
                f"CITY {knowledge.city} [{knowledge.category}] "
                f"{knowledge.title}: {knowledge.content}"
            )

        for event in db.scalars(events_stmt):
            chunks.append(
                f"EVENT {event.city} {event.event_date} "
                f"[{event.category}] {event.title} at {event.venue}: "
                f"{event.description}"
            )

    return "\n".join(chunks)


async def answer(question: str) -> str:
    context = retrieve_context(question)

    if not context.strip():
        return "No synchronized local information is available for that question yet."

    prompt = f"""You are an on-prem travel and weather agent.
Answer using ONLY the supplied local context.
Do not invent current events, weather, places, or facts.
If event information is absent, say that current event information has not been synchronized.
Today is {date.today()}.

LOCAL CONTEXT:
{context}

USER QUESTION:
{question}

Provide a concise, useful answer.
For itinerary requests, organize the answer by time of day.
"""

    return await generate(prompt)
