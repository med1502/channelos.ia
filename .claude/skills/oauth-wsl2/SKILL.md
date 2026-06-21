---
name: oauth-wsl2
description: >
  Use when generating or refreshing a Google/YouTube OAuth token inside WSL2 for
  ChannelOS (publisher.py auth, expired token, invalid_grant error, "Pas de token
  valide pour channel_id"). Covers the reliable manual-code-exchange method that
  works under WSL2 NAT networking, where run_local_server / localhost redirect fails.
  Trigger on: token regeneration, channel re-auth, OAuth errors (redirect_uri,
  InsecureTransport, MismatchingState, invalid code verifier, connection refused on localhost).
---

# OAuth sous WSL2 — méthode fiable

## Pourquoi le flux standard échoue
Le réseau WSL2 est en NAT isolé (IP `172.x`). Quand `flow.run_local_server()` ouvre un
serveur local, le navigateur **Windows** ne peut pas joindre le port WSL → `ERR_CONNECTION_REFUSED`.
Inutile d'itérer sur cette approche : passer directement à l'échange manuel.

## Méthode : échange manuel du code (sans PKCE, sans state)
Les variables d'env neutralisent les deux gardes qui posent problème en local :
- `OAUTHLIB_INSECURE_TRANSPORT=1` — autorise le redirect `http://localhost` (sinon `InsecureTransportError`)
- `OAUTHLIB_RELAX_TOKEN_SCOPE=1` — tolère le réordonnancement des scopes

Et on échange le code à la main pour éviter `MismatchingStateError` (state) et
`Invalid code verifier` (PKCE).

```python
import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
import json, requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

CHANNEL_ID = 1   # adapter
cfg = json.load(open("secrets/client_secret.json"))["installed"]
CID, CSECRET = cfg["client_id"], cfg["client_secret"]
REDIRECT = "http://localhost:8765/"
SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
         "https://www.googleapis.com/auth/youtube.readonly "
         "https://www.googleapis.com/auth/yt-analytics.readonly")

auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode({
    "response_type": "code", "client_id": CID, "redirect_uri": REDIRECT,
    "scope": SCOPE, "access_type": "offline", "prompt": "consent",
})
print("\n1. Ouvre CETTE URL (le BON compte), autorise:\n")
print(auth_url)
print("\n2. Page 'localhost inaccessible' = NORMAL. Copie l'URL COMPLETE de la barre.\n")

pasted = input("> ").strip()
code = parse_qs(urlparse(pasted).query).get("code", [None])[0]
if not code:
    raise SystemExit("Aucun code dans l'URL")

r = requests.post("https://oauth2.googleapis.com/token", data={
    "code": code, "client_id": CID, "client_secret": CSECRET,
    "redirect_uri": REDIRECT, "grant_type": "authorization_code",
})
r.raise_for_status()
tok = r.json()
creds = {"token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
         "token_uri": "https://oauth2.googleapis.com/token",
         "client_id": CID, "client_secret": CSECRET, "scopes": SCOPE.split()}
Path(f"secrets/yt_token_channel_{CHANNEL_ID}.json").write_text(json.dumps(creds))
print("\nOK token écrit. refresh_token:", bool(tok.get("refresh_token")))
```

## Discipline (les 3 échecs classiques)
1. **Vieille URL** : toujours copier la NOUVELLE url affichée, jamais une d'un message précédent.
2. **Code expiré** : usage unique, ~secondes de validité → coller dans la minute.
3. **Mauvais compte** : channelosia porte FounderAIHub (ch1) ; mohamed porte Daily (ch2).
   Choisir le bon compte sur l'écran Google.

## Vérification obligatoire après
```python
from googleapiclient.discovery import build
from channelos.pipeline.publisher import _get_credentials
yt = build("youtube","v3",credentials=_get_credentials(1),cache_discovery=False)
print(yt.channels().list(part="snippet", mine=True).execute()["items"][0]["snippet"]["title"])
# DOIT afficher le titre de chaîne attendu (FounderAIHub), pas le nom du compte perso
```
Si le titre ne correspond pas à la chaîne voulue → le token pointe vers le mauvais compte, recommencer.