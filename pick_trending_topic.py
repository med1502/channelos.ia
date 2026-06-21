#!/usr/bin/env python3
"""
pick_trending_topic.py
Agrège YouTube Data API v3, Hacker News et Google Trends pour choisir
le topic AI/entrepreneur le plus porteur du jour.
Conçu pour être appelé par le cron via $(...) — affiche UN topic sur stdout.

Reddit retiré (2026-06-21) : la Responsible Builder Policy interdit l'usage
commercial des données et leur passage dans un modèle IA sans accord écrit.
Notre pipeline = données Reddit → Claude → Shorts monétisés = non conforme.

Usage:
    python3 pick_trending_topic.py

Dépendances:
    pip install pytrends requests anthropic --break-system-packages
"""

import os
import sys
import re
import json
import random
import logging
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────

PROJECT_ROOT = "/home/mfayech/Github/channelos.ia"
sys.path.insert(0, PROJECT_ROOT)

# Charge .env sans xargs (évite le bug avec DATABASE_URL qui contient '=')
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Log vers stderr uniquement — stdout est réservé au topic final
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("pick_topic")

FALLBACK_TOPICS = [
    "AI tools for entrepreneurs",
    "Claude Code workflows",
    "no-code automation",
    "AI for small business",
]

# ─────────────────────────────────────────────────────────
# SOURCE 1 : YouTube Data API v3
# Cherche les vidéos courtes les plus vues cette semaine
# dans la niche AI/entrepreneur
# ─────────────────────────────────────────────────────────

def fetch_youtube_trends() -> list[str]:
    import requests

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        log.warning("YOUTUBE_API_KEY absent — source YouTube ignorée")
        return []

    signals = []
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=7)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    year = datetime.now(timezone.utc).year
    queries = [
        f"AI tools entrepreneurs {year}",
        "AI automation small business",
        "no-code AI productivity",
    ]

    for query in queries:
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "key": api_key,
                "q": query,
                "type": "video",
                "order": "viewCount",
                "publishedAfter": published_after,
                "videoDuration": "short",   # Shorts uniquement
                "maxResults": 5,
                "part": "snippet",
                "relevanceLanguage": "en",
            }
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            for item in data.get("items", []):
                title = item["snippet"]["title"]
                channel = item["snippet"]["channelTitle"]
                signals.append(f"[YouTube] {title} (by {channel})")

            log.info(f"YouTube '{query}' → {len(data.get('items', []))} résultats")

        except Exception as e:
            log.warning(f"YouTube erreur pour '{query}': {e}")

    return signals


# ─────────────────────────────────────────────────────────
# SOURCE 2 : Hacker News (Algolia API — gratuit, sans clé)
# Top stories AI des 3 derniers jours avec score > 50
# ─────────────────────────────────────────────────────────

def fetch_hackernews_trends() -> list[str]:
    import requests

    signals = []
    since = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp())

    queries = [
        "AI tools",
        "LLM automation",
        "AI entrepreneur",
        "Claude AI",
        "AI productivity",
    ]

    for query in queries:
        try:
            # numericFilters en chaîne comma-séparée déclenchait un 400 Bad Request.
            # On récupère par date (search_by_date, tri récent→ancien) et on filtre
            # récence + score côté Python : plus robuste, aucun param fragile.
            url = "https://hn.algolia.com/api/v1/search_by_date"
            params = {
                "query": query,
                "tags": "story",
                "hitsPerPage": 20,
            }
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            kept = 0
            for hit in data.get("hits", []):
                title = hit.get("title", "")
                score = hit.get("points") or 0
                created = hit.get("created_at_i") or 0
                if title and score > 50 and created > since:
                    signals.append(f"[HN:{score}pts] {title}")
                    kept += 1

            log.info(f"HN '{query}' → {kept} résultats (sur {len(data.get('hits', []))})")

        except Exception as e:
            log.warning(f"HN erreur pour '{query}': {e}")

    return signals


# ─────────────────────────────────────────────────────────
# SOURCE 3 : Google Trends (pytrends — gratuit, sans clé)
# Volume de recherche sur 7 jours + related queries
# ─────────────────────────────────────────────────────────

