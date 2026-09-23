# On-Prem Weather & Travel Agent

A containerized weather and travel recommendation system designed to run on-prem with restricted internet access. External connectivity is needed only for weather synchronization and optional tourism/event updates; inference and user queries run locally.

## Architecture

```text
                               INTERNET
                                   |
                            restricted egress
                                   |
                                   v
                              Open-Meteo
                                   |
                                   v
                           Weather Producer
                                   |
========================== ON-PREM ==================================
                                   |
                                   v
                              RabbitMQ
                             /        \
                            /          \
                           v            v
                     Weather Queue      DLQ
                           |
                           v
                    Weather Consumer
                       |        |
                       |        +-------> Ollama / Qwen
                       |
                       v
                    PostgreSQL
                       ^
                       |
                  Agent Harness
                   |         |
                   |         +----------> Ollama / Qwen
                   v
                  FastAPI
                     |
                     v
                Streamlit UI

        FastAPI / Consumer / Producer
                       |
                       v
                   Prometheus
                       |
                       v
                     Grafana
```

## Why these technologies

- **Open-Meteo**: simple external weather source for five cities.
- **RabbitMQ**: durable asynchronous ingestion, publisher confirms, manual acknowledgements and a DLQ.
- **PostgreSQL**: durable local source of truth for weather, tourism knowledge, events and recommendations.
- **Ollama + Qwen2.5 3B Instruct**: local open-weight LLM inference with no external LLM API.
- **FastAPI**: agent/query API.
- **Streamlit**: fast dashboard and chat UX.
- **Prometheus + Grafana**: bonus observability.
- **Docker Compose**: one-command on-prem deployment.

## Reliability model

The producer publishes persistent RabbitMQ messages with publisher confirms. The consumer uses manual ACKs and acknowledges a message only after processing and database commit. Failed messages are retried and then routed to a DLQ. Each event has a unique `event_id`, so redelivery does not create duplicate records.

## Offline behavior

The system separates online synchronization from offline inference. Weather is synchronized while outbound internet is available. Once stored locally, the agent can answer questions using PostgreSQL and the local Ollama model without internet access. Tourism knowledge is seeded locally. Event data can be synchronized/imported and the agent is instructed not to invent missing current events.

## Run

Requirements: Docker + Docker Compose, preferably at least 8 GB RAM for comfortable local LLM use.

```bash
cp .env.example .env
docker compose up -d --build
```

Watch model initialization:

```bash
docker compose logs -f ollama-init
```

Then check:

```bash
docker compose ps
docker compose logs -f producer consumer api
```

## Accessing the application

Docker Compose publishes the following service ports:

| Service | Port |
| --- | ---: |
| Streamlit UI | 8501 |
| FastAPI | 8000 |
| Grafana | 3000 |
| Prometheus | 9090 |
| RabbitMQ Management | 15672 |

### Local deployment

When Docker Compose is running on the same machine as your browser:

- Streamlit: `http://localhost:8501`
- FastAPI docs: `http://localhost:8000/docs`
- RabbitMQ UI: `http://localhost:15672` (`weather` / `weather`)
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

### Remote or on-prem server

When the stack runs on a remote Linux or on-prem server, access can be provided through the organization's internal network/reverse proxy, or securely through SSH port forwarding.

Example:

```bash
ssh \
  -L 8501:localhost:8501 \
  -L 8000:localhost:8000 \
  -L 3000:localhost:3000 \
  user@SERVER_IP
```

After the tunnel is established, open from the local workstation:

- Streamlit: `http://localhost:8501`
- FastAPI docs: `http://localhost:8000/docs`
- Grafana: `http://localhost:3000`

For a production on-prem deployment, these services would normally be exposed through the internal network, DNS, TLS and a reverse proxy/load balancer rather than exposing container ports directly to the public Internet.

## Example questions

