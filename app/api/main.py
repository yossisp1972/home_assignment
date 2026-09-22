from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, make_asgi_app
from sqlalchemy import select
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

@app.get("/weather/{city}")
def weather(city: str):
    with SessionLocal() as db:
        rows = list(db.scalars(select(WeatherForecast).where(WeatherForecast.city == city).order_by(WeatherForecast.forecast_date)))
    if not rows:
        raise HTTPException(404, "No synchronized weather for this city")
    return [{
        "city": r.city,
        "date": r.forecast_date,
        "temp_min": r.temp_min,
        "temp_max": r.temp_max,
        "rain_probability": r.rain_probability,
        "wind_speed": r.wind_speed,
        "recommendation": r.recommendation,
    } for r in rows]

@app.post("/agent/chat")
async def chat(req: ChatRequest):
    CHAT.inc()
    with LAT.time():
        return {"answer": await answer(req.question)}
