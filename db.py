"""
ChannelOS — Couche de persistance + tracking des coûts
======================================================
S'intègre dans channelos.py pour enregistrer chaque run en base
et calculer le coût réel par vidéo.

Dépendances : pip install psycopg2-binary

DB : utilise DATABASE_URL (Docker Compose) ou les valeurs par défaut.
Initialise le schéma avec :  python3 db.py init
Affiche les coûts avec    :  python3 db.py costs
"""

import os
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/channelos",
)

# ─────────────────────────────────────────────────────────
# Tarifs de référence (USD) — pour estimer les coûts
# Ajuste selon ton plan réel
# ─────────────────────────────────────────────────────────
PRICING = {
    "anthropic": {  # Claude Sonnet, par token
        "input_per_token": 3.0 / 1_000_000,
        "output_per_token": 15.0 / 1_000_000,
    },
    "tavily": {"per_credit": 0.008},          # 1 recherche basique = 1 crédit
    "json2video": {"per_second": 0.004},      # ~ selon plan (1 crédit/seconde)
    "pexels": {"per_request": 0.0},           # gratuit
}


def connect():
    return psycopg2.connect(DATABASE_URL)


# ─────────────────────────────────────────────────────────
# INIT — créer le schéma
# ─────────────────────────────────────────────────────────
def init_schema(schema_path="schema.sql"):
    with open(schema_path) as f:
        sql = f.read()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    print("✅ Schéma initialisé")


# ─────────────────────────────────────────────────────────
# ENREGISTREMENT — idée, vidéo, coûts
# ─────────────────────────────────────────────────────────
def save_idea(idea: dict, channel_id=None) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ideas
               (channel_id, title, hook, angle, structure, broll_query,
                affiliate_angle, viral_score, score_reason, based_on_trend,
                brand_safe, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'selected')
               RETURNING id""",
            (channel_id, idea.get("title"), idea.get("hook"), idea.get("angle"),
             json.dumps(idea.get("structure", [])), idea.get("broll_query"),
             idea.get("affiliate_angle"), idea.get("viral_score"),
             idea.get("score_reason"), idea.get("based_on_trend"),
             idea.get("brand_safe", True)),
        )
        idea_id = cur.fetchone()[0]
        conn.commit()
    return idea_id


def save_video(idea_id: int, script: dict, broll_url: str,
               video_url: str, local_path: str, duration: float = None) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO videos
               (idea_id, spoken_text, caption, hashtags, broll_url,
                video_url, local_path, duration_sec, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'downloaded')
               RETURNING id""",
            (idea_id, script.get("spoken_text"), script.get("caption"),
             json.dumps(script.get("hashtags", [])), broll_url,
             video_url, local_path, duration),
        )
        video_id = cur.fetchone()[0]
        # marquer l'idée comme produite
        cur.execute("UPDATE ideas SET status='produced' WHERE id=%s", (idea_id,))
        conn.commit()
    return video_id


def log_cost(provider: str, operation: str, units: float, unit_type: str,
             video_id=None, idea_id=None):
    """Enregistre un coût et le calcule selon les tarifs de référence."""
    cost = estimate_cost(provider, unit_type, units)
    units = sum(units.values()) if isinstance(units, dict) else units
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO cost_log
               (video_id, idea_id, provider, operation, units, unit_type, cost_usd)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (video_id, idea_id, provider, operation, units, unit_type, cost),
        )
        conn.commit()
    return cost


def estimate_cost(provider: str, unit_type: str, units: float) -> float:
    p = PRICING.get(provider, {})
    if provider == "anthropic":
        # units attendu sous forme dict {"input": n, "output": m}
        if isinstance(units, dict):
            return (units.get("input", 0) * p["input_per_token"]
                    + units.get("output", 0) * p["output_per_token"])
        return 0.0
    if provider == "tavily":
        return units * p.get("per_credit", 0)
    if provider == "json2video":
        return units * p.get("per_second", 0)
    return 0.0


def log_anthropic(msg, operation: str, video_id=None, idea_id=None):
    """Helper : enregistre le coût d'un appel Claude depuis l'objet réponse."""
    usage = getattr(msg, "usage", None)
    if not usage:
        return 0.0
    units = {"input": usage.input_tokens, "output": usage.output_tokens}
    cost = estimate_cost("anthropic", "tokens", units)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO cost_log
               (video_id, idea_id, provider, operation, units, unit_type, cost_usd)
               VALUES (%s,%s,'anthropic',%s,%s,'tokens',%s)""",
            (video_id, idea_id, operation,
             usage.input_tokens + usage.output_tokens, cost),
        )
        conn.commit()
    return cost


# ─────────────────────────────────────────────────────────
# REPORTING — le chiffre que tu veux voir
# ─────────────────────────────────────────────────────────
def show_costs():
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM video_costs ORDER BY created_at DESC LIMIT 20")
        rows = cur.fetchall()
        cur.execute("SELECT COALESCE(SUM(cost_usd),0) AS total FROM cost_log")
        total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS n FROM videos")
        n = cur.fetchone()["n"]

    print(f"\n{'='*60}")
    print(f"  COÛTS CHANNELOS")
    print(f"{'='*60}")
    print(f"  Vidéos produites : {n}")
    print(f"  Coût total       : ${total:.4f}")
    if n:
        print(f"  Coût moyen/vidéo : ${float(total)/n:.4f}")
    print(f"{'='*60}\n")
    for r in rows:
        print(f"  🎥 #{r['video_id']} {r['idea_title'][:40]:42} "
              f"${float(r['total_cost_usd']):.4f}")
        if r['cost_breakdown']:
            for prov, c in r['cost_breakdown'].items():
                print(f"        {prov:12} ${float(c):.4f}")
    print()


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "init":
        init_schema()
    elif cmd == "costs":
        show_costs()
    else:
        print("Usage: python3 db.py [init|costs]")