"""
ChannelOS — VideoProducer (render pipeline)
Fetches B-roll from Pexels and renders via JSON2Video (Azure TTS + subtitles).

TASK-004: fetch_broll_multi() — one clip per ranking item
TASK-005: visual rank numbers on screen for ranking format
"""

import os
import time
import requests

J2V_URL = "https://api.json2video.com/v2/movies"

# Set by main.py from niche profile + lang arg
VOICE: str = "en-US-AndrewMultilingualNeural"
LANG_CODE: str = "en"


# ── B-roll ────────────────────────────────────────────────────────────────────

def _pexels_search(query: str, count: int = 5) -> list[str]:
    """Returns a list of portrait video URLs from Pexels."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    urls = []
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": key},
            params={"query": query, "orientation": "portrait",
                    "per_page": count, "size": "medium"},
            timeout=10,
        )
        r.raise_for_status()
        for v in r.json().get("videos", []):
            files = sorted(v["video_files"], key=lambda f: f.get("height") or 0, reverse=True)
            for f in files:
                if (f.get("height") or 0) >= (f.get("width") or 0):
                    urls.append(f["link"])
                    break
    except Exception as e:
        print(f"   ⚠️  Pexels B-roll failed: {e}")
    return urls


def fetch_broll(query: str) -> str:
    """Single clip — backward-compatible."""
    urls = _pexels_search(query, 5)
    return urls[0] if urls else ""


def fetch_broll_multi(queries: list[str], fallback_query: str, n: int) -> list[str]:
    """
    TASK-004: Fetch n distinct B-roll clips.
    Uses one specific query per ranking item, then fills from fallback_query.
    """
    clips: list[str] = []

    for q in queries:
        urls = _pexels_search(q, 3)
        pick = next((u for u in urls if u not in clips), None)
        if pick:
            clips.append(pick)
        if len(clips) >= n:
            break

    if len(clips) < n:
        extra = _pexels_search(fallback_query, n * 2)
        for u in extra:
            if u not in clips:
                clips.append(u)
            if len(clips) >= n:
                break

    return clips[:n]


# ── Rank number overlay (TASK-005) ────────────────────────────────────────────

def _rank_overlay(number: int) -> dict:
    """
    Returns a JSON2Video text element showing the rank number in cyan.
    E.g. number=3 → "3" bottom-left, #00E5FF, 120px bold.
    """
    return {
        "type": "text",
        "text": str(number),
        "duration": -2,
        "position": "custom",
        "x": 60,
        "y": 1700,
        "width": 200,
        "height": 200,
        "settings": {
            "font-family": "Roboto",
            "font-size": "160px",
            "font-weight": "900",
            "color": "#00E5FF",
            "text-align": "left",
            "vertical-align": "center",
            "outline-color": "#000000",
            "outline-width": 8,
        },
    }


# ── Video render ──────────────────────────────────────────────────────────────

def render_video(
    spoken_text: str,
    broll_url: str,
    hook: str = "",
    broll_clips: list[str] | None = None,
    screen_items: list[str] | None = None,
    fmt: str = "single",
    voice: str | None = None,
    lang_code: str | None = None,
) -> tuple[str, float]:
    """
    Build and render the video via JSON2Video.

    Scene 1 (2s)  : giant hook text — scroll-stopper + thumbnail
    Scene 2 (~28s): B-roll + Azure TTS voice + auto-synced subtitles

    For ranking format: one scene per item with B-roll change (TASK-004)
    and rank number overlay (TASK-005).

    Returns (video_url, duration_seconds).
    """
    _voice = voice or VOICE
    _lang = lang_code or LANG_CODE

    api_key = os.environ["JSON2VIDEO_API_KEY"]
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    broll_clips = broll_clips or ([broll_url] if broll_url else [])
    first_clip = broll_clips[0] if broll_clips else ""

    # ── Scene 1: hook intro ──────────────────────────────────────────────────
    hook_text = (hook or spoken_text).strip()
    hw = hook_text.split()
    if len(hw) > 12:
        hook_text = " ".join(hw[:12]) + "…"

    intro_elements: list[dict] = []
    if first_clip:
        intro_elements += [
            {"type": "video", "src": first_clip, "loop": -1, "duration": -2,
             "x": 0, "y": 0, "width": 1080, "height": 1920,
             "resize": "cover", "volume": 0},
            {"type": "html",
             "html": "<div style='width:1080px;height:1920px;"
                     "background:rgba(0,0,0,0.6);'></div>",
             "duration": -2, "x": 0, "y": 0, "width": 1080, "height": 1920},
        ]
    intro_elements += [
        {"type": "html",
         "html": "<div style='width:200px;height:12px;background:#00E5FF;"
                 "border-radius:6px;'></div>",
         "duration": -2, "position": "custom", "x": 440, "y": 1180,
         "width": 200, "height": 12},
        {"type": "text", "style": "002", "text": hook_text.upper(),
         "duration": -2,
         "settings": {
             "font-family": "Roboto", "font-size": "90px",
             "font-weight": "900", "color": "#FFFFFF",
             "text-align": "center", "vertical-align": "center",
             "horizontal-align": "center", "shadow": 3,
         }},
    ]
    intro_scene = {
        "background-color": "#0D1117",
        "duration": 2.0,
        "elements": intro_elements,
    }

    # ── Scene 2: content ─────────────────────────────────────────────────────
    # For ranking format with multiple clips: one scene per item (TASK-004/005)
    content_scenes: list[dict] = []
    items = screen_items or []

    if fmt == "ranking" and len(broll_clips) > 1 and len(items) > 1:
        # Split spoken_text roughly equally across items
        words = spoken_text.split()
        chunk_size = max(1, len(words) // len(items))
        chunks = [
            " ".join(words[i * chunk_size: (i + 1) * chunk_size])
            for i in range(len(items))
        ]
        # append any remainder to last chunk
        if len(words) > chunk_size * len(items):
            chunks[-1] += " " + " ".join(words[chunk_size * len(items):])

        for idx, (item, chunk) in enumerate(zip(items, chunks)):
            clip = broll_clips[idx % len(broll_clips)]
            rank_num = len(items) - idx  # countdown: 5, 4, 3, 2, 1
            scene_elements: list[dict] = [
                {"type": "video", "src": clip, "loop": -1, "duration": -1,
                 "x": 0, "y": 0, "width": 1080, "height": 1920,
                 "resize": "cover", "volume": 0},
                {"type": "html",
                 "html": "<div style='width:1080px;height:1920px;"
                         "background:rgba(0,0,0,0.4);'></div>",
                 "duration": -1, "x": 0, "y": 0, "width": 1080, "height": 1920},
                {"type": "voice", "model": "azure", "voice": _voice,
                 "text": chunk, "duration": -1},
                _rank_overlay(rank_num),  # TASK-005
            ]
            content_scenes.append({
                "background-color": "#0D1117",
                "duration": -1,
                "elements": scene_elements,
            })
    else:
        # Single content scene (single / versus / ranking without multi-clip)
        content_elements: list[dict] = []
        if first_clip:
            content_elements += [
                {"type": "video", "src": first_clip, "loop": -1, "duration": -2,
                 "x": 0, "y": 0, "width": 1080, "height": 1920,
                 "resize": "cover", "volume": 0},
                {"type": "html",
                 "html": "<div style='width:1080px;height:1920px;"
                         "background:rgba(0,0,0,0.4);'></div>",
                 "duration": -2, "x": 0, "y": 0, "width": 1080, "height": 1920},
            ]
        content_elements.append({
            "type": "voice", "model": "azure", "voice": _voice,
            "text": spoken_text, "duration": -1,
        })
        content_scenes.append({
            "background-color": "#0D1117",
            "duration": -1,
            "elements": content_elements,
        })

    spec = {
        "width": 1080,
        "height": 1920,
        "quality": "high",
        "scenes": [intro_scene] + content_scenes,
        "elements": [{
            "type": "subtitles",
            "language": _lang,
            "settings": {
                "style": "classic-progressive",
                "font-family": "Roboto",
                "font-size": 95,
                "font-weight": 900,
                "word-color": "#00E5FF",
                "line-color": "#FFFFFF",
                "outline-color": "#000000",
                "outline-width": 7,
                "position": "center",
            },
        }],
    }

    r = requests.post(J2V_URL, headers=headers, json=spec, timeout=30)
    r.raise_for_status()
    project_id = r.json()["project"]

    print("   Rendering", end="", flush=True)
    while True:
        time.sleep(4)
        s = requests.get(J2V_URL, headers=headers, params={"project": project_id}, timeout=15)
        s.raise_for_status()
        movie = s.json().get("movie", {})
        status = movie.get("status")
        if status == "done":
            print(" ✓")
            return movie["url"], movie.get("duration", 0)
        if status == "error":
            raise RuntimeError(f"Render failed: {movie.get('message')}")
        print(".", end="", flush=True)


def download_video(url: str, out_path: str) -> None:
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
