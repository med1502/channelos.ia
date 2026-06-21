---
name: db-patterns
description: >
  Use when writing SQL or DB-touching Python for ChannelOS (PostgreSQL): inserting
  videos/ideas, updating status, querying the experiment/verdict table, balancing
  channels, dating scheduled publications. Enforces zero-manual-placeholder patterns
  (CTE WITH ... RETURNING), COALESCE for scheduled dates, and the FK-safe deletion rule.
  Trigger on: INSERT/UPDATE/DELETE on videos/ideas/performance/cost_log, channel
  balancing logic, "save_video", mark_published, retention/verdict queries.
---

# Patterns DB — ChannelOS

## Règle d'or : zéro placeholder manuel
L'utilisateur travaille souvent sur mobile. **Jamais** de snippet avec `N` ou `IDEA_ID`
à remplacer à la main, jamais de copier-coller de valeur entre étapes. Utiliser des CTE.

### INSERT lié (idée + vidéo) en une transaction atomique
```sql
WITH new_idea AS (
    INSERT INTO ideas (title, format)
    VALUES ('...', 'ranking')
    RETURNING id
)
INSERT INTO videos (idea_id, ..., status, published_at)
SELECT id, ..., 'published', NOW()
FROM new_idea
RETURNING id;
```

### INSERT idempotent (évite les doublons sans SELECT préalable)
```sql
WITH existing AS (SELECT id FROM videos WHERE yt_video_id = 'XXX'),
new_idea AS (
    INSERT INTO ideas (title, format)
    SELECT '...', 'ranking' WHERE NOT EXISTS (SELECT 1 FROM existing)
    RETURNING id
),
inserted AS (
    INSERT INTO videos (idea_id, ...) SELECT id, ... FROM new_idea RETURNING id
)
SELECT 'insere' a, id FROM inserted UNION ALL SELECT 'deja present', id FROM existing;
```

## Dater au créneau, pas à l'upload
`mark_published` et toute écriture de `published_at` pour une vidéo programmée :
```sql
UPDATE videos SET status='published', published_at=COALESCE(%s, NOW()), yt_video_id=%s WHERE id=%s
```
`%s` = datetime du créneau (publishAt) ; `None` → `NOW()`. Sinon l'équilibreur et le
slot picker se trompent (bug du double créneau 13h).

## Suppression : FK cost_log
**Ne jamais `DELETE`** une vidéo/idée référencée par `cost_log` (viole la FK).
Marquer le statut à la place :
```sql
UPDATE videos SET status='deleted' WHERE yt_video_id='XXX';     -- retirée de YouTube
UPDATE videos SET status='discarded' WHERE status='downloaded'; -- render test orphelin
```
La comptabilité des coûts doit survivre à la vidéo.

## Équilibreur de chaînes (alternance stricte)
- Ne compter que `status IN ('published','scheduled')` (les `downloaded`/`discarded` faussent).
- Trier par **`id DESC`** (ordre de création réel), PAS `published_at` (futur pour les programmées).
- Logique : prendre la chaîne != dernière chaîne utilisée (rotation circulaire), pas la moins chargée
  (sinon rafale sur une chaîne jusqu'à rattrapage — dangereux pour channelosia).

## Requête du verdict (toujours filtrer)
```sql
SELECT v.hook_pattern, ROUND(AVG(p.retention_pct)::numeric,1) ret, COUNT(*) n
FROM performance p JOIN videos v ON v.id=p.video_id
WHERE p.retention_pct IS NOT NULL
  AND v.format='ranking'
  AND v.arm='baseline'
  AND v.hook_pattern <> 'manual'   -- exclut les uploads manuels hors expérience
GROUP BY 1 ORDER BY 2 DESC;
```
Rappel : n<20/cellule = AUCUN signal. Métrique plafonnée à 300%, NULL si durée inconnue.