"""
ChannelOS — TrendResearchAgent v2
Finds real, recent trends and generates brand-safe video ideas.

v2:
- Ancrage temporel: année courante injectée partout (queries Tavily + prompt)
- Garde-fou fraîcheur: interdiction de présenter comme "nouveau" ce qui n'est
  pas dans les trends récents
- Contrat list_items STRICT (noms nus) + validation/nettoyage côté code
"""

import os
import re
import json
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore

CACHE_DIR = Path("cache")
CACHE_TTL_HOURS = 24

RISKY_TERMS = [
    "scam", "fraud", "illegal", "hack", "crack", "pirate",
    "get rich quick", "100x", "guaranteed profit", "tax evasion",
    "conspiracy", "banned", "censored", "leaked",
]

HOOK_PATTERNS = [
    "question",        # "Did you know...?"
    "stat_shock",      # "90% of founders waste 10h/week on..."
    "list_tease",      # "5 AI tools that..."
    "before_after",    # "I used to spend 3h on X. Now it takes 10 min."
    "secret",          # "The tool big companies don't want you to know"
    "versus",          # "ChatGPT vs Claude for..."
    "time_pressure",   # "This free tool disappears in 30 days"
]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"trends_{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if datetime.fromisoformat(data["expires_at"]) < datetime.now():
        return None
    return data["payload"]


def _cache_set(key: str, payload: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"trends_{key}.json"
    path.write_text(json.dumps({
        "expires_at": (datetime.now() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
        "payload": payload,
    }, ensure_ascii=False))


# ── Trend search ──────────────────────────────────────────────────────────────

def search_trends(niche: str) -> list[dict]:
    """Run 3 Tavily basic searches for the niche (24h cached).
    L'année courante est injectée dynamiquement — jamais codée en dur."""
    year = datetime.now().year
    key = _cache_key(f"{niche}_{year}")  # le cache aussi est versionné par année
    cached = _cache_get(key)
    if cached:
        return cached

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        print("   ⚠️  TAVILY_API_KEY not set — skipping trend search")
        return []

    queries = [
        f"{niche} latest news {year}",
        f"best AI tools {niche} {year}",
        f"{niche} productivity automation tips",
    ]
    results = []
    for q in queries:
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": q,
                      "search_depth": "basic", "max_results": 5},
                timeout=15,
            )
            r.raise_for_status()
            results.extend(r.json().get("results", []))
        except Exception as e:
            print(f"   ⚠️  Tavily error for '{q}': {e}")

    _cache_set(key, results)
    return results


# ── list_items contract validation ───────────────────────────────────────────

_DECORATION_RE = re.compile(
    r"^[#\d\s\.\)\-—:→>•·]*"          # numérotation/puces/flèches en tête
)
_PRICE_SUFFIX_RE = re.compile(
    r"\s*[—\-–:→]\s*.*?\$\s*[\d,\.]+.*$"   # " — saves $800/mo" et variantes
)
_NON_ASCII_SYMBOLS_RE = re.compile(r"[^\w\s\.\-&/+']")


def _clean_list_item(item: str) -> str:
    """Nettoie un item: retire numérotation, prix, symboles exotiques."""
    s = str(item).strip()
    s = _DECORATION_RE.sub("", s)
    s = _PRICE_SUFFIX_RE.sub("", s)
    s = _NON_ASCII_SYMBOLS_RE.sub("", s)
    return s.strip()


def validate_ranking_items(idea: dict) -> bool:
    """Contrat list_items pour le format ranking:
    exactement 5 noms nus, 1-4 mots, non vides, distincts.
    Nettoie d'abord, valide ensuite. Renvoie False si irrécupérable."""
    if idea.get("format") != "ranking":
        return True
    raw = idea.get("list_items") or []
    cleaned = []
    for item in raw:
        s = str(item)
        # Un item dont la version brute contient un prix n'est pas un nom
        # d'outil — c'est une ligne de hook/bénéfice. On la rejette, on ne
        # la "nettoie" pas: le nettoyage produirait un faux nom ("Invoice").
        if "$" in s or "€" in s:
            continue
        c = _clean_list_item(s)
        if c and len(c.split()) <= 3:
            cleaned.append(c)
    # dédoublonnage en conservant l'ordre
    seen, items = set(), []
    for c in cleaned:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            items.append(c)
    if len(items) < 3:
        return False
    idea["list_items"] = items[:5]
    return True

# ── Idea generation ───────────────────────────────────────────────────────────

def generate_ideas(
    niche: str,
    language: str,
    trends: list[dict],
    n: int,
    niche_profile: dict,
    yt_insights: dict | None = None,
) -> list[dict]:
    """Call Claude Sonnet to generate n scored video ideas grounded in real trends."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today = datetime.now()
    year = today.year
    date_str = today.strftime("%B %d, %Y")

    trend_snippets = "\n".join(
        f"- {t.get('title', '')} | {t.get('url', '')} | {t.get('content', '')[:200]}"
        for t in trends[:15]
    )
    yt_block = ""
    if yt_insights:
        yt_block = f"""
