"""
ChannelOS — TrendResearchAgent
Finds real, recent trends and generates brand-safe video ideas.
Tools: Tavily API (3 basic searches, 24h cache)
Output: list of 5 scored ideas (JSON)
"""

import os
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

# Human-readable hook patterns passed to Claude's prompt
HOOK_PATTERNS_STR = (
        "question (\"Did you know...?\"), "
        "stat_shock (\"90% of founders waste 10h/week on...\"), "
        "list_tease (\"5 AI tools that...\"), "
        "before_after (\"I used to spend 3h on X. Now 10 min.\"), "
        "secret (\"The tool big companies don't want you to know\"), "
        "versus (\"ChatGPT vs Claude for...\"), "
        "time_pressure (\"This free tool disappears in 30 days\")"
)

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
        """
            Run 3 Tavily basic searches for the niche (24h cached).
                Returns a flat list of result dicts.
                    """
    key = _cache_key(niche)
    cached = _cache_get(key)
    if cached:
                return cached

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
                print(" ⚠️ TAVILY_API_KEY not set — skipping trend search")
                return []

    year = datetime.now().year
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
            print(f" ⚠️ Tavily error for '{q}': {e}")

    _cache_set(key, results)
    return results

# ── Idea generation ───────────────────────────────────────────────────────────

def generate_ideas(
        niche: str,
        language: str,
        trends: list[dict],
        n: int,
        niche_profile: dict,
        yt_insights: dict | None = None,
) -> list[dict]:
        """
            Call Claude Sonnet to generate n scored video ideas grounded in real trends.
                """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
                raise EnvironmentError(
                                "ANTHROPIC_API_KEY is not set. "
                                "Export it: export ANTHROPIC_API_KEY=sk-ant-..."
                )
            client = Anthropic(api_key=api_key)

    trend_snippets = "\n".join(
                f"- {t.get('title', '')} | {t.get('url', '')} | {t.get('content', '')[:200]}"
                for t in trends[:9]
    )

    yt_block = ""
    if yt_insights:
                yt_block = f"""
                YOUTUBE WINNING PATTERNS (last 90 days):
                - Title patterns: {yt_insights.get('title_patterns', [])}
                - Power words: {yt_insights.get('power_words', [])}
                - Optimal duration: {yt_insights.get('optimal_duration_seconds')}s
                - Tips: {yt_insights.get('actionable_tips', [])}
                """

    prompt = f"""You are a viral short-form video strategist for {language} TikTok/Reels.
    NICHE: {niche_profile.get('name')} — Audience: {niche_profile.get('audience')}
    ANGLES to exploit: {niche_profile.get('angles')}
    AFFILIATE partners: {niche_profile.get('affiliates')}

    REAL TREND DATA (last 14 days):
    {trend_snippets}

    {yt_block}

    HOOK PATTERNS to use (pick the best fit per idea):
    {HOOK_PATTERNS_STR}

    Generate {n} distinct short-form video ideas. Each idea MUST:
    1. Be grounded in one of the real trends above (cite it in based_on_trend)
    2. Use a realistic money angle ("saves $X/month", "replaces $Y/mo hire") — no hype
    3. Lead naturally toward an affiliate (no hard sell)
    4. Have a scroll-stopping hook (<12 words, specific, no clickbait)
    5. Choose format: "ranking" (list), "versus" (comparison), or "single" (story)
    6. Be brand-safe (factual, no sensationalism)

    Return ONLY valid JSON array, no markdown:
    [
      {{
          "title": "...",
              "hook": "...",
                  "angle": "...",
                      "hook_pattern": "...",
                          "format": "ranking|versus|single",
                              "list_items": ["item1", "item2", ...],
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
    try:
                ideas = json.loads(raw)
except json.JSONDecodeError as exc:
        raise ValueError(
                        f"Claude returned invalid JSON for ideas. "
                        f"Raw response (first 300 chars): {raw[:300]}"
        ) from exc
    return sorted(ideas, key=lambda x: x.get("viral_score", 0), reverse=True)

# ── Brand safety ──────────────────────────────────────────────────────────────

def filter_brand_safety(ideas: list[dict]) -> tuple[list[dict], list[dict]]:
        """
            Two-layer filter: ideas already flagged brand_safe=False + RISKY_TERMS code scan.
                Returns (safe_ideas, flagged_ideas).
                    """
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
