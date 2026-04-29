.PHONY: dev-up dev-down dev-logs dev-reset test lint

dev-up:
	docker compose up -d
	docker compose ps

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

dev-reset:
	docker compose down -v
	docker compose up -d

test:
	pytest -q

lint:
	black --check ats tests
	isort --check-only ats tests
	flake8 ats tests
	mypy --strict ats
