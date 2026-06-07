.PHONY: up down logs db-init costs run

# Exporte toutes les variables .env (gère les URLs avec = dans la valeur)
include .env
export

up:
	cd infra && docker compose up -d

down:
	cd infra && docker compose down

logs:
	cd infra && docker compose logs -f

db-init:
	python3 db.py init

costs:
	python3 db.py costs

run:
	python3 channelos.py "$(NICHE)"
