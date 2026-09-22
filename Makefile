up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f producer consumer api

test:
	pytest -q

ps:
	docker compose ps
