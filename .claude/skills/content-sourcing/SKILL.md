---
name: content-sourcing
description: >
  Use when integrating an external data source/API into ChannelOS or generating dated
  content with an LLM (trend pickers, pick_trending_topic.py, topic/title synthesis,
  adding or fixing a YouTube/HN/Trends/Reddit source). Enforces the compliance-before-access
  rule (ToS first), external-API pitfalls (User-Agent, client-side filtering, None-safety,
  active-source counting), and dated-content safety (dynamic year, inject today's date into
  the prompt). Trigger on: new API integration, 403/400 from an external source, "ajouter
  une source de trends", LLM output with a year/date, stale year in a title, ToS/policy doubt.
---

# Sourcing externe & fraîcheur — ChannelOS

## 0. La question qui passe EN PREMIER : ai-je le DROIT ?
Avant *« est-ce que ça marche ? »*, demande *« ai-je le droit d'accéder à ça pour CET usage ? »*.
Lis les ToS/policies d'abord. Inverser l'ordre = perdre du temps à percer un mur qu'on n'a pas
le droit de franchir.

Un **blocage répété et propre** (403 systématique malgré un accès correct) est souvent une
**frontière de politique**, pas un défi technique. Ne t'acharne pas à le contourner.

## 1. Conformité — le cas Reddit (jurisprudence du repo)
La *Responsible Builder Policy* de Reddit interdit :
- l'usage **commercial** des données sans accord écrit ;
- leur passage dans un **modèle IA** (« using data to train machine learning or AI models »).

Pipeline ChannelOS = données externes → Claude → Shorts **monétisés** = usage commercial + IA.
→ Reddit **retiré** (2026-06-21). Sanctions prévues : révocation tokens, suspension app **et
comptes liés** — inacceptable avec channelosia déjà sous surveillance.
**Règle : ne jamais aider à contourner une approbation requise.** Vérifier la même clause
(commercial + IA) avant d'ajouter toute nouvelle source.

## 2. Pièges d'API externes
- **User-Agent** : un UA contenant « bot » ou générique = bannissement instantané (Reddit,
  Cloudflare). Si un UA est requis, utiliser un UA navigateur réaliste. Mais un UA ne bat PAS
  un blocage IP/endpoint — si 403 persiste, c'est structurel (voir §0/§1), pas cosmétique.
- **Filtrage côté client > paramètre d'API fragile.** Ex. HN Algolia : `numericFilters`
  comma-séparé → `400 Bad Request`. Solution robuste : `search_by_date` (tri récent→ancien)
  puis filtrer score/récence en Python. Moins de surface = moins de bugs.
  ```python
  # fragile :   params={"numericFilters": f"created_at_i>{since},points>50"}  -> 400
  # robuste :   récupère 20 hits via search_by_date, puis :
  if title and (hit.get("points") or 0) > 50 and (hit.get("created_at_i") or 0) > since: ...
  ```
- **None-safety** : toujours `hit.get(k) or 0` sur les champs numériques. `None > int` plante.
- **Compter les sources actives à chaque run.** L'archi tolérante aux pannes
  (`ThreadPoolExecutor` + timeout) masque les pannes : 1 source sur 4 « marche » sans crier.
  Logguer `N sources actives` et alerter si une tombe à 0.

## 3. Contenu daté généré par un LLM
Bug vécu : en juin **2026**, le pipeline a sorti « Free AI Tools That Save Money **2025** ».
Deux causes qui se cumulent — corriger les DEUX :

1. **Date codée en dur = bombe à retardement.** Une requête `"AI tools entrepreneurs 2025"`
   écrite en 2025 devient fausse en silence le 1er janvier. → année dynamique :
   ```python
   year = datetime.now(timezone.utc).year
   queries = [f"AI tools entrepreneurs {year}", ...]
   ```
2. **Un LLM n'a pas de présent.** Il ne connaît que le prompt + son entraînement (figé) ; sans
   date il recopie l'année qu'il voit dans les signaux. → injecter la date ET une règle :
   ```python
   now = datetime.now(timezone.utc)
   prompt = f"""Today's date: {now:%B %d, %Y}. The current year is {now.year}.
   ...
   5. If the phrase needs a year, use {now.year} — NEVER an older year, even if the signals mention one"""
   ```

**Règle générale** : tout nombre/mot temporel non issu d'une horloge périme. Dès qu'un LLM
génère du contenu daté, l'ancrage temporel dans le prompt est obligatoire, jamais optionnel.

## 4. Réflexe maître (commun à tout le repo)
Un script qui **réussit** n'est pas un script qui **marche**. Regarde l'output RÉEL, pas juste
le code de sortie 0 — les bugs qui ne plantent pas (année fausse, source muette) sont les pires.

## 5. Discipline d'expérience (pendant le run 90 j)
Ajouter/modifier une source de trends ou l'idéation **pollue** le signal bandit-vs-baseline →
**post-verdict (P2)**. Un *bug de correction* (année fausse, source cassée) ≠ un *changement de
scope*. Distingue les deux avant d'éditer ; en cas de doute, ne touche pas aux variables d'entrée.