def fetch_google_trends() -> list[str]:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        log.warning("pytrends non installé — pip install pytrends --break-system-packages")
        return []

    signals = []

    try:
        # Délai pour éviter le rate-limit Google Trends
        import time
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 30), retries=2, backoff_factor=0.5)

        # 1. Tendances de recherche en temps réel (US)
        try:
            trending = pt.trending_searches(pn="united_states")
            ai_terms = [
                t for t in trending[0].head(30).tolist()
                if any(kw in t.lower() for kw in ["ai", "gpt", "claude", "automation", "tool", "llm", "tech"])
            ]
            for term in ai_terms[:5]:
                signals.append(f"[GTrends trending] {term}")
            log.info(f"GTrends trending searches → {len(ai_terms)} termes AI")
        except Exception as e:
            log.warning(f"GTrends trending_searches: {e}")

        time.sleep(2)  # Rate limit

        # 2. Intérêt comparé sur 7 jours pour nos keywords clés
        try:
            kws = ["AI tools", "AI automation", "no-code AI", "Claude AI"]
            pt.build_payload(kws, timeframe="now 7-d", geo="US")
            iot = pt.interest_over_time()
            if not iot.empty:
                latest = iot.iloc[-1].drop("isPartial", errors="ignore")
                top_kw = latest.idxmax()
                top_val = latest.max()
                signals.append(f"[GTrends top7d] {top_kw} (score {top_val})")
                log.info(f"GTrends interest_over_time → top: {top_kw} ({top_val})")
        except Exception as e:
            log.warning(f"GTrends interest_over_time: {e}")

        time.sleep(2)

        # 3. Related queries pour "AI entrepreneur"
        try:
            pt.build_payload(["AI entrepreneur"], timeframe="now 7-d", geo="US")
            related = pt.related_queries()
            top_df = related.get("AI entrepreneur", {}).get("top", None)
            if top_df is not None:
                for q in top_df["query"].head(5).tolist():
                    signals.append(f"[GTrends related] {q}")
                log.info(f"GTrends related queries → {len(top_df)} résultats")
        except Exception as e:
            log.warning(f"GTrends related_queries: {e}")

    except Exception as e:
        log.warning(f"GTrends erreur générale: {e}")

    return signals


# ─────────────────────────────────────────────────────────
# SYNTHÈSE : Claude Haiku choisit le meilleur topic
# Cheap (~$0.0001/appel), rapide, déjà dans la stack
# ─────────────────────────────────────────────────────────

def synthesize_with_claude(signals: list[str]) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY absent — synthèse Claude ignorée")
        return None

    if not signals:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        signals_block = "\n".join(signals[:40])  # Cap à 40 signaux

        now = datetime.now(timezone.utc)
        today_str = now.strftime("%B %d, %Y")
        current_year = now.year

        prompt = f"""You help pick the daily video topic for a YouTube Shorts channel.

Today's date: {today_str}. The current year is {current_year}.

Channel profile:
- Niche: AI tools for entrepreneurs and small business owners
- Format: short vertical video, 30 seconds, ranking style
- Language: English
- Goal: maximum retention in the first 3 seconds

Today's trending signals from YouTube, HackerNews, and Google Trends:
{signals_block}

Based on these signals, output ONLY a single short keyword phrase (3-7 words) that:
1. Is directly relevant to AI tools, automation, or productivity for entrepreneurs
2. Has clear trending evidence in the signals above
3. Is specific enough to anchor a compelling 30s ranking video
4. Is in English
5. If the phrase needs a year, use {current_year} — NEVER an older year, even if the signals mention one

Output the keyword phrase ONLY. No explanation, no punctuation, no quotes."""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )

        topic = message.content[0].text.strip().strip('"').strip("'")

        # Validation basique
        if topic and len(topic) < 80 and "\n" not in topic and len(topic.split()) >= 2:
            log.info(f"Claude Haiku → topic sélectionné: '{topic}'")
            return topic
        else:
            log.warning(f"Claude Haiku → réponse invalide: '{topic}'")

    except Exception as e:
        log.warning(f"Synthèse Claude erreur: {e}")

    return None


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def pick_topic() -> str:
    log.info("=== pick_trending_topic démarrage ===")

    all_signals: list[str] = []

    # Collecte parallèle des 3 sources (timeout global 40s)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fetch_youtube_trends): "YouTube",
            executor.submit(fetch_hackernews_trends): "HackerNews",
            executor.submit(fetch_google_trends): "GoogleTrends",
        }
        for future in as_completed(futures, timeout=40):
            source = futures[future]
            try:
                result = future.result()
                log.info(f"{source} → {len(result)} signaux collectés")
                all_signals.extend(result)
            except Exception as e:
                log.warning(f"{source} → échec: {e}")

    log.info(f"Total signaux collectés: {len(all_signals)}")

    if not all_signals:
        fallback = random.choice(FALLBACK_TOPICS)
        log.warning(f"Aucun signal — fallback: '{fallback}'")
        return fallback

    # Synthèse via Claude Haiku
    topic = synthesize_with_claude(all_signals)
    if topic:
        return topic

    # Fallback 1 : premier titre YouTube nettoyé
    for signal in all_signals:
        if signal.startswith("[YouTube]"):
            raw = signal.replace("[YouTube] ", "")
            cleaned = re.sub(r"\s*[\|\-–#@]\s*.{0,50}$", "", raw).strip()
            if 5 < len(cleaned) < 70:
                log.info(f"Fallback YouTube title: '{cleaned}'")
                return cleaned

    # Fallback 2 : topic statique aléatoire
    fallback = random.choice(FALLBACK_TOPICS)
    log.warning(f"Fallback statique: '{fallback}'")
    return fallback


if __name__ == "__main__":
    print(pick_topic())