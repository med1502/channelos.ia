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

_DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
_DEFAULT_LANG = "en"

# Max seconds to wait for JSON2Video to finish rendering
_MAX_POLL_SECONDS = 300

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
        print(f" ⚠️ Pexels B-roll failed: {e}")
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
        voice: str = _DEFAULT_VOICE,
        lang_code: str = _DEFAULT_LANG,
) -> tuple[str, float]:
        """
            Build and render the video via JSON2Video.
                Raises TimeoutError if rendering exceeds _MAX_POLL_SECONDS.
                    """
    api_key = os.environ.get("JSON2VIDEO_API_KEY")
    if not api_key:
                raise EnvironmentError(
                                "JSON2VIDEO_API_KEY is not set. "
                                "Export it: export JSON2VIDEO_API_KEY=..."
                )

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    broll_clips = broll_clips or ([broll_url] if broll_url else [])
    screen_items = screen_items or []

    # ── Build intro scene ─────────────────────────────────────────────────────
    first_clip = broll_clips[0] if broll_clips else None
    intro_elements: list[dict] = []
    if first_clip:
                intro_elements += [
                                {"type": "video", "src": first_clip, "loop": -1, "duration": -2,
                                              "x": 0, "y": 0, "width": 1080, "height": 1920,
                                              "resize": "cover", "volume": 0},
                                {"type": "html",
                                              "html": "<div style='width:1080px;height:1920px;"
                                                      "background:rgba(0,0,0,0.4);'></div>",
                                              "duration": -2, "x": 0, "y": 0, "width": 1080, "height": 1920},
                ]
    intro_elements.append({
                "type": "voice", "model": "azure", "voice": voice,
                "text": hook or spoken_text[:60], "duration": -1,
    })
    intro_scene = {
                "background-color": "#0D1117",
                "duration": -1,
                "elements": intro_elements,
    }

    # ── Build content scenes ──────────────────────────────────────────────────
    content_scenes: list[dict] = []
    if fmt == "ranking" and screen_items and len(broll_clips) > 1:
                for idx, (item, clip) in enumerate(zip(screen_items, broll_clips[1:] or broll_clips), 1):
                                content_elements: list[dict] = []
                                if clip:
                                                    content_elements += [
                                                                            {"type": "video", "src": clip, "loop": -1, "duration": -2,
                                                                                                  "x": 0, "y": 0, "width": 1080, "height": 1920,
                                                                                                  "resize": "cover", "volume": 0},
                                                                            {"type": "html",
                                                                                                  "html": "<div style='width:1080px;height:1920px;"
                                                                                                          "background:rgba(0,0,0,0.4);'></div>",
                                                                                                  "duration": -2, "x": 0, "y": 0, "width": 1080, "height": 1920},
                                                    ]
                                                content_elements.append(_rank_overlay(idx))
            content_elements.append({
                                "type": "voice", "model": "azure", "voice": voice,
                                "text": item, "duration": -1,
            })
            content_scenes.append({
                                "background-color": "#0D1117",
                                "duration": -1,
                                "elements": content_elements,
            })
else:
        first_clip = broll_clips[0] if broll_clips else None
        content_elements = []
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
                        "type": "voice", "model": "azure", "voice": voice,
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
                                "language": lang_code,
                                "settings": {
                                                    "color": "#FFFFFF",
                                                    "font-size": "48px",
                                                    "font-weight": "700",
                                                    "position": "bottom",
                                },
                }],
    }

    r = requests.post(J2V_URL, headers=headers, json=spec, timeout=30)
    r.raise_for_status()
    project_id = r.json()["project"]

    # ── Poll with timeout ─────────────────────────────────────────────────────
    print("  Rendering", end="", flush=True)
    max_polls = _MAX_POLL_SECONDS // 4
    for _ in range(max_polls):
                time.sleep(4)
        s = requests.get(J2V_URL, headers=headers,
                                                  params={"project": project_id}, timeout=15)
        s.raise_for_status()
        movie = s.json().get("movie", {})
        status = movie.get("status")
        if status == "done":
                        print(" ✓")
            return movie["url"], movie.get("duration", 0)
        if status == "error":
                        raise RuntimeError(f"Render failed: {movie.get('message')}")
        print(".", end="", flush=True)

    raise TimeoutError(
                f"JSON2Video render timed out after {_MAX_POLL_SECONDS}s "
                f"(project={project_id})"
    )


def download_video(url: str, out_path: str) -> None:
        r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(out_path, "wb") as f:
                for chunk in r.iter_content(8192):
                                f.write(chunk)
