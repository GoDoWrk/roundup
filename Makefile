.PHONY: up down logs test migrate run-once fmt

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker

migrate:
	docker compose run --rm api alembic upgrade head

run-once:
	docker compose run --rm worker python -m scripts.run_pipeline_once

test:
	pytest -q
