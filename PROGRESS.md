# ChannelOS IA — Progression 90 jours

> **J1 atteint le 10 juin 2026** · Verdict moat: J86–90 (~3–7 sept 2026)
> Question unique: les hooks choisis par le bandit battent-ils la baseline en rétention ?
> Périmètre gelé (ADR-009): `ai_entrepreneurs` · EN · `ranking` · 7 hooks · 2 chaînes

**Progression: 6 ✅ · 3 🔧 · 11 ⬜ — ~40%**

`██████████████░░░░░░░░░░░░░░░░░░░░░` 

| Indicateur | Valeur |
|---|---|
| Vidéos publiées | 2 (novyQkhjhOg, iMeLa0Yqg-8) |
| Patterns observés | list_tease, secret |
| Coût/vidéo | ~$0.18 |
| Prochain ticket | **TCK-08 — Ingestion Analytics** |

---

## Sprint 1 — Terrain (J1–J7) — 90%

- [x] **TCK-01** [OWNER] Geler le périmètre — ADR-009, format ranking
- [ ] **TCK-02** [PLATFORM] Hygiène repo — `.gitignore` ✅, **reste: archiver le repo jumeau `channelos-ia`**
- [x] **TCK-03** [DATA] Tagging décisionnel — migrations 001+002, `save_video` v2, validé en prod
- [x] **TCK-04** [OWNER] Chaînes YouTube — FounderAIHub + Daily, tokens OAuth vérifiés
- [x] **TCK-05** [PLATFORM] Quota tranché — option A, 6 uploads/jour

## Sprint 2 — Colonne vertébrale données (J8–J30) — 40%

- [x] **TCK-06** [PIPELINE] Publisher YouTube — 1er publish réel 10 juin, chaîne ①→⑥ propre 11 juin
- [ ] **TCK-07** [PIPELINE] Production quotidienne — runs manuels ✅, **reste: cron + fix équilibrage chaînes**
- [ ] **TCK-08** [DATA] ⭐ **PROCHAIN** — Ingestion Analytics → table `performance`
- [ ] **TCK-09** [DATA] Fiabilisation ingestion (délais J+1/J+3, retries, zéro trou silencieux)
- [ ] **TCK-10** [DATA] Revue volume/cellule (cible: 20–40 échantillons/cellule/mois)
- [ ] **TCK-18** [OWNER] Affiliation vague 1: Make.com, Buffer, Notion — **échéance J7 (17 juin)**

## Sprint 3 — Fermer la boucle (J31–J60) — 10%

- [ ] **TCK-11** [ML] Bandit v1 — poids à seuil sur 7 hooks
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
TCK-03 ✅ → TCK-06 ✅ → TCK-07 🔧 → TCK-08 ⭐ → TCK-11 → TCK-12 → TCK-13 → TCK-15 → TCK-16 → TCK-17
```

Tout retard sur **TCK-08** décale le verdict d'autant. Les tickets affiliation (18/19/20)
sont P1: ils glissent en priorité si une semaine est serrée — jamais TCK-08.

## Journal des jalons

| Date | Jalon |
|---|---|
| 10 juin 2026 | **J1** — premier Short publié de bout en bout (novyQkhjhOg) |
| 11 juin 2026 | Première chaîne ①→⑥ sans erreur (iMeLa0Yqg-8) · 2e pattern observé |

> Mise à jour: cocher les cases au fil de l'eau, ajouter les jalons en bas.
> Régénération complète: demander à Claude "mets à jour PROGRESS.md".