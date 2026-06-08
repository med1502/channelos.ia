# ChannelOS IA — Documentation

Automated short-form video pipeline: one command → one TikTok/Reels-ready MP4.

```
niche query → Tavily trends → Claude ideas → Claude script → Pexels B-roll → JSON2Video render → MP4
```

---

## Prerequisites

- Python 3.10+
- Docker (for PostgreSQL)
- API keys: Anthropic, JSON2Video, Pexels, Tavily (YouTube optional)

---

## Installation

```bash
git clone https://github.com/med1502/channelos.ia
cd channelos.ia

# Fix all files and run tests (run once after clone or pull)
python3 fix_phase1.py

# Copy and fill your API keys
cp .env.example .env
nano .env

# Install Python dependencies
pip install -r requirements.txt

# Start PostgreSQL
make up

# Create database schema
make db-init
```

---

## .env keys

```bash
ANTHROPIC_API_KEY=sk-ant-...        # Required — ideas + script
JSON2VIDEO_API_KEY=...               # Required — video render
PEXELS_API_KEY=...                   # Required — B-roll footage
TAVILY_API_KEY=tvly-...              # Required — trend research
YOUTUBE_API_KEY=...                  # Optional — title pattern analysis
DATABASE_URL=postgresql://channelos:channelos@localhost:5432/channelos
```

---

## Quickstart

```bash
make run        # EN video, ai_entrepreneurs niche
make run-fr     # FR video, ai_entrepreneurs niche
make ideas      # ideas only, no video rendered
```

---

## CLI reference

```
python3 -m channelos "<niche query>" [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--niche-profile` | `ai_entrepreneurs` | Niche profile key (see below) |
| `--lang` | `EN` | Language: `EN` or `FR` |
| `--pick N` | `1` | Produce idea #N (1 = highest viral score) |
| `--ideas-only` | off | Stop after ideas, skip render |
| `--n N` | `5` | Number of ideas to generate |
| `--batch N` | off | Produce N videos sequentially (ideas 1..N) |

### Examples

```bash
# Basic run — top-scored idea
python3 -m channelos "AI tools for entrepreneurs"

# French video on e-commerce niche
python3 -m channelos "outils IA pour e-commerce" \
  --niche-profile ai_ecommerce --lang FR

# Just browse ideas, no API cost for video
python3 -m channelos "AI tools" --ideas-only --n 10

# Pick idea #3 manually
python3 -m channelos "AI tools" --pick 3

# Batch: produce 5 videos in one run
python3 -m channelos "AI tools" --batch 5

# Finance niche, French
python3 -m channelos "investissement IA 2024" \
  --niche-profile ai_finance --lang FR
```

---

## Niche profiles

| Key | Name | Languages |
|-----|------|-----------|
| `ai_entrepreneurs` | AI Tools for Entrepreneurs | EN, FR |
| `ai_ecommerce` | AI for E-commerce | EN |
| `ai_freelancers` | AI for Freelancers & Creators | EN, FR |
| `ai_startups` | AI for Startups & Investors | EN |
| `ai_finance` | AI & Personal Finance | EN, FR |

Each profile defines: audience, angles, affiliate partners, Azure TTS voice, hashtags.
Add custom profiles in `channelos/config/niches.py`.

---

## Output files

After a successful run, `output/` contains:

```
output/
├── video.mp4           # Final rendered video (1080×1920 portrait)
├── post_package.json   # Caption, hashtags, affiliate angle, video URL
└── ideas.json          # All generated ideas with viral scores
```

`post_package.json` structure:
```json
{
  "title": "Top 5 AI tools that save founders 10h/week",
  "caption": "Stop wasting time on manual tasks...",
  "hashtags": ["#AITools", "#Entrepreneur", "#Productivity"],
  "affiliate_angle": "Start with Notion AI free — link in bio",
  "based_on_trend": "Buffer raises $...",
  "viral_score": 87,
  "video_url": "https://cdn.json2video.com/..."
}
```

---

## Video formats

ChannelOS generates three formats based on the idea:

