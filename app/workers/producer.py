import asyncio
import logging
import uuid
from apscheduler.schedulers.blocking import BlockingScheduler
from prometheus_client import Counter, start_http_server
from app.core.config import settings
from app.services.rabbit import publish
from app.services.weather import CITIES, fetch_city_forecast

logging.basicConfig(level=logging.INFO)
PUBLISHED = Counter("weather_messages_published_total", "Published weather messages")
FAILURES = Counter("weather_collection_failures_total", "Weather collection failures")

async def collect_once():
    for city in CITIES:
        try:
            rows = await fetch_city_forecast(city)
            for row in rows:
                row["event_id"] = str(uuid.uuid4())
                publish(row)
                PUBLISHED.inc()
            logging.info("published %s forecast rows for %s", len(rows), city)
        except Exception:
            FAILURES.inc()
            logging.exception("collection failed for %s", city)

def job():
    asyncio.run(collect_once())

if __name__ == "__main__":
    start_http_server(9101)
    job()
    scheduler = BlockingScheduler()
    scheduler.add_job(job, "interval", minutes=settings.weather_update_minutes, max_instances=1, coalesce=True)
    scheduler.start()
