"""
ChannelOS — pipeline/publisher.py  (TCK-06)
============================================
Publie un Short sur la bonne chaîne YouTube (round-robin géré en amont
par _resolve_channel_id) et marque la vidéo 'published' en DB.

Architecture OAuth (brand accounts, 1 compte Google, 2-3 chaînes):
  - 1 fichier client_secret.json (projet GCP, OAuth Desktop app)
  - 1 token par chaîne: secrets/yt_token_channel_<db_channel_id>.json
    (au moment d'autoriser, Google demande QUELLE chaîne — choisir la bonne)

Quota (décision TCK-05, option A):
  - videos.insert ≈ 1600 unités, quota défaut 10 000/jour → plafond 6 uploads/jour
  - garde-fou local: compteur quotidien en DB (table publish_quota)

Bootstrap (une fois par chaîne):
  python3 -m channelos.pipeline.publisher auth --channel-id 1
  python3 -m channelos.pipeline.publisher auth --channel-id 2
  ...

Publier:
  from channelos.pipeline.publisher import publish
  yt_id = publish(video_id, video_path, meta, channel_id)

Dépendances:
  pip install google-auth google-auth-oauthlib google-api-python-client
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError, ResumableUploadError
from googleapiclient.http import MediaFileUpload

from datetime import datetime, timedelta, timezone

import channelos.db as db

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
SECRETS_DIR = Path("secrets")
CLIENT_SECRET = SECRETS_DIR / "client_secret.json"

MAX_UPLOADS_PER_DAY = 6          # TCK-05 option A — quota défaut 10 000 u/j
UPLOAD_COST_UNITS = 1600

CATEGORY_SCIENCE_TECH = "28"     # catégorie YouTube par défaut pour le niche

PUBLISH_SLOTS_UTC = [13, 17, 21]   # heures UTC cibles (audience EN/US)
MIN_GAP_HOURS = 4                  # espacement minimal entre publications


# ── Quota guard (local, en DB) ────────────────────────────────────────────────

def _ensure_quota_table() -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS publish_quota (
                day    DATE PRIMARY KEY,
                count  INT NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def _quota_remaining() -> int:
    _ensure_quota_table()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count FROM publish_quota WHERE day=%s", (date.today(),))
        row = cur.fetchone()
    used = row[0] if row else 0
    return MAX_UPLOADS_PER_DAY - used


def _quota_consume() -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO publish_quota (day, count) VALUES (%s, 1)
            ON CONFLICT (day) DO UPDATE SET count = publish_quota.count + 1
            """,
            (date.today(),),
        )
        conn.commit()


# ── OAuth par chaîne ──────────────────────────────────────────────────────────

def _token_path(channel_id: int) -> Path:
    return SECRETS_DIR / f"yt_token_channel_{channel_id}.json"


