import httpx

from app.core.config import settings


async def generate(prompt: str) -> str:
    """Generate a concise answer with the locally hosted Ollama model."""
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 250,
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

        data = response.json()
        answer = data.get("response", "").strip()

        if not answer:
            raise RuntimeError("Ollama returned an empty response")

        return answer


async def weather_recommendation(event: dict) -> str:
    prompt = f"""You are a concise outdoor activity advisor.

Activity: {settings.activity}
City: {event['city']}
Date: {event['forecast_date']}
Temperature: {event['temp_min']} to {event['temp_max']} C
Rain probability: {event['rain_probability']}%
Wind: {event['wind_speed']} km/h
Weather code: {event['weather_code']}

Return only the final recommendation.
Use only the supplied weather facts.
Do not explain your reasoning.
Maximum 2 sentences.
"""
    return await generate(prompt)
