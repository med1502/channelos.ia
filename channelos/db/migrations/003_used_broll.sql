-- migration_003_used_broll.sql
-- Dédup B-roll: mémorise chaque clip Pexels utilisé pour ne pas le resservir.

CREATE TABLE IF NOT EXISTS used_broll (
    id          SERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    video_id    INTEGER REFERENCES videos(id),
    used_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_used_broll_used_at ON used_broll (used_at);