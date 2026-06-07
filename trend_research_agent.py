"""
ChannelOS — TrendResearchAgent
==============================
Le CŒUR de ChannelOS : trouve des idées de contenu ANCRÉES dans des
tendances réelles, pas hallucinées.

Flux :
  1. Tavily   → recherche web temps réel (ce qui buzze MAINTENANT dans la niche)
  2. Claude   → analyse ces données réelles + génère des idées COMPLÈTES
                prêtes à scripter (hook + angle + structure + broll + score)
  3. Sortie   → JSON directement consommable par le pipeline vidéo v7

Clés requises :
  ANTHROPIC_API_KEY
  TAVILY_API_KEY    (gratuit : 1000 crédits/mois)

Optimisation coût : recherche BASIQUE (1 crédit), pas l'endpoint Research
(qui peut coûter ~250 crédits). Cache 24h pour éviter les requêtes répétées.
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime, timedelta

NICHE = sys.argv[1] if len(sys.argv) > 1 else "AI tools for entrepreneurs"
LANGUAGE = "EN"
N_IDEAS = 5
OUTPUT_DIR = "output"
CACHE_DIR = "cache"
CACHE_TTL_HOURS = 24
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────
# 1 — TENDANCES RÉELLES via Tavily (avec cache 24h)
# ─────────────────────────────────────────────────────────
def search_trends(niche: str) -> list:
    """
    Recherche web ciblée sur ce qui est récent/tendance dans la niche.
    Plusieurs requêtes complémentaires pour couvrir différents angles.
    Mise en cache 24h pour économiser les crédits.
    """
    from tavily import TavilyClient

    # Cache : éviter de re-payer pour la même niche dans les 24h
    cache_key = hashlib.md5(niche.encode()).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"trends_{cache_key}.json")
    if os.path.exists(cache_file):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if age < timedelta(hours=CACHE_TTL_HOURS):
            print("   (cache hit — 0 crédit consommé)")
            with open(cache_file) as f:
                return json.load(f)

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    # Requêtes complémentaires — angles différents pour des tendances riches
    queries = [
        f"latest {niche} trends this week",
        f"new {niche} viral",
        f"best {niche} 2026",
    ]

    results = []
    for q in queries:
        try:
            resp = client.search(
                query=q,
                search_depth="basic",       # 1 crédit (pas "advanced")
                max_results=5,
                topic="news",               # priorise le récent
                days=14,                    # fenêtre fraîche : 2 semaines
            )
            for r in resp.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", "")[:500],  # limiter le bruit
                    "url": r.get("url", ""),
                })
        except Exception as e:
            print(f"   ⚠️ requête '{q}' échouée : {e}")

    # Dédupliquer par titre
    seen = set()
    deduped = []
    for r in results:
        if r["title"] and r["title"] not in seen:
            seen.add(r["title"])
            deduped.append(r)

    with open(cache_file, "w") as f:
        json.dump(deduped, f, ensure_ascii=False)

    return deduped


# ─────────────────────────────────────────────────────────
# 2 — IDÉES COMPLÈTES via Claude (ancrées dans les données réelles)
# ─────────────────────────────────────────────────────────
def generate_ideas(niche: str, language: str, trends: list, n: int, niche_profile: dict = None, yt_insights: dict = None) -> list:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Compacter les tendances en contexte pour Claude
    trend_context = "\n".join(
        f"- {t['title']}: {t['content']}" for t in trends[:12]
    ) or "No fresh data available — use evergreen angles for the niche."

    # Contexte des patterns YouTube gagnants
    yt_ctx = ""
    if yt_insights:
        yt_ctx = f"""
WINNING PATTERNS FROM TOP YOUTUBE VIDEOS (learn from what actually works):
- Title patterns: {', '.join(yt_insights.get('title_patterns', []))}
- Power words: {', '.join(yt_insights.get('power_words', []))}
- Common angles: {', '.join(yt_insights.get('common_angles', []))}
- Tips: {' | '.join(yt_insights.get('actionable_tips', []))}
Apply these proven patterns to make ideas more likely to go viral.
"""

    # Contexte du profil de niche
    audience_ctx = ""
    if niche_profile:
        audience_ctx = f"""
