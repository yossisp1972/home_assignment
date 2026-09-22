import asyncio
import json
import logging
from datetime import date
import pika
from sqlalchemy import select
from prometheus_client import Counter, Histogram, start_http_server
from app.core.config import settings
from app.db.base import SessionLocal
from app.db.init_db import init_db
from app.models.entities import WeatherForecast
from app.services.ollama import weather_recommendation
from app.services.rabbit import connection, declare, DLX

logging.basicConfig(level=logging.INFO)
PROCESSED = Counter("weather_messages_processed_total", "Processed weather messages")
FAILED = Counter("weather_processing_failures_total", "Failed weather messages")
LLM_REQ = Counter("llm_requests_total", "LLM requests", ["purpose"])
LLM_ERR = Counter("llm_errors_total", "LLM errors", ["purpose"])
LLM_LAT = Histogram("llm_request_duration_seconds", "LLM latency", ["purpose"])

async def process(event: dict):
    with SessionLocal() as db:
        if db.scalar(select(WeatherForecast.id).where(WeatherForecast.event_id == event["event_id"])):
            return
        try:
            LLM_REQ.labels("weather_recommendation").inc()
            with LLM_LAT.labels("weather_recommendation").time():
                recommendation = await weather_recommendation(event)
        except Exception:
            LLM_ERR.labels("weather_recommendation").inc()
            raise
        db.add(WeatherForecast(
            event_id=event["event_id"], city=event["city"],
            forecast_date=date.fromisoformat(event["forecast_date"]),
            temp_min=event["temp_min"], temp_max=event["temp_max"],
            rain_probability=event["rain_probability"], wind_speed=event["wind_speed"],
            weather_code=event["weather_code"], recommendation=recommendation,
        ))
        db.commit()

def main():
    init_db()
    conn = connection()
    ch = conn.channel()
    declare(ch)
    ch.basic_qos(prefetch_count=1)

    def callback(channel, method, properties, body):
        event = json.loads(body)
        retry = int((properties.headers or {}).get("x-retry-count", 0))
        try:
            asyncio.run(process(event))
            channel.basic_ack(method.delivery_tag)
            PROCESSED.inc()
        except Exception:
            FAILED.inc()
            logging.exception("processing failed for %s", event.get("event_id"))
            if retry >= settings.max_retries:
                channel.basic_publish(
                    exchange=DLX,
                    routing_key="dead",
                    body=body,
                    properties=pika.BasicProperties(delivery_mode=2, headers={"x-retry-count": retry}),
                )
                channel.basic_ack(method.delivery_tag)
            else:
                props = pika.BasicProperties(
                    delivery_mode=2,
                    message_id=properties.message_id,
                    content_type="application/json",
                    headers={"x-retry-count": retry + 1},
                )
                channel.basic_publish("weather.exchange", "weather", body=body, properties=props)
                channel.basic_ack(method.delivery_tag)

    ch.basic_consume(settings.rabbitmq_queue, callback, auto_ack=False)
    ch.start_consuming()

if __name__ == "__main__":
    start_http_server(9102)
    main()
