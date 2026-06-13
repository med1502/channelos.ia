"""
ChannelOS — pipeline/collect.py  (TCK-08 ✅ + TCK-09 fiabilisation)
====================================================================
Ingestion quotidienne YouTube Analytics → table `performance`.

TCK-09 — fiabilisation:
  - Retries avec backoff sur erreurs transitoires (5xx, 429) — 3 tentatives
  - Classification des erreurs permanentes (403 = chaîne étrangère/token,
    404 = vidéo supprimée) → skip propre, pas de retry inutile
  - Détection de trous: vidéo published >3 jours SANS ligne performance = alerte
  - Résumé daté en fin de run (lisible dans logs/collect.log)

Métrique (TCK-08 v2): retention_pct = averageViewDuration / duration_sec * 100,
plafonné à 300%. NULL honnête si durée inconnue — jamais un chiffre inventé.

Usage:  python3 -m channelos.pipeline.collect   ou: make collect
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import channelos.db as db
from channelos.pipeline.publisher import _get_credentials

MIN_AGE_HOURS = 24       # analytics YouTube dispo J+1 à J+3
RETENTION_CAP = 300.0    # % max plausible (boucles Shorts tolérées)
GAP_ALERT_DAYS = 3       # published depuis >3j sans perf = trou à signaler
MAX_RETRIES = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ── Retry sur erreurs transitoires ────────────────────────────────────────────

def _query_with_retry(fn, *, what: str, retries: int = MAX_RETRIES,
                      _sleep=time.sleep):
    """Exécute fn(); retry avec backoff (2s, 4s, 8s) sur erreurs transitoires.
    Les erreurs permanentes (403/404...) remontent immédiatement."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status not in RETRYABLE_STATUS:
                raise                       # permanent → pas de retry
            last = e
            if attempt < retries:
                wait = 2 ** attempt
                print(f"  ↻ retry {attempt}/{retries - 1} ({what}, "
                      f"HTTP {status}) dans {wait}s")
                _sleep(wait)
    raise RuntimeError(f"{what}: échec après {retries} tentatives "
                       f"(dernier: HTTP {getattr(last.resp, 'status', '?')})")


# ── Sélection des vidéos à collecter ──────────────────────────────────────────

