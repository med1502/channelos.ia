"""
ChannelOS IA — Main orchestrator
=================================
One command → one ready-to-post short-form video.

Usage:
  python3 -m channelos "AI tools for entrepreneurs"
  python3 -m channelos "AI tools" --niche-profile ai_entrepreneurs --lang EN
  python3 -m channelos "AI tools" --ideas-only
  python3 -m channelos "AI tools" --pick 3
  python3 -m channelos "AI tools" --batch 5
"""

import os
import sys
import json
import argparse
from pathlib import Path

from channelos.config import get_niche, list_niches, DEFAULT_NICHE
from channelos.agents import (
    search_trends, generate_ideas, filter_brand_safety,
    get_youtube_insights, write_script,
)
from channelos.pipeline.render import (
    fetch_broll, fetch_broll_multi, render_video, download_video,
)
import channelos.db as db

from dotenv import load_dotenv
load_dotenv()

def _resolve_channel_id(niche_key: str) -> int | None:
    """Chaîne du niche la moins chargée (équilibrage persistant inter-processus).

    Remplace le round-robin en mémoire: chaque invocation CLI étant un
    processus neuf, seul un état en DB équilibre réellement les chaînes."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id
            FROM channels c
            LEFT JOIN videos v ON v.channel_id = c.id
            WHERE c.niche_key = %s
            GROUP BY c.id
            ORDER BY COUNT(v.id) ASC, c.id ASC
            LIMIT 1
            """,
            (niche_key,),
        )
        row = cur.fetchone()
    return row[0] if row else None

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def run_pipeline(args: argparse.Namespace, niche_profile: dict) -> None:
    """Execute the full pipeline for one video."""
    language = args.lang
    lang_code = language.lower()
    voice = niche_profile["voices"].get(language, "en-US-AndrewMultilingualNeural")

    print(f"\n{'='*60}")
    print(f"  ChannelOS — '{args.niche}' ({language}) [{niche_profile['name']}]")
    print(f"  Audience : {niche_profile['audience']}")
    print(f"  Voice    : {voice}")
    print(f"{'='*60}\n")

    # ① Trends (Tavily)
    print("① Searching real trends (Tavily)...")
    trends = search_trends(args.niche)
    db.log_cost("tavily", "trends", 3, "credits")
    print(f"   {len(trends)} signals retrieved\n")

    # ①bis YouTube patterns
    print("①bis Analysing top YouTube videos...")
    yt_insights = get_youtube_insights(args.niche, niche_profile["name"])
    if yt_insights:
        print(f"   {yt_insights.get('_sample_count', 0)} videos analysed")
    print()

    # ② Ideas
    print(f"② Generating + brand-safety filtering {args.n} ideas (Claude)...")
    raw_ideas = generate_ideas(args.niche, language, trends, args.n, niche_profile, yt_insights)
    db.log_cost("anthropic", "ideas", {"input": 2000, "output": 2500}, "tokens")
    safe, flagged = filter_brand_safety(raw_ideas)
    (OUTPUT_DIR / "ideas.json").write_text(
        json.dumps(safe, indent=2, ensure_ascii=False)
    )
    print(f"   {len(safe)} safe ideas ({len(flagged)} flagged)\n")

    for i, idea in enumerate(safe, 1):
        print(f"   #{i} [{idea['viral_score']}] {idea['title']}")
    print()

    if args.ideas_only:
        print("✅ Ideas generated (--ideas-only mode).\n")
        return

