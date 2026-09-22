from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, make_asgi_app
from sqlalchemy import and_, func, select

from app.db.base import SessionLocal
from app.db.init_db import init_db
from app.models.entities import WeatherForecast
from app.services.agent import answer


app = FastAPI(title="On-Prem Weather & Travel Agent", version="1.0.0")
app.mount("/metrics", make_asgi_app())

CHAT = Counter("agent_requests_total", "Agent requests")
LAT = Histogram("agent_request_duration_seconds", "Agent request latency")


class ChatRequest(BaseModel):
    question: str


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


def latest_weather_statement(city: str):
    latest = (
        select(
            WeatherForecast.city.label("city"),
            WeatherForecast.forecast_date.label("forecast_date"),
            func.max(WeatherForecast.collected_at).label("max_collected_at"),
        )
        .where(WeatherForecast.city == city)
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
        .order_by(WeatherForecast.forecast_date)
    )


@app.get("/weather/{city}")
def weather(city: str):
    with SessionLocal() as db:
        rows = list(db.scalars(latest_weather_statement(city)))

    if not rows:
        raise HTTPException(404, "No synchronized weather for this city")

    return [
        {
            "city": row.city,
            "forecast_date": row.forecast_date.isoformat(),
            "temp_min": row.temp_min,
            "temp_max": row.temp_max,
            "rain_probability": row.rain_probability,
            "wind_speed": row.wind_speed,
            "weather_code": row.weather_code,
            "recommendation": row.recommendation,
            "collected_at": row.collected_at.isoformat(),
        }
        for row in rows
    ]


@app.post("/agent/chat")
async def chat(req: ChatRequest):
    CHAT.inc()
    with LAT.time():
        return {"answer": await answer(req.question)}
