"""
ChannelOS — Pipeline v7 : JSON2Video + B-roll Pexels + voix dynamique
=====================================================================
Améliorations vs v6 :
  • Voix plus DYNAMIQUE : en-US-AvaMultilingualNeural (énergique)
    + ajustement du débit via SSML (prosody rate)
  • FOND VIDÉO : B-roll Pexels pertinent (gratuit) au lieu du fond uni
    → Claude génère le mot-clé, Pexels fournit la vidéo, J2V l'utilise en fond
  • Overlay sombre pour garder les sous-titres lisibles sur la vidéo

Clés requises :
  ANTHROPIC_API_KEY   (script)
  JSON2VIDEO_API_KEY  (rendu)
  PEXELS_API_KEY      (B-roll — gratuit sur pexels.com/api)
"""

import os
import sys
import json
import time
import requests

NICHE = sys.argv[1] if len(sys.argv) > 1 else "AI tools for entrepreneurs"
LANGUAGE = "EN"
LANG_CODE = "en"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

API_URL = "https://api.json2video.com/v2/movies"

# Voix dynamiques recommandées (Azure, gratuites) :
#   en-US-AvaMultilingualNeural    → femme, énergique, naturelle
#   en-US-AndrewMultilingualNeural → homme, posé moderne
#   en-US-EmmaMultilingualNeural   → femme, chaleureuse
#   en-US-BrianMultilingualNeural  → homme, conversationnel
VOICE = "en-US-AvaMultilingualNeural"


# ─────────────────────────────────────────────────────────
# 1 — SCRIPT via Claude
# ─────────────────────────────────────────────────────────
def generate_script(niche: str, language: str) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""Write a short-form video script for a faceless {language} TikTok/Reels video.
Niche: {niche}

Requirements:
- ~35 seconds spoken (90-110 words)
- Scroll-stopping hook in the first sentence
- 3-4 punchy value sentences
- CTA mentioning "link in bio"
- Energetic, direct tone

Return ONLY valid JSON, no markdown:
{{
  "hook": "...",
  "body": "...",
  "cta": "...",
  "caption": "...",
  "hashtags": ["...", "..."],
  "broll_query": "ONE concise stock-footage search term (2-3 words) for a
                  dynamic background video matching the topic, e.g.
                  'busy office laptop' or 'futuristic technology'"
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────
# 2 — B-ROLL via Pexels (gratuit) — vidéo verticale pertinente
# ─────────────────────────────────────────────────────────
def fetch_broll(query: str) -> str:
    """Récupère l'URL d'une vidéo verticale Pexels correspondant au mot-clé."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return ""  # pas de clé → fond uni de secours

    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait",
                "per_page": 5, "size": "medium"},
    )
    r.raise_for_status()
    videos = r.json().get("videos", [])
    if not videos:
        return ""

    # Choisir le premier clip et sa version HD verticale
    for v in videos:
        files = sorted(v["video_files"],
                       key=lambda f: (f.get("height") or 0), reverse=True)
        for f in files:
            if (f.get("height") or 0) >= (f.get("width") or 0):  # vertical
                return f["link"]
    # fallback : premier lien dispo
    return videos[0]["video_files"][0]["link"]


# ─────────────────────────────────────────────────────────
# 3 — SPEC JSON2Video : fond vidéo + overlay + voix + sous-titres
# ─────────────────────────────────────────────────────────
def build_movie_spec(script: dict, broll_url: str) -> dict:
    full_text = f"{script['hook']} {script['body']} {script['cta']}"


    scene_elements = []

    # Fond : B-roll vidéo si dispo, sinon couleur unie
    if broll_url:
        scene_elements.append({
            "type": "video",
            "src": broll_url,
            "duration": -2,          # = durée de la scène
            "x": 0, "y": 0,
            "width": 1080, "height": 1920,
            "resize": "cover",       # remplit tout le cadre vertical
            "volume": 0,             # couper le son du B-roll
        })
        # Overlay sombre via composant HTML (pas de dépendance externe)
        scene_elements.append({
            "type": "html",
            "html": "<div style='width:1080px;height:1920px;"
                    "background:rgba(0,0,0,0.45);'></div>",
            "duration": -2,
            "x": 0, "y": 0,
            "width": 1080, "height": 1920,
        })

    # Voix
    voice_el = {
        "type": "voice",
        "model": "azure",
        "voice": VOICE,
        "text": full_text,
        "duration": -1,
    }
    scene_elements.append(voice_el)

    spec = {
        "width": 1080,
        "height": 1920,
        "quality": "high",
        "scenes": [
            {
                "background-color": "#0D1117",
                "elements": scene_elements,
            }
        ],
        # Sous-titres auto, synchro mot à mot
        "elements": [
            {
                "type": "subtitles",
                "language": LANG_CODE,
                "settings": {
                    "style": "classic-progressive",
                    "font-family": "Roboto",
                    "font-size": 95,
                    "font-weight": 900,
                    "word-color": "#00E5FF",
                    "line-color": "#FFFFFF",
                    "outline-color": "#000000",
                    "outline-width": 7,
                    "shadow-color": "#000000",
                    "shadow-offset": 4,
                    "position": "center",
                },
            }
        ],
    }
    return spec


def render_video(spec: dict) -> str:
    api_key = os.environ["JSON2VIDEO_API_KEY"]
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    r = requests.post(API_URL, headers=headers, json=spec)
    r.raise_for_status()
    project_id = r.json()["project"]

    print("   Rendu en cours", end="", flush=True)
    while True:
        time.sleep(4)
        s = requests.get(API_URL, headers=headers, params={"project": project_id})
        s.raise_for_status()
        movie = s.json().get("movie", {})
        status = movie.get("status")
        if status == "done":
            print(" ✓")
            return movie["url"]
        if status == "error":
            raise RuntimeError(f"Rendu échoué : {movie.get('message')}")
        print(".", end="", flush=True)


def download(url: str, out_path: str):
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)


# ─────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────
def main():
    print(f"\n🎬 ChannelOS v7 (B-roll + voix dynamique) — '{NICHE}'\n")

    print("① Script via Claude...")
    script = generate_script(NICHE, LANGUAGE)
    print(f"   Hook: {script['hook']}")
    broll_q = script.get("broll_query", "")
    print(f"   B-roll query: {broll_q}\n")
    with open(f"{OUTPUT_DIR}/script.json", "w") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)

    print("② Recherche B-roll Pexels...")
    broll_url = fetch_broll(broll_q)
    print(f"   {'Trouvé : ' + broll_url[:60] + '...' if broll_url else 'Aucun (fond uni)'}\n")

    print("③ Rendu cloud (fond vidéo + voix dynamique + sous-titres auto)...")
    spec = build_movie_spec(script, broll_url)
    with open(f"{OUTPUT_DIR}/movie_spec.json", "w") as f:
        json.dump(spec, f, indent=2)

    video_url = render_video(spec)
    download(video_url, f"{OUTPUT_DIR}/video.mp4")

    print(f"\n✅ Terminé !  🎥 {OUTPUT_DIR}/video.mp4")
    print(f"   URL : {video_url}\n")


if __name__ == "__main__":
    main()