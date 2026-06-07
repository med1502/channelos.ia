"""
ChannelOS — Orchestrateur end-to-end
====================================
Une seule commande : niche → vidéo prête à poster.

Chaîne complète :
  1. TrendResearchAgent  → idées sûres ancrées dans l'actualité réelle (Tavily)
  2. Sélection            → meilleure idée (ou choix manuel via --pick)
  3. ScriptWriter         → développe le script complet depuis l'idée
  4. Pipeline vidéo       → voix Azure + B-roll Pexels + sous-titres auto (JSON2Video)
  5. Sortie               → MP4 + métadonnées (caption, hashtags, affiliate)

Usage :
  python3 channelos.py "AI tools for entrepreneurs"
  python3 channelos.py "AI tools for entrepreneurs" --pick 3   # choisir l'idée #3
  python3 channelos.py "AI tools for entrepreneurs" --ideas-only  # juste les idées

Clés requises :
  ANTHROPIC_API_KEY, TAVILY_API_KEY, JSON2VIDEO_API_KEY, PEXELS_API_KEY
"""

import os
import sys
import json
import time
import argparse
import requests

# Réutilise les briques déjà construites et validées
from trend_research_agent import search_trends, generate_ideas, filter_brand_safety
import db
from niches_config import get_niche, list_niches, DEFAULT_NICHE
from youtube_trends_agent import get_youtube_insights

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Ces valeurs sont remplacées dynamiquement selon la niche + langue choisie
LANGUAGE = "EN"
LANG_CODE = "en"
VOICE = "en-US-AndrewMultilingualNeural"
J2V_URL = "https://api.json2video.com/v2/movies"


# ─────────────────────────────────────────────────────────
# ÉTAPE 3 — ScriptWriter : idée → script complet parlé
# ─────────────────────────────────────────────────────────
def write_script(idea: dict, language: str) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    fmt = idea.get("format", "single")
    format_guidance = {
        "ranking": (
            "FORMAT = RANKING. Structure the script as a countdown/list using "
            "these items: " + json.dumps(idea.get("list_items", [])) + ". "
            "Count UP toward the best (e.g. 'Number 3... Number 2... and number 1'). "
            "Tease that #1 is the best so viewers stay. Each item gets one punchy line."
        ),
        "versus": (
            "FORMAT = VERSUS. Compare the two options: "
            + json.dumps(idea.get("versus", {})) + ". "
            "Set up the matchup, give 1-2 points each, then declare the winner at the end."
        ),
        "single": (
            "FORMAT = SINGLE. Deep dive on one story/tool. Follow the structure beats."
        ),
    }.get(fmt, "FORMAT = SINGLE.")

    prompt = f"""You are a short-form video scriptwriter. Turn this idea into a
complete spoken script for a ~30-second faceless {language} TikTok/Reels video.

IDEA:
- Title: {idea['title']}
- Hook: {idea['hook']}
- Angle: {idea['angle']}
- Structure beats: {json.dumps(idea.get('structure', []))}
- Affiliate angle: {idea.get('affiliate_angle', '')}

{format_guidance}

Rules:
- Open with the EXACT hook provided (it's already optimized)
- 55-70 words TOTAL (hard limit — short = higher retention). Be punchy, cut filler.
- Naturally lead toward the affiliate angle without being salesy
- End with a CTA mentioning "link in bio"
- Stay factual and brand-safe (no hype, no distortion)

Return ONLY valid JSON, no markdown:
{{
  "spoken_text": "the full voiceover text, hook first",
  "caption": "the post caption",
  "hashtags": ["#...", "#..."],
  "screen_items": ["short on-screen labels matching the format, e.g. ranking entries or 'A vs B'"]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw), msg  # msg renvoyé pour le tracking des coûts


# ─────────────────────────────────────────────────────────
# ÉTAPE 4a — B-roll Pexels
# ─────────────────────────────────────────────────────────
def _pexels_search(query: str, count: int = 5) -> list:
    """Retourne une liste d'URLs de vidéos verticales Pexels pour une requête."""
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
        )
        r.raise_for_status()
        for v in r.json().get("videos", []):
            files = sorted(v["video_files"],
                           key=lambda f: (f.get("height") or 0), reverse=True)
            for f in files:
                if (f.get("height") or 0) >= (f.get("width") or 0):
                    urls.append(f["link"])
                    break
    except Exception as e:
        print(f"   ⚠️ B-roll Pexels échoué : {e}")
    return urls


def fetch_broll(query: str) -> str:
    """Un seul clip (compat. ascendante)."""
    urls = _pexels_search(query, 5)
    return urls[0] if urls else ""


