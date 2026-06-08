"""
ChannelOS — YouTubeTrendsAgent
Analyses top YouTube videos in a niche to extract winning patterns.
Gracefully degrades if no API key is set.
Requires: pip install google-api-python-client
"""

import os
import re
from collections import Counter

from channelos.utils.cache import cache_key, cache_get, cache_set
from datetime import datetime, timedelta


def _recent_iso(days: int = 90) -> str:
        return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_youtube_insights(niche_query: str, niche_name: str = "", max_results: int = 10) -> dict | None:
        """
            Fetches top YouTube videos for a niche and extracts:
                - title_patterns, power_words, optimal_duration_seconds, actionable_tips
                    Returns None on any failure (graceful degradation).
                        """
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
                    return None

        query = f"{niche_query} {niche_name}".strip()
        key = cache_key(query)
        cached = cache_get("yt", key)
        if cached:
                    print("  (YouTube cache hit)")
                    return cached

        try:
                    from googleapiclient.discovery import build
except ImportError:
        print(" ⚠️ google-api-python-client not installed — YouTubeTrends skipped")
        return None

    try:
                yt = build("youtube", "v3", developerKey=api_key)

        search = yt.search().list(
                        part="snippet",
                        q=query,
                        type="video",
                        order="viewCount",
                        maxResults=max_results,
                        relevanceLanguage="en",
                        publishedAfter=_recent_iso(days=90),
        ).execute()

        video_ids = [it["id"]["videoId"] for it in search.get("items", [])]
        if not video_ids:
                        return None

        stats_resp = yt.videos().list(
                        part="statistics,contentDetails,snippet",
                        id=",".join(video_ids),
        ).execute()

        videos = stats_resp.get("items", [])

        # Extract insights
        titles = [v["snippet"]["title"] for v in videos]
        durations = []
        for v in videos:
                        iso = v["contentDetails"].get("duration", "PT0S")
                        m = re.findall(r"(\d+)M|(\d+)S", iso)
                        secs = sum(int(a or 0) * 60 + int(b or 0) for a, b in m)
                        if secs:
                                            durations.append(secs)

                    all_words = " ".join(titles).lower().split()
        power_words = [
                        w for w, _ in Counter(all_words).most_common(20)
                        if len(w) > 3 and w not in {
                                            "with", "that", "this", "your", "have", "from", "they",
                                            "will", "more", "what", "when", "how", "the", "for", "and",
                        }
        ]

        title_patterns = []
        for t in titles[:5]:
                        if re.search(r"\d", t):
                                            title_patterns.append("numbered: " + t[:60])
elif " vs " in t.lower():
                title_patterns.append("versus: " + t[:60])
elif t.lower().startswith(("how", "why", "what")):
                title_patterns.append("question: " + t[:60])
else:
                title_patterns.append("statement: " + t[:60])

        avg_duration = int(sum(durations) / len(durations)) if durations else None

        tips = []
        if any(re.search(r"\b\d+\b", t) for t in titles):
                        tips.append("Numbers in titles drive clicks — use '5 tools', 'in 3 steps'")
                    if any(" vs " in t.lower() for t in titles):
                                    tips.append("Versus format performs well in this niche")
                                if avg_duration and avg_duration < 90:
                                                tips.append(f"Top videos average {avg_duration}s — stay under 90s")

        result = {
                        "title_patterns": title_patterns,
                        "power_words": power_words[:10],
                        "optimal_duration_seconds": avg_duration,
                        "actionable_tips": tips,
                        "_sample_count": len(videos),
        }

        cache_set("yt", key, result)
        return result

except Exception as e:
        print(f" ⚠️ YouTube insights failed: {e}")
        return None