YouTube top video patterns for this niche:
- Title patterns: {yt_insights.get('title_patterns', [])}
- Power words: {yt_insights.get('power_words', [])}
- Optimal duration: {yt_insights.get('optimal_duration_seconds', 'unknown')}s
- Tips: {yt_insights.get('actionable_tips', [])}
"""

    prompt = f"""You are a short-form video strategist for "{niche_profile['name']}".
Audience: {niche_profile['audience']}
Angles to prioritise: {niche_profile['angles']}
Affiliate partners: {niche_profile['affiliates']}
Language: {language}

TODAY'S DATE: {date_str}. The current year is {year}.

TEMPORAL RULES (strict):
- If a title mentions a year, it MUST be {year}. Never use past years.
- NEVER present a product/feature as "just launched", "just dropped", "new",
  or "breaking" unless its release is explicitly mentioned in the TREND DATA
  below. Products released in previous years are established tools — frame
  them by what they DO, not by their novelty.

REAL TREND DATA (last 14 days):
{trend_snippets}

{yt_block}

HOOK PATTERNS to use (pick the best fit per idea):
{HOOK_PATTERNS}

Generate {n} distinct short-form video ideas. Each idea MUST:
1. Be grounded in one of the real trends above (cite it in based_on_trend)
2. Use a realistic money angle ("saves $X/month", "replaces $Y/mo hire") — no hype
3. Lead naturally toward an affiliate (no hard sell)
4. Have a scroll-stopping hook (<12 words, specific, no clickbait)
5. Choose format: "ranking" (list), "versus" (comparison), or "single" (story)
6. Be brand-safe (factual, no sensationalism)

STRICT CONTRACT for "list_items" (ranking format only):
- EXACTLY 5 entries
- Each entry is the BARE product/tool name only: e.g. "Notion AI", "Make.com"
- 1 to 4 words per entry. NO numbering, NO prices, NO arrows, NO emojis,
  NO dashes-with-benefits, NO hook lines, NO intro/outro entries.
- BAD:  "#5 — Notion AI → $800/mo saved"
- GOOD: "Notion AI"
The spoken script will add numbers and benefits; list_items is used for
on-screen labels and B-roll search, so it must be clean names only.

Return ONLY valid JSON array, no markdown:
[
  {{
    "title": "...",
    "hook": "...",
    "angle": "...",
    "hook_pattern": "...",
    "format": "ranking|versus|single",
    "list_items": ["Notion AI", "Make.com", "Buffer", "HubSpot", "Mailchimp"],
    "versus": {{"a": "...", "b": "..."}},
    "structure": ["beat1", "beat2", "beat3"],
    "broll_query": "...",
    "affiliate_angle": "...",
    "based_on_trend": "...",
    "viral_score": 0-100,
    "score_reason": "...",
    "brand_safe": true
  }}
]"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    ideas = json.loads(raw)

    # Validation du contrat list_items — échec bruyant par idée, pas silencieux
    valid_ideas = []
    for idea in ideas:
        if validate_ranking_items(idea):
            valid_ideas.append(idea)
        else:
            print(f"   ⚠️  Idée rejetée (list_items irrécupérable): "
                  f"{idea.get('title', '?')[:50]}")

    return sorted(valid_ideas, key=lambda x: x.get("viral_score", 0), reverse=True)


# ── Brand safety ──────────────────────────────────────────────────────────────

def filter_brand_safety(ideas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Two-layer filter: ideas already flagged brand_safe=False + RISKY_TERMS scan."""
    safe, flagged = [], []
    for idea in ideas:
        if not idea.get("brand_safe", True):
            flagged.append(idea)
            continue
        text = " ".join([
            idea.get("title", ""), idea.get("hook", ""),
            idea.get("angle", ""), idea.get("affiliate_angle", ""),
        ]).lower()
        if any(term in text for term in RISKY_TERMS):
            idea["brand_safe"] = False
            flagged.append(idea)
        else:
            safe.append(idea)
    return safe, flagged

# ── Anti-clone: similarité de titres ─────────────────────────────────────────

_STOPWORDS = {"the", "a", "an", "in", "for", "of", "to", "and", "that", "are",
              "is", "your", "you", "with", "on", "how", "i", "my"}


def _title_tokens(title: str) -> set[str]:
    import re as _re
    words = _re.findall(r"[a-z0-9$]+", title.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def title_similarity(a: str, b: str) -> float:
    """Jaccard sur les mots significatifs. 0 = rien en commun, 1 = identiques."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def filter_already_used(ideas: list[dict], recent_titles: list[str],
                        threshold: float = 0.55) -> tuple[list[dict], list[dict]]:
    """Écarte les idées trop proches d'un titre déjà publié (14 derniers jours)."""
    fresh, dupes = [], []
    for idea in ideas:
        sim = max((title_similarity(idea.get("title", ""), t)
                   for t in recent_titles), default=0.0)
        (dupes if sim >= threshold else fresh).append(idea)
    return fresh, dupes
