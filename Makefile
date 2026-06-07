.PHONY: up down run run-fr ideas costs test test-cov install setup-dev clean

PYTHON = python3

# ── Infrastructure ────────────────────────────────────────────────────────────
up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

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
	$(PYTHON) -m channelos.db.client init

costs:
	$(PYTHON) -m channelos.db.client costs

# ── Tests — stdlib unittest, zero pip required ────────────────────────────────
# Works out-of-the-box on any Python 3.10+ install.
# For richer output (pytest), run: make install && make test-pytest
test:
	$(PYTHON) -m unittest discover -s channelos/tests -p "test_*.py" -v

# Optional: pytest (requires: make install first)
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

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .coverage
