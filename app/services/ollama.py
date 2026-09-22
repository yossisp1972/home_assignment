import httpx

from app.core.config import settings


async def generate(prompt: str) -> str:
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 120,
            "temperature": 0.2,
        },
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=300.0,
        write=30.0,
        pool=10.0,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.ollama_url}/api/generate",
            json=payload,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()


async def weather_recommendation(event: dict) -> str:
    prompt = f"""You are a concise outdoor activity advisor.

Activity: {settings.activity}
City: {event['city']}
Date: {event['forecast_date']}
Temperature: {event['temp_min']} to {event['temp_max']} C
Rain probability: {event['rain_probability']}%
Wind: {event['wind_speed']} km/h
Weather code: {event['weather_code']}

Give a maximum 2-sentence recommendation.
Use only the supplied weather facts.
Do not invent information and do not explain your reasoning process.
"""
    return await generate(prompt)
