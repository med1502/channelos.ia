"""
ChannelOS — pipeline/collect.py  (TCK-08 v2)
=============================================
Ingestion quotidienne YouTube Analytics → table `performance`.

v2 — métrique de rétention corrigée pour les Shorts:
  `averageViewPercentage` est gonflé par les boucles de lecture (>2500% observé).
  On calcule désormais: retention_pct = averageViewDuration / duration_sec * 100,
  plafonné à 300% (tolère les re-watches, coupe l'aberrant).
  Vidéo sans duration_sec connue (ex: publiée manuellement) → retention NULL,
  jamais un chiffre inventé.

États — zéro trou silencieux:
  updated : données fraîches écrites
  pending : analytics pas encore disponibles (J+1 à J+3, normal)
  error   : échec API (compté et affiché)

Usage:
  python3 -m channelos.pipeline.collect      ou: make collect
"""

from __future__ import annotations

import sys
from datetime import date

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import channelos.db as db
from channelos.pipeline.publisher import _get_credentials

MIN_AGE_HOURS = 24      # analytics YouTube dispo J+1 à J+3
RETENTION_CAP = 300.0   # % max plausible (boucles Shorts tolérées, aberrant coupé)


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


# ── Requête Analytics pour une vidéo ─────────────────────────────────────────

def _fetch_metrics(yta, yt_video_id: str, start_date) -> dict | None:
    """Renvoie {views, likes, comments, avg_view_sec} ou None si pas de données."""
    common = dict(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=date.today().isoformat(),
        filters=f"video=={yt_video_id}",
    )
    resp = yta.reports().query(metrics="views,likes,comments", **common).execute()
    rows = resp.get("rows") or []
    if not rows:
        return None
    views, likes, comments = rows[0]

    resp2 = yta.reports().query(metrics="averageViewDuration", **common).execute()
    rows2 = resp2.get("rows") or []
    avg_view_sec = float(rows2[0][0]) if rows2 else None

    return {
        "views": int(views),
        "likes": int(likes),
        "comments": int(comments),
        "avg_view_sec": avg_view_sec,
    }


def _compute_retention(avg_view_sec: float | None,
                       duration_sec: float | None) -> float | None:
    """retention_pct normalisée par la durée réelle. NULL si durée inconnue
    ou résultat invraisemblable — jamais un chiffre inventé."""
    if avg_view_sec is None or not duration_sec:
        return None
    pct = avg_view_sec / duration_sec * 100.0
    if pct < 0:
        return None
    return round(min(pct, RETENTION_CAP), 2)


# ── Écriture: remplace l'instantané précédent ─────────────────────────────────

def _replace_performance(video_id: int, m: dict, retention_pct: float | None) -> None:
    """1 ligne par vidéo = dernier instantané (évite le biais de moyenne
    sur snapshots multiples dans la requête du verdict)."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM performance WHERE video_id = %s", (video_id,))
        conn.commit()
    db.save_performance(
        video_id,
        platform="youtube",
        views=m["views"],
        likes=m["likes"],
        comments=m["comments"],
        retention_pct=retention_pct,
    )


# ── Job principal ─────────────────────────────────────────────────────────────

def collect_performance() -> tuple[int, int, int]:
    """Renvoie (updated, pending, errors)."""
    videos = _videos_to_collect()
    if not videos:
        print("Aucune vidéo éligible (publiées depuis >24h). "
              "Normal si tout est récent.")
        return (0, 0, 0)

    yta_by_channel: dict[int, object] = {}
    updated = pending = errors = 0

    for v in videos:
        cid = v["channel_id"]
        try:
            if cid not in yta_by_channel:
                creds = _get_credentials(cid)
                yta_by_channel[cid] = build(
                    "youtubeAnalytics", "v2",
                    credentials=creds, cache_discovery=False,
                )
            m = _fetch_metrics(
                yta_by_channel[cid], v["yt_video_id"], v["published_date"]
            )
            if m is None:
                pending += 1
                print(f"  ⏳ video {v['video_id']} ({v['yt_video_id']}): "
                      f"analytics pas encore prêtes")
                continue

            retention = _compute_retention(m["avg_view_sec"], v["duration_sec"])
            if retention is None and m["avg_view_sec"] is not None:
                print(f"  ⚠️  video {v['video_id']}: durée inconnue ou ratio "
                      f"invraisemblable — rétention NULL "
                      f"(avg_view={m['avg_view_sec']}s, dur={v['duration_sec']})")

            _replace_performance(v["video_id"], m, retention)
            updated += 1
            ret_str = f"{retention}%" if retention is not None else "NULL"
            print(f"  ✅ video {v['video_id']} ({v['yt_video_id']}): "
                  f"{m['views']} vues, rétention {ret_str}")
        except HttpError as e:
            errors += 1
            code = getattr(e.resp, "status", "?")
            print(f"  ❌ video {v['video_id']} ({v['yt_video_id']}): "
                  f"HTTP {code} — {e}")
        except Exception as e:
            errors += 1
            print(f"  ❌ video {v['video_id']} ({v['yt_video_id']}): "
                  f"{type(e).__name__}: {e}")

    print(f"\n{updated} updated | {pending} pending | {errors} errors")
    return (updated, pending, errors)


if __name__ == "__main__":
    _, _, errs = collect_performance()
    sys.exit(1 if errs else 0)