def _videos_to_collect() -> list[dict]:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, yt_video_id, channel_id, published_at::date, duration_sec
            FROM videos
            WHERE status = 'published'
              AND yt_video_id IS NOT NULL
              AND channel_id IS NOT NULL
              AND published_at < NOW() - make_interval(hours => %s)
            ORDER BY id
            """,
            (MIN_AGE_HOURS,),
        )
        rows = cur.fetchall()
    return [
        {"video_id": r[0], "yt_video_id": r[1], "channel_id": r[2],
         "published_date": r[3], "duration_sec": float(r[4]) if r[4] else None}
        for r in rows
    ]


# ── Détection de trous (TCK-09) ───────────────────────────────────────────────

def _detect_gaps() -> list[tuple[int, str, str]]:
    """Vidéos published depuis > GAP_ALERT_DAYS jours sans AUCUNE ligne
    performance. Renvoie [(video_id, yt_video_id, published_at_date)]."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.id, v.yt_video_id, v.published_at::date::text
            FROM videos v
            LEFT JOIN performance p ON p.video_id = v.id
            WHERE v.status = 'published'
              AND v.published_at < NOW() - make_interval(days => %s)
              AND p.id IS NULL
            ORDER BY v.id
            """,
            (GAP_ALERT_DAYS,),
        )
        return cur.fetchall()


# ── Requête Analytics pour une vidéo ─────────────────────────────────────────

def _fetch_metrics(yta, yt_video_id: str, start_date) -> dict | None:
    common = dict(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=date.today().isoformat(),
        filters=f"video=={yt_video_id}",
    )
    resp = _query_with_retry(
        lambda: yta.reports().query(metrics="views,likes,comments",
                                    **common).execute(),
        what=f"metrics {yt_video_id}",
    )
    rows = resp.get("rows") or []
    if not rows:
        return None
    views, likes, comments = rows[0]

    resp2 = _query_with_retry(
        lambda: yta.reports().query(metrics="averageViewDuration",
                                    **common).execute(),
        what=f"avgViewDuration {yt_video_id}",
    )
    rows2 = resp2.get("rows") or []
    avg_view_sec = float(rows2[0][0]) if rows2 else None

    return {"views": int(views), "likes": int(likes),
            "comments": int(comments), "avg_view_sec": avg_view_sec}


def _compute_retention(avg_view_sec: float | None,
                       duration_sec: float | None) -> float | None:
    if avg_view_sec is None or not duration_sec:
        return None
    pct = avg_view_sec / duration_sec * 100.0
    if pct < 0:
        return None
    return round(min(pct, RETENTION_CAP), 2)


# ── Écriture: remplace l'instantané précédent ─────────────────────────────────

def _replace_performance(video_id: int, m: dict,
                         retention_pct: float | None) -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM performance WHERE video_id = %s", (video_id,))
        conn.commit()
    db.save_performance(
        video_id, platform="youtube",
        views=m["views"], likes=m["likes"], comments=m["comments"],
        retention_pct=retention_pct,
    )


# ── Job principal ─────────────────────────────────────────────────────────────

def collect_performance() -> tuple[int, int, int]:
    """Renvoie (updated, pending, errors)."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"── collect {stamp} ──")

    videos = _videos_to_collect()
    if not videos:
        print("Aucune vidéo éligible (publiées depuis >24h).")
        print(f"── fin: 0 updated | 0 pending | 0 errors | 0 gaps ──")
        return (0, 0, 0)

    yta_by_channel: dict[int, object] = {}
    updated = pending = errors = 0
    permanent_skips: list[str] = []

    for v in videos:
        cid = v["channel_id"]
        label = f"video {v['video_id']} ({v['yt_video_id']})"
        try:
            if cid not in yta_by_channel:
                creds = _get_credentials(cid)
                yta_by_channel[cid] = build(
                    "youtubeAnalytics", "v2",
                    credentials=creds, cache_discovery=False,
                )
            m = _fetch_metrics(yta_by_channel[cid], v["yt_video_id"],
                               v["published_date"])
            if m is None:
                pending += 1
                print(f"  ⏳ {label}: analytics pas encore prêtes")
                continue
            retention = _compute_retention(m["avg_view_sec"], v["duration_sec"])
            _replace_performance(v["video_id"], m, retention)
            updated += 1
            ret_str = f"{retention}%" if retention is not None else "NULL"
            print(f"  ✅ {label}: {m['views']} vues, rétention {ret_str}")
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            errors += 1
            if status == 404:
                permanent_skips.append(f"{label}: vidéo supprimée/introuvable (404)")
                print(f"  🚫 {label}: 404 — vidéo supprimée ou privée")
            elif status == 403:
                permanent_skips.append(f"{label}: accès refusé (403) — "
                                       f"token/chaîne à vérifier")
                print(f"  🚫 {label}: 403 — token ou chaîne incorrecte")
            else:
                print(f"  ❌ {label}: HTTP {status} — {e}")
        except Exception as e:
            errors += 1
            print(f"  ❌ {label}: {type(e).__name__}: {e}")

    gaps = _detect_gaps()
    for gid, gyt, gdate in gaps:
        print(f"  🕳️  TROU: video {gid} ({gyt}) publiée le {gdate}, "
              f"toujours aucune donnée après {GAP_ALERT_DAYS}j — investiguer")

    print(f"── fin: {updated} updated | {pending} pending | "
          f"{errors} errors | {len(gaps)} gaps ──")
    if permanent_skips:
        print("Erreurs permanentes (action requise):")
        for s in permanent_skips:
            print(f"  • {s}")
    return (updated, pending, errors)


if __name__ == "__main__":
    _, _, errs = collect_performance()
    sys.exit(1 if errs else 0)