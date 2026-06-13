"""
ChannelOS — Database client
Persistence + cost tracking for every pipeline run.

Usage:
  python3 -m channelos.db.client init    # create schema
  python3 -m channelos.db.client costs   # show cost report
"""

import os
import sys
import json
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://channelos:channelos@localhost:5432/channelos",
)

# Reference pricing (USD) — adjust to your actual plan
PRICING = {
    "anthropic": {
        "input_per_token":  3.0 / 1_000_000,   # Sonnet input
        "output_per_token": 15.0 / 1_000_000,  # Sonnet output
    },
    "tavily":     {"per_credit": 0.008},    # 1 basic search = 1 credit
    "json2video": {"per_second": 0.004},    # ~1 credit/second rendered
    "pexels":     {"per_request": 0.0},     # free
}


# ── Connection ────────────────────────────────────────────────────────────────

def connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(DATABASE_URL, connect_timeout=5)


# ── Schema ────────────────────────────────────────────────────────────────────

def init_schema(schema_path: str | None = None) -> None:
    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path) as f:
        sql = f.read()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    print("✅ Schema initialised")


# ── Write ─────────────────────────────────────────────────────────────────────

def save_idea(idea: dict, channel_id: int | None = None) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ideas
              (channel_id, title, hook, angle, structure, broll_query,
               affiliate_angle, viral_score, score_reason, based_on_trend,
               brand_safe, format, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'selected')
            RETURNING id
            """,
            (
                channel_id,
                idea.get("title"),
                idea.get("hook"),
                idea.get("angle"),
                json.dumps(idea.get("structure", [])),
                idea.get("broll_query"),
                idea.get("affiliate_angle"),
                idea.get("viral_score"),
                idea.get("score_reason"),
                idea.get("based_on_trend"),
                idea.get("brand_safe", True),
                idea.get("format", "single"),
            ),
        )
        idea_id = cur.fetchone()[0]
        conn.commit()
    return idea_id


def save_video(
    idea_id: int,
    script: dict,
    broll_url: str,
    video_url: str,
    local_path: str,
    *,
    hook_pattern: str,
    format: str,
    niche: str,
    lang: str,
    channel_id: int,
    arm: str,
    duration: float | None = None,
    yt_video_id: str | None = None,
) -> int:
    """Persist a produced video WITH the full decision context (TCK-03)."""
    if arm not in ("bandit", "baseline"):
        raise ValueError(f"arm must be 'bandit' or 'baseline', got {arm!r}")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO videos
              (idea_id, spoken_text, caption, hashtags, broll_url,
               video_url, local_path, duration_sec,
               hook_pattern, format, niche, lang, channel_id, arm,
               yt_video_id, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,'downloaded')
            RETURNING id
            """,
            (
                idea_id,
                script.get("spoken_text"),
                script.get("caption"),
                json.dumps(script.get("hashtags", [])),
                broll_url,
                video_url,
                local_path,
                duration,
                hook_pattern,
                format,
                niche,
                lang,
                channel_id,
                arm,
                yt_video_id,
            ),
        )
        video_id = cur.fetchone()[0]
        cur.execute("UPDATE ideas SET status='produced' WHERE id=%s", (idea_id,))
        conn.commit()
    return video_id


def mark_published(video_id: int, yt_video_id: str,
                   published_at=None) -> None:
    """published_at: datetime du créneau programmé (publishAt). None = NOW()."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE videos SET status='published', "
            "published_at=COALESCE(%s, NOW()), "
            "yt_video_id=%s WHERE id=%s",
            (published_at, yt_video_id, video_id),
        )
        conn.commit()


def save_performance(
    video_id: int,
    *,
    platform: str = "youtube",
    views: int = 0,
    likes: int = 0,
    shares: int = 0,
    comments: int = 0,
    retention_pct: float | None = None,
) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT hook_pattern, format, niche, lang, arm "
            "FROM videos WHERE id=%s",
            (video_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"no video with id={video_id}")
        hook_pattern, fmt, niche, lang, arm = row
        cur.execute(
            """
            INSERT INTO performance
              (video_id, platform, views, likes, shares, comments,
               retention_pct, hook_pattern, format, niche, lang, arm)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (video_id, platform, views, likes, shares, comments,
             retention_pct, hook_pattern, fmt, niche, lang, arm),
        )
        perf_id = cur.fetchone()[0]
        conn.commit()
    return perf_id