def _get_credentials(channel_id: int, interactive: bool = False) -> Credentials:
    """Charge (ou crée si interactive=True) le token OAuth de la chaîne."""
    token_file = _token_path(channel_id)
    creds: Credentials | None = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())

    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError(
                f"Pas de token valide pour channel_id={channel_id}. "
                f"Lancer: python3 -m channelos.pipeline.publisher auth "
                f"--channel-id {channel_id}"
            )
        if not CLIENT_SECRET.exists():
            raise FileNotFoundError(
                f"{CLIENT_SECRET} manquant — créer un OAuth client "
                f"(Desktop app) dans le projet GCP et le placer là."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        # run_local_server ouvre le navigateur; CHOISIR LA BONNE CHAÎNE
        # (brand account) sur l'écran de sélection Google.
        creds = flow.run_local_server(port=0)
        SECRETS_DIR.mkdir(exist_ok=True)
        token_file.write_text(creds.to_json())
        print(f"✅ Token enregistré: {token_file}")

    return creds


def _youtube_client(channel_id: int):
    creds = _get_credentials(channel_id)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ── Publication ───────────────────────────────────────────────────────────────

def _build_metadata(meta: dict) -> dict:
    """Construit snippet/status pour videos.insert à partir du post_package.

    Shorts: vidéo verticale <60s + '#Shorts' dans le titre ou la description.
    """
    title = meta.get("title", "").strip()
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    title = title[:100]  # limite YouTube

    hashtags = meta.get("hashtags", [])
    description_parts = [meta.get("caption", "").strip()]
    if hashtags:
        description_parts.append(" ".join(hashtags))
    description = "\n\n".join(p for p in description_parts if p)[:5000]

    # tags YouTube = hashtags sans '#'
    tags = [h.lstrip("#") for h in hashtags][:15]

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": CATEGORY_SCIENCE_TECH,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

def _next_publish_slot(now: datetime, last_published_at: datetime | None) -> datetime:
    """Prochain créneau optimal: >= now+15min, >= last+MIN_GAP_HOURS,
    sur une heure de PUBLISH_SLOTS_UTC. Cherche jour par jour."""
    floor = now + timedelta(minutes=15)            # marge de traitement YouTube
    if last_published_at is not None:
        gap = last_published_at + timedelta(hours=MIN_GAP_HOURS)
        floor = max(floor, gap)
    day = floor.date()
    for d in range(0, 8):                          # jusqu'à 7 jours devant
        for h in PUBLISH_SLOTS_UTC:
            slot = datetime(day.year, day.month, day.day, h,
                            tzinfo=timezone.utc) + timedelta(days=d)
            if slot >= floor:
                return slot
    raise RuntimeError("Aucun créneau trouvé sous 7 jours")

def publish(
    video_id: int,
    video_path: str,
    meta: dict,
    channel_id: int,
    publish_at=None,
) -> str:
    """Upload le MP4 sur la chaîne, marque published en DB, renvoie yt_video_id.

    Lève RuntimeError si le quota local du jour est épuisé — échec bruyant,
    jamais d'upload silencieusement sauté.
    """
    remaining = _quota_remaining()
    if remaining <= 0:
        raise RuntimeError(
            f"Quota local épuisé ({MAX_UPLOADS_PER_DAY}/jour, TCK-05 option A). "
            f"Réessayer demain ou revoir la décision quota."
        )

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Vidéo introuvable: {video_path}")

    yt = _youtube_client(channel_id)
    body = _build_metadata(meta)
    if publish_at is not None:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at.isoformat().replace("+00:00", "Z")
    media = MediaFileUpload(
        str(path), mimetype="video/mp4", resumable=True, chunksize=4 * 1024 * 1024
    )

    request = yt.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    print(f"⏫ Upload → channel {channel_id} ({remaining} restants aujourd'hui)…")
    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"   {int(status.progress() * 100)}%")
    except ResumableUploadError as e:
        raise RuntimeError(f"Upload échoué (resumable): {e}") from e
    except HttpError as e:
        if e.resp.status == 403 and b"quotaExceeded" in e.content:
            raise RuntimeError(
                "Quota YouTube RÉEL épuisé (403 quotaExceeded) — le compteur "
                "local et le quota Google ont divergé. Vérifier la console GCP."
            ) from e
        raise

    yt_video_id = response["id"]
    _quota_consume()
    db.mark_published(video_id, yt_video_id)

    url = f"https://youtube.com/shorts/{yt_video_id}"
    print(f"✅ Published: {url} (channel {channel_id})")
    return yt_video_id


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli() -> None:
    parser = argparse.ArgumentParser(prog="channelos.pipeline.publisher")
    sub = parser.add_subparsers(dest="cmd")

    p_auth = sub.add_parser("auth", help="bootstrap OAuth pour une chaîne")
    p_auth.add_argument("--channel-id", type=int, required=True,
                        help="id de la chaîne dans la table channels")

    sub.add_parser("quota", help="quota local restant aujourd'hui")

    args = parser.parse_args()

    if args.cmd == "auth":
        _get_credentials(args.channel_id, interactive=True)
        print(
            "\n⚠️  Vérifier que la chaîne autorisée correspond bien à "
            f"channel_id={args.channel_id} en DB (brand account choisi à l'écran)."
        )
    elif args.cmd == "quota":
        print(f"Uploads restants aujourd'hui: {_quota_remaining()}/{MAX_UPLOADS_PER_DAY}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()