| Format | Structure | B-roll |
|--------|-----------|--------|
| `ranking` | Countdown (#5 → #1), cyan rank overlay per scene | One clip per item |
| `versus` | A vs B setup → verdict | Single clip |
| `single` | Hook → story → CTA | Single clip |

---

## Make targets

```bash
make run          # Produce one EN video (ai_entrepreneurs)
make run-fr       # Produce one FR video (ai_entrepreneurs)
make ideas        # Ideas only, no render
make batch        # Produce 3 videos in sequence
make test         # Run 25 unit tests (no API keys required)
make db-init      # Create PostgreSQL schema
make costs        # Print cost report per video
make up           # Start Docker services (PostgreSQL)
make down         # Stop Docker services
make install      # pip install -r requirements.txt
make clean        # Remove __pycache__, .pyc, .coverage
```

---

## Pipeline internals

```
main.py
│
├── agents/trend_agent.py       TrendResearchAgent
│   ├── search_trends()         → 3 Tavily searches, 24h cache
│   ├── generate_ideas()        → Claude Sonnet, returns 5 scored ideas
│   └── filter_brand_safety()   → blocks scam/fraud/hype terms
│
├── agents/youtube_agent.py     YouTubeTrendsAgent (optional)
│   └── get_youtube_insights()  → top video patterns, title formats
│
├── agents/script_agent.py      ScriptWriter
│   └── write_script()          → Claude Sonnet, 55-70 words, JSON output
│
├── pipeline/render.py          VideoProducer
│   ├── fetch_broll()           → single Pexels clip
│   ├── fetch_broll_multi()     → one clip per ranking item, deduplicated
│   ├── render_video()          → JSON2Video: hook scene + content scenes + subtitles
│   └── download_video()        → saves MP4 locally
│
├── pipeline/publisher.py       PublisherAgent (stub — Phase 2)
│
└── db/client.py                Persistence + cost tracking
    ├── save_idea()
    ├── save_video()
    └── log_cost() / log_anthropic()
```

---

## Cost estimation

Approximate cost per video at current API pricing:

| Provider | Operation | Typical cost |
|----------|-----------|-------------|
| Anthropic | Ideas (Claude Sonnet) | ~$0.015 |
| Anthropic | Script (Claude Sonnet) | ~$0.005 |
| Tavily | 3 basic searches | ~$0.024 |
| JSON2Video | ~30s render | ~$0.120 |
| Pexels | B-roll fetch | $0.000 |
| **Total** | | **~$0.16/video** |

View your actual costs: `make costs`

---

## Testing

Tests use Python's `unittest` stdlib — no pip install needed.

```bash
make test
# Ran 25 tests in ~0.1s — OK
```

Test coverage:

| File | Tests | What's covered |
|------|-------|----------------|
| `test_trend_agent.py` | 9 | Brand safety filter, Tavily cache, idea sorting |
| `test_script_agent.py` | 7 | Word count ≤70, required keys, all 3 formats |
| `test_render.py` | 9 | URL validation, render error, ranking multi-scene, B-roll dedup, rank overlay |

All external APIs are mocked — tests run offline.

---

## Troubleshooting

**`IndentationError` or `SyntaxError` on any file**
```bash
python3 fix_phase1.py   # rewrites all files + purges __pycache__
```

**`ModuleNotFoundError: No module named 'channelos.pipeline'`**
```bash
python3 fix_phase1.py   # recreates missing __init__.py files
```

**`pip install -e .` fails with `No module named 'setuptools.backends'`**
```bash
pip install --upgrade pip setuptools
pip install -e .
# Or skip install -e . entirely — make test works without it
```

**Video renders but no sound**
Azure TTS requires `JSON2VIDEO_API_KEY` to be valid and the voice name to be exact. Check `channelos/config/niches.py` for the voice string per niche/language.

**Tavily returns 0 results**
Check `TAVILY_API_KEY` in `.env`. The cache is at `cache/trends_*.json` — delete cache files to force a fresh search.

---

## Project structure

```
channelos.ia/
├── .env.example
├── .gitignore
├── Makefile
├── pyproject.toml
├── requirements.txt
├── setup.py
├── fix_phase1.py          ← run after clone/pull to fix any corruption
│
├── channelos/
│   ├── main.py            ← CLI entrypoint + orchestrator
│   ├── agents/
│   │   ├── trend_agent.py
│   │   ├── script_agent.py
│   │   └── youtube_agent.py
│   ├── config/
│   │   └── niches.py
│   ├── db/
│   │   ├── client.py
│   │   └── schema.sql
│   ├── pipeline/
│   │   ├── render.py
│   │   └── publisher.py   ← stub (Phase 2)
│   └── tests/
│       ├── test_render.py
│       ├── test_script_agent.py
│       └── test_trend_agent.py
│
├── infra/
│   └── docker-compose.yml
│
├── cache/                 ← auto-created, gitignored
└── output/                ← auto-created, gitignored
```