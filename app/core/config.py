from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://weather:weather@postgres:5432/weatherdb"
    rabbitmq_url: str = "amqp://weather:weather@rabbitmq:5672/%2F"
    rabbitmq_queue: str = "weather.events"
    rabbitmq_dlq: str = "weather.events.dlq"
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b"
    weather_update_minutes: int = 30
    max_retries: int = 5
    activity: str = "running"
    api_url: str = "http://api:8000"

settings = Settings()