# ADR-009: filtrer au format de l'expérience (la grille est gelée)
    if args.format != "any":
        matching = [i for i in safe if i.get("format") == args.format]
        if matching:
            safe = matching
            print(f"   Filtre format={args.format}: {len(safe)} idée(s) retenue(s)\n")
        else:
            print(f"   ⚠️  Aucune idée au format {args.format} — run abandonné "
                  f"(relancer, ou --format any pour outrepasser)")
            return
    # Anti-clone: écarter les idées trop proches d'une vidéo récente
    from channelos.agents.trend_agent import filter_already_used
    fresh, dupes = filter_already_used(safe, db.get_recent_published_titles())
    if dupes:
        print(f"   ♻️  {len(dupes)} idee(s) ecartee(s) (trop proche d'une video recente)")
    if not fresh:
        raise SystemExit("❌ Toutes les idees ressemblent a des videos deja publiees. "
                         "Varie le mot-cle ou attends de nouveaux trends.")
    safe = fresh

    # ③ Select idea
    pick = max(1, min(args.pick, len(safe)))
    idea = safe[pick - 1]
    print(f"③ Selected idea #{pick} — {idea['title']}")
    if getattr(args, "title", None):
        if len(args.title) > 92:   # 100 - len(" #Shorts")
            raise SystemExit(f"❌ Titre trop long ({len(args.title)} car., max 92 avec #Shorts)")
        idea["title"] = args.title
        print(f"   Titre forcé: {args.title}")
    if getattr(args, "hook", None):
        if len(args.hook) > 100:
            raise SystemExit(f"❌ Hook trop long ({len(args.hook)} car., max 100 — frame d'intro)")
        idea["hook"] = args.hook
        print(f"   Hook forcé: {args.hook}")



    idea_id = db.save_idea(idea)
    print(f"   Idea saved (id={idea_id})")
    print("   Writing script (Claude)...")
    script, script_msg = write_script(idea, language)
    db.log_anthropic(script_msg, operation="script", idea_id=idea_id)
    print(f"   Hook: {script['spoken_text'][:70]}...\n")

    # ④ B-roll
    print("④ Fetching B-roll (Pexels)...")
    fmt = idea.get("format", "single")
    if fmt == "ranking" and idea.get("list_items"):
        broll_queries = [f"{item} business" for item in idea["list_items"]]
        broll_clips = fetch_broll_multi(
            broll_queries,
            fallback_query=idea.get("broll_query", args.niche),
            n=len(idea["list_items"]),
        )
        broll_url = broll_clips[0] if broll_clips else ""
    else:
        broll_url = fetch_broll(idea.get("broll_query", args.niche))
        broll_clips = [broll_url] if broll_url else []

    # Anti-répétition B-roll: écarter les clips déjà vus (garder l'original si tout vu)
    _used = db.get_used_broll_urls()
    _fresh_clips = [c for c in broll_clips if c not in _used]
    if _fresh_clips:
        broll_clips = _fresh_clips
        broll_url = broll_clips[0]
    elif broll_clips:
        print("   ♻️  clips deja vus — reutilisation acceptee (fallback)")
    db.log_cost("pexels", "broll", 1, "request", idea_id=idea_id)
    print(f"   {'✓ ' + str(len(broll_clips)) + ' clip(s) found' if broll_clips else '✗ none (solid background)'}\n")
    
    if args.no_render:
        print("⏭️  --no-render: pipeline validé jusqu'au B-roll, 0 crédit consommé.\n")
        return
    # ⑤ Render
    print("⑤ Rendering video (JSON2Video)...")
    video_url, duration = render_video(
        spoken_text=script["spoken_text"],
        broll_url=broll_url,
        hook=idea.get("hook", ""),
        broll_clips=broll_clips,
        screen_items=(idea.get("list_items") if fmt == "ranking" and idea.get("list_items")
                      else script.get("screen_items", [])),
        fmt=fmt,
        voice=voice,
        lang_code=lang_code,
    )
    video_path = str(OUTPUT_DIR / "video.mp4")
    download_video(video_url, video_path)
 
    # ── Decision context (TCK-03) — stamped at creation, before any publish ──
    niche_key = niche_profile.get("key", args.niche_profile)
    hook_pattern = idea.get("hook_pattern", "unknown")   # TODO TCK-11: tag in IdeaGenerator
    arm = getattr(args, "arm", "baseline")               # TCK-13 will set 'bandit'
    channel_id_used = getattr(args, "channel_id", None) or _resolve_channel_id(niche_key)
 
    video_id = db.save_video(
        idea_id,
        script,
        broll_url,
        video_url,
        video_path,
        hook_pattern=hook_pattern,
        format=fmt,
        niche=niche_key,
        lang=language,
        channel_id=channel_id_used,
        arm=arm,
        duration=duration,
    )
    db.log_cost("json2video", "render", duration or 0, "seconds",
                video_id=video_id, idea_id=idea_id)
    db.record_broll_urls(broll_clips, video_id)
    print(f"   Video saved (id={video_id}, {duration}s, "
          f"niche={niche_key}, pattern={hook_pattern}, arm={arm})")
 
    # Output package — construit AVANT le publish (qui l'enrichit)
    meta = {
        "title": idea["title"],
        "caption": script.get("caption", ""),
        "hashtags": script.get("hashtags", []),
        "affiliate_angle": idea.get("affiliate_angle", ""),
        "based_on_trend": idea.get("based_on_trend", ""),
        "viral_score": idea.get("viral_score"),
        "video_url": video_url,
    }
 
    # ⑥ Publish (TCK-06)
    if args.publish:
        from channelos.pipeline.publisher import publish
        if channel_id_used is None:
            print("⚠️  Aucune chaîne configurée pour ce niche — publish sauté.")
            print("    Peupler la table channels puis relancer avec --publish.")
        else:
            print("⑥ Publishing to YouTube...")
            publish_at = None
            if getattr(args, "schedule", False):
                from datetime import datetime, timezone
                from channelos.pipeline.publisher import _next_publish_slot
                with db.connect() as conn, conn.cursor() as cur:
                    cur.execute("SELECT MAX(published_at) FROM videos "
                                "WHERE status IN ('published','scheduled')")
                    last = cur.fetchone()[0]
                publish_at = _next_publish_slot(datetime.now(timezone.utc), last)
                print(f"   📅 Publication programmée: {publish_at.isoformat()}")
            yt_video_id = publish(video_id, video_path, meta, channel_id_used,
                                  publish_at=publish_at)
            meta["yt_video_id"] = yt_video_id
            meta["yt_url"] = f"https://youtube.com/shorts/{yt_video_id}"
 
    # Écrit UNE seule fois, après publish — sinon les champs yt_* sont écrasés
    (OUTPUT_DIR / "post_package.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False)
    )
 
    print(f"\n{'='*60}")
    print("✅ VIDEO READY TO POST")
    print(f"{'='*60}")
    print(f"   🎥 {video_path}")
    print(f"   📝 {meta['caption']}")
    print(f"   #️⃣  {' '.join(meta['hashtags'])}")
    print(f"   💰 {meta['affiliate_angle']}")
    if meta.get("yt_url"):
        print(f"   ▶️  {meta['yt_url']}")
    print(f"   📦 output/post_package.json")
 

    # Cost for this run
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT COALESCE(SUM(cost_usd),0) AS c FROM cost_log "
                "WHERE video_id=%s OR idea_id=%s",
                (video_id, idea_id),
            )
            run_cost = cur.fetchone()["c"]
        print(f"   💵 Cost this video: ${float(run_cost):.4f}")
    except Exception:
        pass
    print()