def fetch_broll_multi(queries: list, fallback_query: str, n: int) -> list:
    """
    Récupère n clips B-roll distincts. Utilise les requêtes spécifiques
    (une par item du ranking) et complète avec la requête générale si besoin.
    """
    clips = []
    # un clip par requête spécifique
    for q in queries:
        urls = _pexels_search(q, 3)
        # éviter les doublons
        pick = next((u for u in urls if u not in clips), None)
        if pick:
            clips.append(pick)
        if len(clips) >= n:
            break
    # compléter avec la requête générale
    if len(clips) < n:
        extra = _pexels_search(fallback_query, n * 2)
        for u in extra:
            if u not in clips:
                clips.append(u)
            if len(clips) >= n:
                break
    return clips[:n]


# ─────────────────────────────────────────────────────────
# ÉTAPE 4b — Rendu JSON2Video
# ─────────────────────────────────────────────────────────
def render_video(spoken_text: str, broll_url: str, hook: str = "",
                 broll_clips=None, screen_items=None, fmt="single") -> tuple:
    """
    Construit et rend la vidéo.
    - Intro (2s) : hook géant = arrêt-scroll + thumbnail
    - Contenu : voix + sous-titres auto. Si fmt=ranking et clips multiples,
      le B-roll change par segment et un GROS numéro s'affiche.
    """
    api_key = os.environ["JSON2VIDEO_API_KEY"]
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    broll_clips = broll_clips or ([broll_url] if broll_url else [])
    first_clip = broll_clips[0] if broll_clips else ""

    # ───── SCÈNE 1 : intro hook géant ─────
    hook_text = (hook or spoken_text).strip()
    hw = hook_text.split()
    if len(hw) > 12:
        hook_text = " ".join(hw[:12]) + "…"

    intro_elements = []
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
         "settings": {"font-family": "Roboto", "font-size": "90px",
                      "font-weight": "900", "color": "#FFFFFF",
                      "text-align": "center", "vertical-align": "center",
                      "horizontal-align": "center", "shadow": 3}},
    ]
    intro_scene = {"background-color": "#0D1117", "duration": 2.0,
                   "elements": intro_elements}

    # ───── SCÈNE 2 : contenu ─────
    content_elements = []

    if first_clip:
        content_elements.append({
            "type": "video", "src": first_clip, "loop": -1, "duration": -2,
            "x": 0, "y": 0, "width": 1080, "height": 1920,
            "resize": "cover", "volume": 0,
        })
        content_elements.append({
            "type": "html",
            "html": "<div style='width:1080px;height:1920px;"
                    "background:rgba(0,0,0,0.4);'></div>",
            "duration": -2, "x": 0, "y": 0, "width": 1080, "height": 1920,
        })

    # La voix pilote la durée
    content_elements.append({
        "type": "voice", "model": "azure", "voice": VOICE,
        "text": spoken_text, "duration": -1,
    })

    content_scene = {"background-color": "#0D1117", "duration": -1,
                     "elements": content_elements}

    spec = {
        "width": 1080, "height": 1920, "quality": "high",
        "scenes": [intro_scene, content_scene],
        "elements": [{
            "type": "subtitles", "language": LANG_CODE,
            "settings": {
                "style": "classic-progressive", "font-family": "Roboto",
                "font-size": 95, "font-weight": 900,
                "word-color": "#00E5FF", "line-color": "#FFFFFF",
                "outline-color": "#000000", "outline-width": 7,
                "position": "center",
            },
        }],
    }

    r = requests.post(J2V_URL, headers=headers, json=spec)
    r.raise_for_status()
    project_id = r.json()["project"]

    print("   Rendu en cours", end="", flush=True)
    while True:
        time.sleep(4)
        s = requests.get(J2V_URL, headers=headers, params={"project": project_id})
        s.raise_for_status()
        movie = s.json().get("movie", {})
        if movie.get("status") == "done":
            print(" ✓")
            return movie["url"], movie.get("duration", 0)
        if movie.get("status") == "error":
            raise RuntimeError(f"Rendu échoué : {movie.get('message')}")
        print(".", end="", flush=True)


def download(url: str, out_path: str):
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)


