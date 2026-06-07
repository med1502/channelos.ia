"""
ChannelOS — YouTubeTrendsAgent
==============================
Analyse les vidéos les plus VUES d'une niche sur YouTube pour en extraire
les PATTERNS gagnants (titres, structure, durée) — puis les injecte dans
la génération d'idées.

Ce que ça apprend (faisable via API officielle) :
  - Quels mots/structures de titres cartonnent ("Top 5", chiffres, "vs"...)
  - Quelle durée performe le mieux
  - Quels angles reviennent chez les vidéos à fort succès
  - Les tags les plus fréquents

Ce que ça NE fait PAS (étape ultérieure, transcription manuelle) :
  - Analyser le montage / style visuel des vidéos
  → noté dans le plan pour plus tard (téléchargement manuel + transcription)

Clé requise : YOUTUBE_API_KEY (gratuit, Google Cloud Console, 10k unités/jour)

SETUP :
  pip install google-api-python-client
  # Google Cloud Console → API YouTube Data v3 → créer une clé API
  export YOUTUBE_API_KEY=...
"""

import os
import re
import json
import hashlib
from datetime import datetime, timedelta

CACHE_DIR = "cache"
CACHE_TTL_HOURS = 24
os.makedirs(CACHE_DIR, exist_ok=True)


def _parse_duration(iso: str) -> int:
    """Convertit une durée ISO 8601 (PT1M30S) en secondes."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


# ─────────────────────────────────────────────────────────
# Récupération des vidéos top d'une niche (avec cache 24h)
# ─────────────────────────────────────────────────────────
def fetch_top_videos(query: str, max_results: int = 15) -> list:
    """
    Cherche les vidéos d'une niche triées par nombre de vues,
    et récupère leurs métadonnées (titre, vues, durée, tags).
    """
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("   ⚠️ YOUTUBE_API_KEY absente — YouTubeTrends ignoré")
        return []

    # Cache
    cache_key = hashlib.md5(query.encode()).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"yt_{cache_key}.json")
    if os.path.exists(cache_file):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if age < timedelta(hours=CACHE_TTL_HOURS):
            print("   (cache YouTube hit)")
            with open(cache_file) as f:
                return json.load(f)

    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("   ⚠️ google-api-python-client non installé — YouTubeTrends ignoré")
        return []

    yt = build("youtube", "v3", developerKey=key)

    # 1. Chercher les vidéos pertinentes, triées par vues
    search = yt.search().list(
        part="snippet", q=query, type="video",
        order="viewCount", maxResults=max_results,
        relevanceLanguage="en", publishedAfter=_recent_iso(days=90),
    ).execute()

    video_ids = [it["id"]["videoId"] for it in search.get("items", [])]
    if not video_ids:
        return []

    # 2. Récupérer les stats + détails de ces vidéos
    details = yt.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids),
    ).execute()

    videos = []
    for it in details.get("items", []):
        sn = it.get("snippet", {})
        st = it.get("statistics", {})
        cd = it.get("contentDetails", {})
        videos.append({
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
            "duration_sec": _parse_duration(cd.get("duration", "")),
            "tags": sn.get("tags", [])[:10],
            "published": sn.get("publishedAt", ""),
        })

    # Trier par vues décroissantes
    videos.sort(key=lambda v: v["views"], reverse=True)

    with open(cache_file, "w") as f:
        json.dump(videos, f, ensure_ascii=False)

    return videos


def _recent_iso(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────
# Analyse des patterns par Claude
# ─────────────────────────────────────────────────────────
def analyze_patterns(videos: list, niche: str) -> dict:
    """
    Claude analyse les vidéos top et extrait les patterns gagnants
    (titres, structures, durée, angles) réutilisables.
    """
    if not videos:
        return {}

    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Compacter les données pour Claude
    sample = "\n".join(
        f"- [{v['views']:,} views, {v['duration_sec']}s] {v['title']}"
        for v in videos[:15]
    )

    prompt = f"""Here are the most-viewed recent YouTube videos in the niche "{niche}".
Analyze them to extract WINNING PATTERNS we can reuse for short-form content.

TOP VIDEOS (by views):
{sample}

Return ONLY valid JSON, no markdown:
{{
  "title_patterns": ["recurring title structures that work, e.g. 'Top N ...', 'X vs Y'"],
  "power_words": ["words/phrases that appear in high-view titles"],
  "common_angles": ["recurring content angles/themes"],
  "optimal_duration_note": "what video length seems to perform (short note)",
  "actionable_tips": ["3-5 concrete tips to apply to OUR short-form videos"]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ─────────────────────────────────────────────────────────
# Point d'entrée : retourne les insights prêts à injecter
# ─────────────────────────────────────────────────────────
def get_youtube_insights(query: str, niche: str) -> dict:
    """
    Combine fetch + analyse. Retourne un dict d'insights
    (vide si pas de clé/données — le pipeline continue sans).
    """
    videos = fetch_top_videos(query)
    if not videos:
        return {}
    patterns = analyze_patterns(videos, niche)
    patterns["_sample_count"] = len(videos)
    patterns["_top_title"] = videos[0]["title"] if videos else ""
    return patterns


# ─────────────────────────────────────────────────────────
# CLI de test
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "AI tools for entrepreneurs"
    print(f"\n🔎 YouTubeTrendsAgent — '{q}'\n")
    insights = get_youtube_insights(q, q)
    if not insights:
        print("Aucun insight (vérifie YOUTUBE_API_KEY).")
    else:
        print(f"Analysé {insights.get('_sample_count', 0)} vidéos top\n")
        print(json.dumps(insights, indent=2, ensure_ascii=False))