def main() -> None:
    parser = argparse.ArgumentParser(prog="channelos")
    parser.add_argument("niche")
    parser.add_argument("--pick", type=int, default=1,
                        help="idea number to produce (default: 1 = top scored)")
    parser.add_argument("--ideas-only", action="store_true",
                        help="stop after ideas, no video")
    parser.add_argument("--n", type=int, default=5,
                        help="number of ideas to generate")
    parser.add_argument("--niche-profile", default=DEFAULT_NICHE,
                        help="niche profile: " + ", ".join(k for k, _ in list_niches()))
    parser.add_argument("--lang", default="EN", choices=["EN", "FR"],
                        help="video language")
    parser.add_argument("--batch", type=int, default=0,
                        help="generate N videos (ideas 1..N) in one run")
    parser.add_argument("--publish", action="store_true",
                        help="upload sur YouTube après le render")
    parser.add_argument("--no-render", action="store_true",
                        help="stop après le script + B-roll, zéro crédit render")
    parser.add_argument("--format", default="ranking",
                        choices=["ranking", "versus", "single", "any"],
                        help="ne produire que ce format (ADR-009: ranking pour les 90j)")
    parser.add_argument("--title", type=str, default=None,
                        help="Force le titre de la vidéo (remplace celui de l'idée)")
    parser.add_argument("--hook", type=str, default=None,
                        help="Force le hook (phrase d'ouverture + frame d'intro)")
    parser.add_argument("--schedule", action="store_true",
                        help="Publie en différé au prochain créneau optimal (publishAt YouTube)")
    args = parser.parse_args()

    niche_profile = get_niche(args.niche_profile)

    if args.batch > 0:
        print(f"\n🔄 Batch mode: generating {args.batch} videos\n")
        for i in range(1, args.batch + 1):
            print(f"\n{'─'*60}")
            print(f"  Batch {i}/{args.batch}")
            print(f"{'─'*60}")
            args.pick = i
            run_pipeline(args, niche_profile)
    else:
        run_pipeline(args, niche_profile)


if __name__ == "__main__":
    main()
