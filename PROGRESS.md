# ChannelOS IA — Progression 90 jours

> **J1 atteint le 10 juin 2026** · Verdict moat: J86–90 (~3–7 sept 2026)
> Question unique: les hooks choisis par le bandit battent-ils la baseline en rétention ?
> Périmètre gelé (ADR-009): `ai_entrepreneurs` · EN · `ranking` · 7 hooks · 2 chaînes

**Progression: 8 ✅ · 2 🔧 · 10 ⬜ — ~48%**

`█████████████████░░░░░░░░░░░░░░░░░░`

| Indicateur | Valeur |
|---|---|
| Vidéos publiées | 4 (3 pipeline + 1 manuelle) |
| Lignes `performance` | 1 (vidéos 5/6/7 attendues au cron du 12 juin) |
| Chaînes actives | 2 — équilibrage validé en prod |
| Patterns observés | list_tease, secret |
| Coût/vidéo | ~$0.18 |
| Échéance proche | **TCK-18 — 17 juin** |

---

## Sprint 1 — Terrain (J1–J7) — 90%

- [x] **TCK-01** [OWNER] Geler le périmètre — ADR-009, format ranking
- [ ] **TCK-02** [PLATFORM] Hygiène repo — `.gitignore` ✅, **reste: archiver le repo jumeau `channelos-ia`**
- [x] **TCK-03** [DATA] Tagging décisionnel — migrations 001+002, `save_video` v2, validé en prod
- [x] **TCK-04** [OWNER] Chaînes YouTube — FounderAIHub + Daily, tokens OAuth vérifiés
- [x] **TCK-05** [PLATFORM] Quota tranché — option A, 6 uploads/jour

## Sprint 2 — Colonne vertébrale données (J8–J30) — 70%

- [x] **TCK-06** [PIPELINE] Publisher YouTube — publish réel validé, chaîne ①→⑥ propre
- [x] **TCK-07** [PIPELINE] Production quotidienne — cron 9h actif, équilibrage chaînes persistant (DB) validé
- [x] **TCK-08** [DATA] Ingestion Analytics — **validé sur données réelles le 11 juin**
  - métrique: `averageViewDuration / duration_sec` (averageViewPercentage gonflé ×26 par les boucles Shorts — écarté)
  - garde-fous: plafond 300%, NULL honnête si durée inconnue, zéro chiffre inventé
- [ ] **TCK-09** [DATA] Fiabilisation ingestion — retries, détection de trous (>3j sans perf = alerte), résumé log
- [ ] **TCK-10** [DATA] Revue volume/cellule (cible: 20–40 échantillons/cellule/mois)
- [ ] **TCK-18** [OWNER] ⚠️ Affiliation vague 1: Make.com, Buffer, Notion — **échéance J7 (17 juin)**

## Sprint 3 — Fermer la boucle (J31–J60) — 10%

- [ ] **TCK-11** [ML] Bandit v1 — poids à seuil sur 7 hooks · *prérequis: ~2 semaines de lignes `performance`*
- [ ] **TCK-12** [ML] Bandit → idéation — tagging `hook_pattern` déjà ✅ (list_tease, secret observés)
- [ ] **TCK-13** [ML] Split A/B 50/50, tag `arm`
- [ ] **TCK-14** [ML] Surveillance dérive poids / famine de cellule

## Sprint 4 — Prouver le lift (J61–J90) — 0%

- [ ] **TCK-15** [PIPELINE] Run du test — gel total, 20–40 éch./bras
- [ ] **TCK-16** [ML] Analyse de significativité → OUI/NON chiffré
- [ ] **TCK-17** [OWNER] Verdict + narratif de levée

## Monétisation — Affiliation (parallèle, P1)

- [ ] **TCK-19** [OWNER] Affiliation vague 2: Mailchimp, HubSpot — échéance J30 (10 juillet)
- [ ] **TCK-20** [PIPELINE] Substitution auto des liens affiliés — déclencheur: 1re approbation

---

## Chemin critique

```
TCK-03 ✅ → TCK-06 ✅ → TCK-07 ✅ → TCK-08 ✅ → [accumulation de données ~2 sem] → TCK-11 → TCK-12 → TCK-13 → TCK-15 → TCK-16 → TCK-17
```

**Le chemin critique est en attente de DONNÉES, pas de code.** Le système accumule
tout seul (cron collect 9h + publications quotidiennes). TCK-11 démarre quand
`performance` a ~2 semaines de lignes. Tickets affiliation = P1, glissent en
priorité si une semaine est serrée.

## Rituel quotidien

1. Matin: `make collect` (ou vérifier `logs/collect.log` si cron passé) — guetter les rétentions
2. Journée: 2–3 × `RENDER_BUDGET_SECONDS=200 python3 -m channelos "AI tools" --publish`, espacés
3. Coup d'œil: `psql $DATABASE_URL -c "SELECT hook_pattern, ROUND(AVG(retention_pct)::numeric,1) AS ret, COUNT(*) FROM performance GROUP BY 1 ORDER BY 2 DESC;"`

## Journal des jalons

| Date | Jalon |
|---|---|
| 10 juin 2026 | **J1** — premier Short publié de bout en bout (novyQkhjhOg) |
| 11 juin 2026 | Première chaîne ①→⑥ sans erreur (iMeLa0Yqg-8) · 2e pattern observé |
| 11 juin 2026 | Équilibrage chaînes validé (oZo-FqFRFOc → channel 2) |
| 11 juin 2026 | **TCK-08 validé sur API réelle** — 1re ligne `performance` (105 vues) · métrique Shorts corrigée |
| 12 juin 2026 | *(attendu)* Premières rétentions comparables — vidéos 5, 6, 7 via cron |

> Mise à jour: cocher les cases au fil de l'eau, ajouter les jalons en bas.
> Régénération complète: demander à Claude "mets à jour PROGRESS.md".