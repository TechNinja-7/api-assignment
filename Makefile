# Makefile

.PHONY: help install run-local up down logs test

help:
	@echo "Available targets:"
	@echo "  make install    - Install Python dependencies"
	@echo "  make run-local  - Run app locally with uvicorn"
	@echo "  make up         - Start Docker Compose (build + run)"
	@echo "  make down       - Stop Docker Compose and remove volumes"
	@echo "  make logs       - Follow Docker logs for api service"
	@echo "  make test       - Run pytest tests"

install:
	pip install -r requirements.txt

run-local:
	@echo "Make sure to set DATABASE_URL, WEBHOOK_SECRET, LOG_LEVEL before running."
	uvicorn app.main:app --reload

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	pytest tests/ -v
