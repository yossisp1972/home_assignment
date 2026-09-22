import json

import pika
from pika.exceptions import NackError, UnroutableError

from app.core.config import settings


EXCHANGE = "weather.exchange"
DLX = "weather.dlx"


def connection():
    return pika.BlockingConnection(
        pika.URLParameters(settings.rabbitmq_url)
    )


def declare(ch):
    ch.exchange_declare(
        exchange=EXCHANGE,
        exchange_type="direct",
        durable=True,
    )

    ch.exchange_declare(
        exchange=DLX,
        exchange_type="direct",
        durable=True,
    )

    ch.queue_declare(
        queue=settings.rabbitmq_dlq,
        durable=True,
    )

    ch.queue_bind(
        queue=settings.rabbitmq_dlq,
        exchange=DLX,
        routing_key="dead",
    )

    ch.queue_declare(
        queue=settings.rabbitmq_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX,
            "x-dead-letter-routing-key": "dead",
        },
    )

    ch.queue_bind(
        queue=settings.rabbitmq_queue,
        exchange=EXCHANGE,
        routing_key="weather",
    )


def publish(event: dict):
    conn = connection()

    try:
        ch = conn.channel()
        declare(ch)
        ch.confirm_delivery()

        ch.basic_publish(
            exchange=EXCHANGE,
            routing_key="weather",
            body=json.dumps(event).encode(),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                message_id=event["event_id"],
                content_type="application/json",
                headers={
                    "x-retry-count": event.get("retry_count", 0),
                },
            ),
            mandatory=True,
        )

    except (NackError, UnroutableError):
        raise

    finally:
        if conn.is_open:
            conn.close()