- `What is the weather tomorrow in Rome?`
- `What activities can I do with my wife this week in London? We like concerts, shopping and fine dining.`
- `Plan a one-day outdoor itinerary in Lisbon.`
- `Should I run tomorrow in Tel Aviv?`

## Main data flow

1. Producer fetches seven-day forecasts for Rome, London, Tel Aviv, Budapest and Lisbon.
2. Each forecast row is published to RabbitMQ.
3. Consumer reads from the queue and asks the local LLM for an activity recommendation.
4. Consumer writes the enriched record to PostgreSQL and then ACKs the queue message.
5. Agent detects the relevant supported city and retrieves targeted local weather, tourism and event context from PostgreSQL.
6. Agent sends the bounded local context plus the user question to the local LLM.
7. FastAPI returns the answer to Streamlit.

## Data update

Weather refresh interval is configured with `WEATHER_UPDATE_MINUTES` (default `360`, or six hours). Restarting the producer also triggers an immediate collection cycle.

Tourism seed data lives in `data/city_knowledge.json`. Event seed/import data lives in `data/events.json`.

## Failure scenarios

- **Open-Meteo unavailable**: existing local data remains queryable; producer retries next scheduled cycle.
- **PostgreSQL temporarily unavailable**: consumer processing fails and the queue message is not lost.
- **Ollama temporarily unavailable**: consumer retries; repeated failures are sent to the DLQ.
- **Consumer crash after DB commit**: RabbitMQ may redeliver, but `event_id` idempotency prevents duplicates.
- **Internet unavailable**: local agent, DB, LLM, API and UI continue to operate on synchronized data.

## Observability

Metrics include:

- `weather_messages_published_total`
- `weather_collection_failures_total`
- `weather_messages_processed_total`
- `weather_processing_failures_total`
- `llm_requests_total`
- `llm_errors_total`
- `llm_request_duration_seconds`
- `agent_requests_total`
- `agent_request_duration_seconds`

## CI/CD

GitHub Actions runs:

1. dependency installation
2. unit tests
3. Docker Compose configuration validation
4. Docker image build

The workflow is in `.github/workflows/ci.yml`.

## Repository structure

```text
app/
  api/            FastAPI
  core/           configuration
  db/             SQLAlchemy engine + DB bootstrap
  models/         database models
  services/       weather, RabbitMQ, Ollama, agent
  workers/        producer and consumer
  ui/             Streamlit

data/             local tourism/event seed data
prometheus/        Prometheus config
grafana/           Grafana datasource provisioning
tests/             unit tests
.github/workflows/ GitHub Actions
```

## Trade-offs

For only five cities, the system uses structured PostgreSQL retrieval instead of adding a vector database. This reduces operational complexity and keeps the submission easy to run on-prem. If the knowledge base becomes large, PostgreSQL can be extended with pgvector without adding a separate database.

The reference configuration uses `qwen2.5:3b-instruct` to keep CPU/RAM requirements reasonable while preserving useful instruction-following behavior. The model name is configurable through `OLLAMA_MODEL`, so GPU-backed installations can select a larger model without changing the application code.

## Validation notes

The stack was validated end-to-end on a Linux EC2 host using Docker Compose. AWS is not a runtime dependency; EC2 was used only as a convenient Linux test host, and the same Compose stack can run on an on-prem Linux server.

During validation, the following flow was confirmed:

1. Open-Meteo returned forecast data for the configured cities.
2. The producer published persistent events to RabbitMQ.
3. The consumer processed events with manual acknowledgements and generated recommendations through local Ollama/Qwen inference.
4. Enriched forecast records were committed to PostgreSQL.
5. FastAPI and Streamlit served the synchronized data and agent interface.

On CPU-only hosts, local inference can be slow. The reference deployment was validated with `qwen2.5:3b-instruct` through Ollama. `OLLAMA_MODEL` is configurable in `.env`, so GPU-backed on-prem systems can use a larger model without changing the architecture.
