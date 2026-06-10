"""
ChannelOS — VideoProducer (render pipeline) v2
Fetches B-roll from Pexels and renders via JSON2Video (Azure TTS + subtitles).

v2:
- Render quota guard (protège les crédits JSON2Video, échec bruyant AVANT l'appel)
- Découpage du script par PHRASES (plus de coupures mi-phrase entre scènes)
- Overlay nom de l'outil + numéro de rang par scène (le visuel suit le contexte)
- Log de la branche de rendu choisie (diagnostic vidéos statiques)
"""

import os
import re
import time
from datetime import date

import requests

import channelos.db as db

J2V_URL = "https://api.json2video.com/v2/movies"

# Set by main.py from niche profile + lang arg
VOICE: str = "en-US-AndrewMultilingualNeural"
LANG_CODE: str = "en"

# ── Render quota guard ────────────────────────────────────────────────────────
# 1 crédit ≈ 1 seconde rendue (1080p). Budget quotidien paramétrable.
# 90 = ~3 vidéos/jour (semaine 1) ; passer à 200 pour 6/jour.

RENDER_BUDGET_SECONDS_PER_DAY = float(os.environ.get("RENDER_BUDGET_SECONDS", 90))
EXPECTED_VIDEO_SECONDS = 32  # 30s + marge, consommé en estimation avant render


def _ensure_render_quota_table() -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS render_quota (
                day     DATE PRIMARY KEY,
                seconds FLOAT NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def render_quota_remaining() -> float:
    _ensure_render_quota_table()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT seconds FROM render_quota WHERE day=%s", (date.today(),))
        row = cur.fetchone()
    used = row[0] if row else 0.0
    return RENDER_BUDGET_SECONDS_PER_DAY - used


def _render_quota_check() -> None:
    remaining = render_quota_remaining()
    if remaining < EXPECTED_VIDEO_SECONDS:
        raise RuntimeError(
            f"Budget de rendu quotidien insuffisant: {remaining:.0f}s restants, "
            f"~{EXPECTED_VIDEO_SECONDS}s requis "
            f"(RENDER_BUDGET_SECONDS={RENDER_BUDGET_SECONDS_PER_DAY:.0f}/jour)."
        )


def _render_quota_consume(actual_seconds: float) -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO render_quota (day, seconds) VALUES (%s, %s)
            ON CONFLICT (day) DO UPDATE
              SET seconds = render_quota.seconds + EXCLUDED.seconds
            """,
            (date.today(), actual_seconds),
        )
        conn.commit()


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
    """Fetch n distinct B-roll clips: one specific query per ranking item,
    then fill from fallback_query."""
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


# ── Script chunking (par phrases, plus de coupures mi-phrase) ────────────────

def _split_sentences(text: str) -> list[str]:
    """Découpe naïve mais robuste sur . ! ? en conservant la ponctuation."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _chunk_by_sentences(text: str, n_chunks: int) -> list[str]:
    """Répartit les phrases en n_chunks consécutifs, équilibrés en mots.

    Garantit n_chunks non vides quand il y a au moins n_chunks phrases ;
    sinon, répartit ce qu'il y a (les chunks vides héritent d'une phrase
    du chunk précédent si possible)."""
    sentences = _split_sentences(text)
    if not sentences:
        return [text] + [""] * (n_chunks - 1)

    total_words = sum(len(s.split()) for s in sentences)
    target = max(1, total_words / n_chunks)

    chunks: list[list[str]] = [[] for _ in range(n_chunks)]
    i = 0
    acc = 0
    for s in sentences:
        chunks[i].append(s)
        acc += len(s.split())
        if acc >= target * (i + 1) and i < n_chunks - 1:
            i += 1

    # Rééquilibrage: aucun chunk vide si on peut l'éviter
    for j in range(1, n_chunks):
        if not chunks[j] and len(chunks[j - 1]) > 1:
            chunks[j].append(chunks[j - 1].pop())

    return [" ".join(c) for c in chunks]


# ── Overlays par scène ────────────────────────────────────────────────────────

def _rank_overlay(number: int) -> dict:
    """Numéro de rang, cyan, bas-gauche."""
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


def _item_name_overlay(name: str) -> dict:
    """Nom de l'outil/item, en haut de l'écran — le visuel suit le contexte."""
    display = name.strip()
    if len(display) > 28:
        display = display[:27] + "…"
    return {
        "type": "text",
        "text": display.upper(),
        "duration": -2,
        "position": "custom",
        "x": 90,
        "y": 200,
        "width": 900,
        "height": 160,
        "settings": {
            "font-family": "Roboto",
            "font-size": "72px",
            "font-weight": "900",
            "color": "#FFFFFF",
            "text-align": "center",
            "vertical-align": "center",
            "outline-color": "#000000",
            "outline-width": 7,
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
    Scene 1 (2s)  : giant hook text — scroll-stopper + thumbnail
    Scenes 2..N   : ranking → une scène par item (clip dédié + nom + rang)
                    sinon  → une scène contenu unique

    Returns (video_url, duration_seconds).
    """
    _render_quota_check()  # échec bruyant AVANT de consommer des crédits

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

    # ── Scenes contenu ───────────────────────────────────────────────────────
    content_scenes: list[dict] = []
    items = screen_items or []

    multi = fmt == "ranking" and len(broll_clips) > 1 and len(items) > 1
    print(f"   Render branch: {'MULTI-SCENE' if multi else 'SINGLE-SCENE'} "
          f"(fmt={fmt}, clips={len(broll_clips)}, items={len(items)})")

    if multi:
        chunks = _chunk_by_sentences(spoken_text, len(items))

        for idx, (item, chunk) in enumerate(zip(items, chunks)):
            if not chunk.strip():
                continue
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
                _rank_overlay(rank_num),
                _item_name_overlay(item),
            ]
            content_scenes.append({
                "background-color": "#0D1117",
                "duration": -1,
                "elements": scene_elements,
            })
    else:
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
            duration = movie.get("duration", 0) or EXPECTED_VIDEO_SECONDS
            _render_quota_consume(duration)
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