# ─────────────────────────────────────────────────────────
# ORCHESTRATION
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("niche")
    parser.add_argument("--pick", type=int, default=1,
                        help="numéro de l'idée à produire (défaut: 1, la mieux scorée)")
    parser.add_argument("--ideas-only", action="store_true",
                        help="s'arrêter après les idées, sans produire de vidéo")
    parser.add_argument("--n", type=int, default=5, help="nombre d'idées à générer")
    parser.add_argument("--niche-profile", default=DEFAULT_NICHE,
                        help="profil de niche: " + ", ".join(k for k, _ in list_niches()))
    parser.add_argument("--lang", default="EN", choices=["EN", "FR"],
                        help="langue de la vidéo (EN ou FR)")
    args = parser.parse_args()

    # Charger le profil de niche et configurer les globals
    global LANGUAGE, LANG_CODE, VOICE
    niche_profile = get_niche(args.niche_profile)
    LANGUAGE = args.lang
    LANG_CODE = args.lang.lower()
    VOICE = niche_profile["voices"].get(args.lang, "en-US-AndrewMultilingualNeural")

    print(f"\n{'='*60}")
    print(f"  ChannelOS — '{args.niche}' ({LANGUAGE}) [{niche_profile['name']}]")
    print(f"  Audience : {niche_profile['audience']}")
    print(f"  Voix     : {VOICE}")
    print(f"{'='*60}\n")

    # 1 + 2 — Tendances réelles → idées sûres
    print("① Recherche des tendances réelles (Tavily)...")
    trends = search_trends(args.niche)
    # 3 requêtes basiques = ~3 crédits (sauf cache hit)
    db.log_cost("tavily", "trends", 3, "credits")
    print(f"   {len(trends)} signaux récupérés\n")

    print("①bis Analyse des vidéos YouTube top de la niche...")
    yt_insights = get_youtube_insights(args.niche, niche_profile["name"])
    if yt_insights:
        print(f"   {yt_insights.get('_sample_count', 0)} vidéos analysées — patterns extraits")
    print()

    print(f"② Génération + filtrage brand-safety de {args.n} idées (Claude)...")
    raw_ideas = generate_ideas(args.niche, LANGUAGE, trends, args.n, niche_profile, yt_insights)
    # coût approximatif de génération d'idées (gros prompt + sortie)
    db.log_cost("anthropic", "ideas",
                {"input": 2000, "output": 2500}, "tokens")
    safe, flagged = filter_brand_safety(raw_ideas)
    with open(f"{OUTPUT_DIR}/ideas.json", "w") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)
    print(f"   {len(safe)} idées sûres ({len(flagged)} écartée(s))\n")

    for i, idea in enumerate(safe, 1):
        print(f"   #{i} [{idea['viral_score']}] {idea['title']}")
    print()

    if args.ideas_only:
        print("✅ Idées générées (mode --ideas-only).\n")
        return

    # 3 — Sélection + persistance de l'idée
    pick = max(1, min(args.pick, len(safe)))
    idea = safe[pick - 1]
    print(f"③ Idée sélectionnée : #{pick} — {idea['title']}")

    idea_id = db.save_idea(idea)          # → enregistrée en base
    print(f"   Idée enregistrée (id={idea_id})")
    print(f"   Développement du script (Claude)...")
    script, script_msg = write_script(idea, LANGUAGE)
    db.log_anthropic(script_msg, operation="script", idea_id=idea_id)
    print(f"   Hook: {script['spoken_text'][:70]}...\n")

    # 4 — B-roll + rendu
    print("④ Recherche B-roll Pexels...")
    broll = fetch_broll(idea.get("broll_query", args.niche))
    db.log_cost("pexels", "broll", 1, "request", idea_id=idea_id)
    print(f"   {'✓ trouvé' if broll else '✗ aucun (fond uni)'}\n")

    print("⑤ Rendu vidéo (JSON2Video)...")
    video_url, duration = render_video(
        script["spoken_text"], broll, idea.get("hook", ""),
        broll_clips=[broll] if broll else None,
        screen_items=script.get("screen_items", []),
        fmt=idea.get("format", "single"),
    )
    video_path = f"{OUTPUT_DIR}/video.mp4"
    download(video_url, video_path)

    # Persistance vidéo + coûts
    video_id = db.save_video(idea_id, script, broll, video_url,
                             video_path, duration)
    db.log_cost("json2video", "render", duration or 0, "seconds",
                video_id=video_id, idea_id=idea_id)
    # rattacher le coût du script à la vidéo aussi (déjà loggé par idea_id)
    print(f"   Vidéo enregistrée (id={video_id}, {duration}s)")

    # Métadonnées de publication
    meta = {
        "title": idea["title"],
        "caption": script.get("caption", ""),
        "hashtags": script.get("hashtags", []),
        "affiliate_angle": idea.get("affiliate_angle", ""),
        "based_on_trend": idea.get("based_on_trend", ""),
        "viral_score": idea.get("viral_score"),
        "video_url": video_url,
    }
    with open(f"{OUTPUT_DIR}/post_package.json", "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"✅ VIDÉO PRÊTE À POSTER")
    print(f"{'='*60}")
    print(f"   🎥 {video_path}")
    print(f"   📝 Caption : {meta['caption']}")
    print(f"   #️⃣  {' '.join(meta['hashtags'])}")
    print(f"   💰 Affiliate : {meta['affiliate_angle']}")
    print(f"   📦 Package complet : {OUTPUT_DIR}/post_package.json")
    # Coût réel de cette vidéo (depuis la base)
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COALESCE(SUM(cost_usd),0) AS c FROM cost_log "
                        "WHERE video_id=%s OR idea_id=%s", (video_id, idea_id))
            run_cost = cur.fetchone()["c"]
        print(f"   💵 Coût de cette vidéo : ${float(run_cost):.4f}")
    except Exception:
        pass
    print()


if __name__ == "__main__":
    main()