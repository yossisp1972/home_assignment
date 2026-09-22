import json
import pika
from app.core.config import settings

EXCHANGE = "weather.exchange"
DLX = "weather.dlx"

def connection():
    return pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))

def declare(ch):
    ch.exchange_declare(EXCHANGE, "direct", durable=True)
    ch.exchange_declare(DLX, "direct", durable=True)
    ch.queue_declare(settings.rabbitmq_dlq, durable=True)
    ch.queue_bind(settings.rabbitmq_dlq, DLX, routing_key="dead")
    ch.queue_declare(
        settings.rabbitmq_queue,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": "dead"},
    )
    ch.queue_bind(settings.rabbitmq_queue, EXCHANGE, routing_key="weather")

def publish(event: dict):
    conn = connection()
    ch = conn.channel()
    declare(ch)
    ch.confirm_delivery()
    ok = ch.basic_publish(
        exchange=EXCHANGE,
        routing_key="weather",
        body=json.dumps(event).encode(),
        properties=pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=event["event_id"],
            content_type="application/json",
            headers={"x-retry-count": event.get("retry_count", 0)},
        ),
        mandatory=True,
    )
    conn.close()
    if not ok:
        raise RuntimeError("RabbitMQ publisher confirm failed")
