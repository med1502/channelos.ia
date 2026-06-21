-- ChannelOS IA — Migration 002: schema drift repair
-- La base réelle a divergé de schema.sql (CREATE TABLE IF NOT EXISTS ne met
-- pas à jour les tables existantes). Cette migration aligne la réalité sur
-- le schéma attendu par le code. Idempotente.
--
-- Run: psql "$DATABASE_URL" -f channelos/db/migration_002_drift_repair.sql

BEGIN;

-- ── videos: published_at manquant (utilisé par mark_published) ──────────────
ALTER TABLE videos ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- ── channels: niche_key manquant (utilisé par _resolve_channel_id) ──────────
ALTER TABLE channels ADD COLUMN IF NOT EXISTS niche_key  TEXT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS platform   TEXT DEFAULT 'youtube';
ALTER TABLE channels ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- ── ideas: colonnes utilisées par save_idea (au cas où la table est ancienne)
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS structure       JSONB DEFAULT '[]';
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS broll_query     TEXT;
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS affiliate_angle TEXT;
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS viral_score     INT;
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS score_reason    TEXT;
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS based_on_trend  TEXT;
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS brand_safe      BOOLEAN DEFAULT TRUE;
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS format          TEXT DEFAULT 'single';
ALTER TABLE ideas ADD COLUMN IF NOT EXISTS status          TEXT DEFAULT 'generated';

-- ── cost_log: colonnes utilisées par log_cost ───────────────────────────────
ALTER TABLE cost_log ADD COLUMN IF NOT EXISTS unit_type TEXT;
ALTER TABLE cost_log ADD COLUMN IF NOT EXISTS units     FLOAT;

COMMIT;

-- Vérification post-migration (à lancer à la main):
--   \d videos      → published_at présent
--   \d channels    → niche_key présent
--   \d performance → hook_pattern, arm, format, niche, lang présents