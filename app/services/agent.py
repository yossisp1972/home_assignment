from datetime import date, timedelta
from sqlalchemy import select
from app.db.base import SessionLocal
from app.models.entities import WeatherForecast, CityKnowledge, Event
from app.services.ollama import generate

CITY_NAMES = ["Rome", "London", "Tel Aviv", "Budapest", "Lisbon"]

def detect_city(question: str) -> str | None:
    q = question.lower()
    return next((c for c in CITY_NAMES if c.lower() in q), None)

def retrieve_context(question: str) -> str:
    city = detect_city(question)
    with SessionLocal() as db:
        chunks = []
        weather_stmt = select(WeatherForecast).order_by(WeatherForecast.forecast_date.desc()).limit(14)
        knowledge_stmt = select(CityKnowledge).limit(30)
        events_stmt = select(Event).where(Event.event_date >= date.today(), Event.event_date <= date.today() + timedelta(days=30)).limit(30)
        if city:
            weather_stmt = select(WeatherForecast).where(WeatherForecast.city == city).order_by(WeatherForecast.forecast_date).limit(14)
            knowledge_stmt = select(CityKnowledge).where(CityKnowledge.city == city).limit(30)
            events_stmt = select(Event).where(Event.city == city, Event.event_date >= date.today(), Event.event_date <= date.today() + timedelta(days=30)).order_by(Event.event_date).limit(30)
        for w in db.scalars(weather_stmt):
            chunks.append(f"WEATHER {w.city} {w.forecast_date}: {w.temp_min}-{w.temp_max}C, rain {w.rain_probability}%, wind {w.wind_speed} km/h. Recommendation: {w.recommendation}")
        for k in db.scalars(knowledge_stmt):
            chunks.append(f"CITY {k.city} [{k.category}] {k.title}: {k.content}")
        for e in db.scalars(events_stmt):
            chunks.append(f"EVENT {e.city} {e.event_date} [{e.category}] {e.title} at {e.venue}: {e.description}")
    return "\n".join(chunks)

async def answer(question: str) -> str:
    context = retrieve_context(question)
    prompt = f"""You are an on-prem travel and weather agent.
Answer using ONLY the supplied local context. If current event information is absent, say it has not been synchronized. Do not invent facts.
Today is {date.today()}.

LOCAL CONTEXT:
{context}

USER QUESTION:
{question}

Provide a concise useful answer. For itinerary requests, organize the answer by time of day."""
    return await generate(prompt)
