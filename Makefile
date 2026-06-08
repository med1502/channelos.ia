.PHONY: up down run run-fr ideas batch costs test test-cov db-init install setup-dev clean

PYTHON  = python3
COMPOSE = docker compose -f channelos/infra/docker-compose.yml

# ── Infrastructure ────────────────────────────────────────────────────────────
up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

# ── Pipeline ──────────────────────────────────────────────────────────────────
run:
	$(PYTHON) -m channelos "AI tools for entrepreneurs" \
	  --niche-profile ai_entrepreneurs --lang EN

run-fr:
	$(PYTHON) -m channelos "outils IA pour entrepreneurs" \
	  --niche-profile ai_entrepreneurs --lang FR

ideas:
	$(PYTHON) -m channelos "AI tools for entrepreneurs" --ideas-only

batch:
	$(PYTHON) -m channelos "AI tools for entrepreneurs" --batch 3

# ── Database ──────────────────────────────────────────────────────────────────
db-init:
	$(PYTHON) -m channelos.db init

costs:
	$(PYTHON) -m channelos.db costs

# ── Tests — stdlib unittest, zero pip required ────────────────────────────────
test:
	$(PYTHON) -m unittest discover -s channelos/tests -p "test_*.py" -v

test-pytest:
	$(PYTHON) -m pytest channelos/tests/ -v --tb=short

test-cov:
	$(PYTHON) -m pytest channelos/tests/ -v --tb=short \
	  --cov=channelos --cov-report=term-missing

# ── Dependencies ──────────────────────────────────────────────────────────────
install:
	$(PYTHON) -m pip install -r requirements.txt

setup-dev:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install pytest pytest-mock pytest-cov

# ── Housekeeping ──────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .coverage