AUDIENCE PROFILE:
- Target: {niche_profile.get('audience', '')}
- Key angles for this audience: {', '.join(niche_profile.get('angles', []))}
- Preferred affiliate products: {', '.join(niche_profile.get('affiliates', []))}
Tailor every idea, hook, and affiliate angle to THIS specific audience.
"""

    prompt = f"""You are the trend strategist for a faceless short-form video channel.{audience_ctx}{yt_ctx}
Niche: {niche}
Target language: {language}

Below is REAL, RECENT web data about what's trending in this niche RIGHT NOW.
Use it to ground your ideas in reality — do NOT invent fake trends.

REAL TREND DATA:
{trend_context}

Generate {n} short-form video ideas, each COMPLETE and ready to script.
Prioritize ideas tied to the real data above (recency = virality).

BRAND-SAFETY RULES (mandatory — this channel will be monetized and sold):
- NO sensationalism, conspiracy framing, fear-baiting, or outrage-mining.
- NEVER use words like "addicted", "leaked", "secret", "they don't want you
  to know", or distort a real news story into a misleading claim.
- Frame everything factually and constructively: educate, don't manipulate.
- An idea that relies on controversy or distortion MUST get viral_score <= 40.
- Reward ideas that are accurate, useful, and safe for advertisers/platforms.
- Each idea must be defensible: if a journalist checked it, it should hold up.

MONEY ANGLE (this niche = entrepreneurs; translate every tool into a money outcome):
Whenever possible, frame the value as a concrete financial result, not just features.
- Good: "This AI tool replaces a $2,000/mo task" / "Cut your ad spend by 30%"
- Translate "AI tool X" into "what it earns or saves you" (time → money).
- Include the "money_angle" field: how this idea ties to revenue/savings.

CRITICAL brand-safety on money claims (do NOT cross this line):
- NO get-rich-quick promises, NO guaranteed income, NO fabricated earnings.
- NEVER invent specific income numbers (no "make $62,000/month") unless that
  exact figure comes from the real trend data provided.
- Frame as realistic potential ("could save", "some founders report"), never
  as a guarantee. If a money claim can't be sourced, keep it qualitative.
- An idea with an exaggerated or fabricated income claim MUST get viral_score <= 40.

FORMAT RULES (pick the best format for each idea — this drives retention):
Based on top-performing Shorts, choose ONE "format" per idea:
  - "ranking"  → Top 3/5 list (e.g. "Top 5 AI tools for X"). BEST for
                 retention: viewers stay to see #1. Use when the trend allows
                 listing multiple tools/options.
  - "versus"   → A vs B comparison (e.g. "Tool A vs Tool B — which wins?").
                 Use when two clear competitors/options exist.
  - "single"   → Deep dive on ONE tool/news. Use for a single strong story
                 (like a new product launch) that doesn't fit a list.
Prefer "ranking" or "versus" when the topic reasonably allows it — they
retain better than "single".
For "ranking": fill "list_items" with 3-5 short entries.
For "versus": fill "versus" with {{"a": "...", "b": "...", "winner": "..."}}.

HOOK RULES (critical — the hook decides if the video is watched or skipped):
The "hook" is the first spoken line. It must stop the scroll in under 3 seconds.
- Keep it SHORT: ideally under 12 words, front-load the most striking part.
- Use ONE of these proven patterns (pick what fits the trend best):
  1. Shock number: "This AI tool saved me 40 hours last month."
  2. Contradiction: "Stop paying for that tool. Here's why."
  3. Open loop: "Nobody is talking about what Meta just did."
  4. Costly mistake: "You're using AI wrong, and it's costing you."
  5. Before/after: "I replaced a whole task with one free tool."
  6. Direct question: "What if Facebook ran your marketing for you?"
  7. Freshness/FOMO: "Meta dropped this 3 days ago."
- The FIRST 3-4 words must carry impact (don't open with "Meta just..." —
  open with the benefit, the number, or the tension).
- No throat-clearing ("Today I'll show you", "In this video"). Hit immediately.
- Stay factual and brand-safe (no fake numbers, no distortion).

