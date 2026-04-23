.PHONY: up down logs test frontend-test migrate run-once purge-demo-data fmt

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker inspector migrate

migrate:
	docker compose run --rm migrate

run-once:
	docker compose run --rm worker python -m scripts.run_pipeline_once

purge-demo-data:
	docker compose exec api python scripts/purge_demo_data.py

test:
	pytest -q

frontend-test:
	cd frontend && npm test
