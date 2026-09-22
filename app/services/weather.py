from datetime import datetime, timezone
import httpx

CITIES = {
    "Rome": (41.9028, 12.4964),
    "London": (51.5072, -0.1276),
    "Tel Aviv": (32.0853, 34.7818),
    "Budapest": (47.4979, 19.0402),
    "Lisbon": (38.7223, -9.1393),
}

DAILY = "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,wind_speed_10m_max"

async def fetch_city_forecast(city: str) -> list[dict]:
    lat, lon = CITIES[city]
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": DAILY,
        "timezone": "auto",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
        r.raise_for_status()
        d = r.json()["daily"]
    out = []
    for i, forecast_date in enumerate(d["time"]):
        out.append({
            "city": city,
            "forecast_date": forecast_date,
            "temp_max": d["temperature_2m_max"][i],
            "temp_min": d["temperature_2m_min"][i],
            "rain_probability": d["precipitation_probability_max"][i] or 0,
            "weather_code": d["weather_code"][i],
            "wind_speed": d["wind_speed_10m_max"][i],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return out