Return ONLY a valid JSON array, no markdown, no preamble:
[
  {{
    "title": "internal idea title",
    "hook": "the scroll-stopping first line, <12 words, using a proven pattern",
    "angle": "the unique angle / why people will care",
    "format": "ranking | versus | single",
    "list_items": ["item 1", "item 2", "item 3"],
    "versus": {{"a": "", "b": "", "winner": ""}},
    "structure": ["beat 1", "beat 2", "beat 3", "beat 4"],
    "broll_query": "2-3 word stock footage search term",
    "affiliate_angle": "how this could promote an AI/SaaS affiliate product",
    "money_angle": "the concrete revenue/savings framing (realistic, not hyped)",
    "viral_score": 0-100,
    "hook_pattern": "which of the 7 patterns this hook uses",
    "score_reason": "one sentence: why this score",
    "based_on_trend": "which real data point inspired this (or 'evergreen')",
    "brand_safe": true,
    "safety_note": "why this is safe, OR what risk was avoided"
  }}
]

Sort by viral_score descending. Be specific and punchy."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────
# FILTRE DE SÉCURITÉ — garde-fou code (en plus du prompt)
# ─────────────────────────────────────────────────────────
RISKY_TERMS = [
    "addict", "leaked", "secret", "conspiracy", "exposed", "they don't want",
    "shocking truth", "banned", "scandal", "cover-up", "hidden agenda",
    # promesses financières trompeuses (get-rich-quick)
    "guaranteed", "get rich", "easy money", "passive income guaranteed",
    "make $", "earn $", "/month guaranteed", "quit your job",
]

def filter_brand_safety(ideas: list) -> tuple:
    """
    Sépare les idées sûres des idées risquées.
    Une idée est écartée si elle est marquée brand_safe=false,
    ou si son hook/angle contient un terme à risque.
    """
    safe, flagged = [], []
    for idea in ideas:
        text = (idea.get("hook", "") + " " + idea.get("angle", "") + " "
                + idea.get("title", "")).lower()
        has_risky = any(term in text for term in RISKY_TERMS)
        is_flagged_by_llm = idea.get("brand_safe") is False

        if has_risky or is_flagged_by_llm:
            # cap le score et déplace dans flagged
            idea["viral_score"] = min(idea.get("viral_score", 0), 40)
            idea["_filter_reason"] = (
                "terme à risque détecté" if has_risky else "marqué non-safe par l'IA"
            )
            flagged.append(idea)
        else:
            safe.append(idea)

    safe.sort(key=lambda x: x.get("viral_score", 0), reverse=True)
    return safe, flagged


# ─────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────
def main():
    print(f"\n🔎 TrendResearchAgent — '{NICHE}' ({LANGUAGE})\n")

    print("① Recherche des tendances réelles via Tavily...")
    trends = search_trends(NICHE)
    print(f"   {len(trends)} signaux de tendance récupérés\n")

    print(f"② Génération de {N_IDEAS} idées complètes via Claude...")
    ideas = generate_ideas(NICHE, LANGUAGE, trends, N_IDEAS)

    with open(f"{OUTPUT_DIR}/ideas.json", "w") as f:
        json.dump(ideas, f, indent=2, ensure_ascii=False)

    safe, flagged = filter_brand_safety(ideas)

    # On ne garde que les idées sûres dans le fichier exploité par le pipeline
    with open(f"{OUTPUT_DIR}/ideas.json", "w") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)

    print(f"\n✅ {len(safe)} idées SÛRES → {OUTPUT_DIR}/ideas.json")
    if flagged:
        print(f"⚠️  {len(flagged)} idée(s) écartée(s) pour brand safety\n")
    print("─" * 60)
    for i, idea in enumerate(safe, 1):
        print(f"\n#{i}  [{idea['viral_score']}/100]  {idea['title']}")
        print(f"   🎣 Hook : {idea['hook']}")
        print(f"   🎯 Pattern: {idea.get('hook_pattern', 'n/a')}")
        print(f"   🎞️ Format: {idea.get('format', 'single')}")
        print(f"   📐 Angle: {idea['angle']}")
        print(f"   🎬 B-roll: {idea['broll_query']}")
        print(f"   💰 Affiliate: {idea['affiliate_angle']}")
        print(f"   📊 {idea['score_reason']}")
        print(f"   🔗 Basé sur: {idea['based_on_trend']}")
        print(f"   🛡️  {idea.get('safety_note', 'OK')}")

    if flagged:
        print("\n" + "─" * 60)
        print("⚠️  ÉCARTÉES (non utilisées) :")
        for idea in flagged:
            print(f"   ✗ {idea['title']} — {idea.get('_filter_reason', '')}")

    print("\n" + "─" * 60)
    print("\n👉 Prochaine étape : envoyer une idée sûre au pipeline vidéo v7\n")


if __name__ == "__main__":
    main()