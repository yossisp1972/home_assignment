import httpx
from app.core.config import settings

async def generate(prompt: str) -> str:
    payload = {"model": settings.ollama_model, "prompt": prompt, "stream": False}
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
        r.raise_for_status()
        return r.json().get("response", "").strip()

async def weather_recommendation(event: dict) -> str:
    prompt = f"""You are a concise outdoor activity advisor.
Activity: {settings.activity}
City: {event['city']}
Date: {event['forecast_date']}
Temperature: {event['temp_min']} to {event['temp_max']} C
Rain probability: {event['rain_probability']}%
Wind: {event['wind_speed']} km/h
Weather code: {event['weather_code']}
Give a 2-3 sentence recommendation whether conditions are suitable. Use only these facts."""
    return await generate(prompt)
