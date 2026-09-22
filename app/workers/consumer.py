import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pika
from prometheus_client import Counter, Histogram, start_http_server
from sqlalchemy import select

from app.core.config import settings
from app.db.base import SessionLocal
from app.db.init_db import init_db
from app.models.entities import WeatherForecast
from app.services.ollama import weather_recommendation
from app.services.rabbit import DLX, EXCHANGE, connection, declare


logging.basicConfig(level=logging.INFO)

PROCESSED = Counter(
    "weather_messages_processed_total",
    "Processed weather messages",
)
FAILED = Counter(
    "weather_processing_failures_total",
    "Failed weather messages",
)
LLM_REQ = Counter(
    "llm_requests_total",
    "LLM requests",
    ["purpose"],
)
LLM_ERR = Counter(
    "llm_errors_total",
    "LLM errors",
    ["purpose"],
)
LLM_LAT = Histogram(
    "llm_request_duration_seconds",
    "LLM latency",
    ["purpose"],
)

# One worker keeps processing sequential and leaves the Pika I/O thread free
# to maintain RabbitMQ heartbeats while Ollama performs slow CPU inference.
executor = ThreadPoolExecutor(max_workers=1)


async def process(event: dict):
    with SessionLocal() as db:
        existing = db.scalar(
            select(WeatherForecast.id).where(
                WeatherForecast.event_id == event["event_id"]
            )
        )

        if existing:
            logging.info("Event %s already processed, skipping", event["event_id"])
            return

        try:
            LLM_REQ.labels("weather_recommendation").inc()
            with LLM_LAT.labels("weather_recommendation").time():
                recommendation = await weather_recommendation(event)
        except Exception:
            LLM_ERR.labels("weather_recommendation").inc()
            raise

        db.add(
            WeatherForecast(
                event_id=event["event_id"],
                city=event["city"],
                forecast_date=date.fromisoformat(event["forecast_date"]),
                temp_min=event["temp_min"],
                temp_max=event["temp_max"],
                rain_probability=event["rain_probability"],
                wind_speed=event["wind_speed"],
                weather_code=event["weather_code"],
                recommendation=recommendation,
            )
        )
        db.commit()

        logging.info(
            "Stored forecast for %s %s",
            event["city"],
            event["forecast_date"],
        )


def process_sync(event: dict):
    asyncio.run(process(event))


def main():
    init_db()

    conn = connection()
    ch = conn.channel()
    declare(ch)
    ch.basic_qos(prefetch_count=1)

    def callback(channel, method, properties, body):
        event = json.loads(body)
        retry = int((properties.headers or {}).get("x-retry-count", 0))

        logging.info(
            "Received event %s for %s",
            event.get("event_id"),
            event.get("city"),
        )

        future = executor.submit(process_sync, event)

        def finished(fut):
            def handle_result():
                try:
                    fut.result()
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    PROCESSED.inc()
                    logging.info("ACK event %s", event.get("event_id"))

                except Exception:
                    FAILED.inc()
                    logging.exception(
                        "Processing failed for %s",
                        event.get("event_id"),
                    )

                    if retry >= settings.max_retries:
                        logging.error(
                            "Max retries reached for %s. Sending to DLQ.",
                            event.get("event_id"),
                        )

                        channel.basic_publish(
                            exchange=DLX,
                            routing_key="dead",
                            body=body,
                            properties=pika.BasicProperties(
                                delivery_mode=pika.DeliveryMode.Persistent,
                                message_id=properties.message_id,
                                content_type="application/json",
                                headers={"x-retry-count": retry},
                            ),
                        )
                        channel.basic_ack(delivery_tag=method.delivery_tag)

                    else:
                        logging.warning(
                            "Retrying event %s. Retry %s/%s",
                            event.get("event_id"),
                            retry + 1,
                            settings.max_retries,
                        )

                        retry_properties = pika.BasicProperties(
                            delivery_mode=pika.DeliveryMode.Persistent,
                            message_id=properties.message_id,
                            content_type="application/json",
                            headers={"x-retry-count": retry + 1},
                        )

                        channel.basic_publish(
                            exchange=EXCHANGE,
                            routing_key="weather",
                            body=body,
                            properties=retry_properties,
                        )
                        channel.basic_ack(delivery_tag=method.delivery_tag)

            # Pika channel operations must execute on the connection thread.
            conn.add_callback_threadsafe(handle_result)

        future.add_done_callback(finished)

    ch.basic_consume(
        queue=settings.rabbitmq_queue,
        on_message_callback=callback,
        auto_ack=False,
    )

    logging.info("Consumer waiting for weather events")
    ch.start_consuming()


if __name__ == "__main__":
    start_http_server(9102)
    main()