def log_cost(
    provider: str,
    operation: str,
    units: float | dict,
    unit_type: str,
    video_id: int | None = None,
    idea_id: int | None = None,
) -> float:
    cost = estimate_cost(provider, unit_type, units)
    units_scalar = sum(units.values()) if isinstance(units, dict) else units
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cost_log
              (video_id, idea_id, provider, operation, units, unit_type, cost_usd)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (video_id, idea_id, provider, operation, units_scalar, unit_type, cost),
        )
        conn.commit()
    return cost


def log_anthropic(
    msg,
    operation: str,
    video_id: int | None = None,
    idea_id: int | None = None,
) -> float:
    """Helper: log cost from an Anthropic SDK response object."""
    usage = getattr(msg, "usage", None)
    if not usage:
        return 0.0
    units = {"input": usage.input_tokens, "output": usage.output_tokens}
    cost = estimate_cost("anthropic", "tokens", units)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cost_log
              (video_id, idea_id, provider, operation, units, unit_type, cost_usd)
            VALUES (%s,%s,'anthropic',%s,%s,'tokens',%s)
            """,
            (
                video_id,
                idea_id,
                operation,
                usage.input_tokens + usage.output_tokens,
                cost,
            ),
        )
        conn.commit()
    return cost


# ── Pricing ───────────────────────────────────────────────────────────────────

def estimate_cost(provider: str, unit_type: str, units: float | dict) -> float:
    p = PRICING.get(provider, {})
    if provider == "anthropic":
        if isinstance(units, dict):
            return (
                units.get("input", 0) * p["input_per_token"]
                + units.get("output", 0) * p["output_per_token"]
            )
        return 0.0
    if provider == "tavily":
        return float(units) * p.get("per_credit", 0)
    if provider == "json2video":
        return float(units) * p.get("per_second", 0)
    return 0.0


# ── Reporting ─────────────────────────────────────────────────────────────────

def show_costs() -> None:
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM video_costs ORDER BY created_at DESC LIMIT 20")
        rows = cur.fetchall()
        cur.execute("SELECT COALESCE(SUM(cost_usd),0) AS total FROM cost_log")
        total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS n FROM videos")
        n = cur.fetchone()["n"]

    print(f"\n{'='*60}")
    print("  CHANNELOS — COST REPORT")
    print(f"{'='*60}")
    print(f"  Videos produced : {n}")
    print(f"  Total cost      : ${float(total):.4f}")
    if n:
        print(f"  Avg cost/video  : ${float(total)/int(n):.4f}")
    print(f"{'='*60}\n")
    for r in rows:
        print(
            f"  🎥 #{r['video_id']} {str(r['idea_title'])[:42]:44}"
            f"${float(r['total_cost_usd']):.4f}"
        )
        if r["cost_breakdown"]:
            for prov, c in r["cost_breakdown"].items():
                print(f"        {prov:12} ${float(c):.4f}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli() -> None:
    """Entry point for `python3 -m channelos.db.client [init|costs]`."""
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "init":
        init_schema()
    elif cmd == "costs":
        show_costs()
    else:
        print("Usage: python3 -m channelos.db.client [init|costs]")


if __name__ == "__main__":
    cli()


# ── Dédup idées & B-roll (migration 003) ─────────────────────────────────────

def get_recent_published_titles(days: int = 14) -> list[str]:
    """Titres des vidéos published/deleted des N derniers jours (anti-clone)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT i.title FROM videos v JOIN ideas i ON i.id = v.idea_id "
            "WHERE v.published_at > NOW() - make_interval(days => %s)",
            (days,),
        )
        return [r[0] for r in cur.fetchall() if r[0]]


def get_used_broll_urls(days: int = 30) -> set[str]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT url FROM used_broll WHERE used_at > NOW() - make_interval(days => %s)",
            (days,),
        )
        return {r[0] for r in cur.fetchall()}


def record_broll_urls(urls: list[str], video_id: int | None = None) -> None:
    with connect() as conn, conn.cursor() as cur:
        for u in urls:
            cur.execute(
                "INSERT INTO used_broll (url, video_id) VALUES (%s, %s) "
                "ON CONFLICT (url) DO UPDATE SET used_at = NOW()",
                (u, video_id),
            )
        conn.commit()
