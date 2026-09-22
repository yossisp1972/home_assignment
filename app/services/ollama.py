import httpx

from app.core.config import settings


async def generate(prompt: str) -> str:
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
            raise RuntimeError(
                f"Ollama returned an empty response: {data}"
            )

        return answer
