-- ChannelOS — Schéma PostgreSQL
-- =============================
-- Fondation pour : tracking des coûts + boucle d'apprentissage + multi-users
-- Conçu pour évoluer : single-user aujourd'hui, multi-user demain (sans refonte).

-- ─────────────────────────────────────────────────────────
-- USERS — prêt pour le multi-user, mais un seul user au début
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id           SERIAL PRIMARY KEY,
    email        TEXT UNIQUE NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- User par défaut (toi) pour le mode solo actuel
INSERT INTO users (id, email)
VALUES (1, 'owner@channelos.local')
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────────────────
-- CHANNELS — une niche + langue + plateforme
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS channels (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    name         TEXT NOT NULL,
    niche        TEXT NOT NULL,
    language     TEXT NOT NULL DEFAULT 'EN',
    platform     TEXT,                       -- tiktok / youtube / instagram
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────
-- IDEAS — chaque idée générée, avec sa source de tendance et son score
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ideas (
    id              SERIAL PRIMARY KEY,
    channel_id      INTEGER REFERENCES channels(id),
    title           TEXT NOT NULL,
    hook            TEXT,
    angle           TEXT,
    structure       JSONB,                   -- les beats
    broll_query     TEXT,
    affiliate_angle TEXT,
    viral_score     INTEGER,
    score_reason    TEXT,
    based_on_trend  TEXT,                     -- traçabilité : quelle news
    brand_safe      BOOLEAN DEFAULT true,
    status          TEXT NOT NULL DEFAULT 'generated',
                    -- generated / selected / scripted / produced / posted / rejected
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────
-- VIDEOS — chaque vidéo produite, liée à son idée
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS videos (
    id            SERIAL PRIMARY KEY,
    idea_id       INTEGER REFERENCES ideas(id),
    spoken_text   TEXT,
    caption       TEXT,
    hashtags      JSONB,
    broll_url     TEXT,
    video_url     TEXT,                       -- URL cloud JSON2Video
    local_path    TEXT,
    duration_sec  NUMERIC,
    status        TEXT NOT NULL DEFAULT 'rendered',
                  -- rendered / downloaded / posted / failed
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────
-- COST_LOG — LE tracking des coûts : une ligne par appel API
-- Permet de calculer le coût réel par vidéo, par jour, par user
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cost_log (
    id            SERIAL PRIMARY KEY,
    video_id      INTEGER REFERENCES videos(id),
    idea_id       INTEGER REFERENCES ideas(id),
    provider      TEXT NOT NULL,              -- anthropic / tavily / json2video / pexels
    operation     TEXT,                       -- script / trends / render / broll
    units         NUMERIC,                    -- tokens, crédits, secondes...
    unit_type     TEXT,                       -- 'tokens' / 'credits' / 'seconds'
    cost_usd      NUMERIC(10, 5),             -- coût estimé en USD
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────
-- PERFORMANCE — métriques réelles (pour la boucle d'apprentissage future)
-- Vide pour l'instant : se remplira quand tu posteras et collecteras les vues
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS performance (
    id            SERIAL PRIMARY KEY,
    video_id      INTEGER REFERENCES videos(id),
    platform      TEXT,
    views         INTEGER DEFAULT 0,
    likes         INTEGER DEFAULT 0,
    shares        INTEGER DEFAULT 0,
    comments      INTEGER DEFAULT 0,
    retention_pct NUMERIC,                    -- % moyen regardé
    clicks        INTEGER DEFAULT 0,          -- clics lien bio (affiliation)
    measured_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────
-- INDEX — pour les requêtes fréquentes
-- ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ideas_channel   ON ideas(channel_id);
CREATE INDEX IF NOT EXISTS idx_ideas_status     ON ideas(status);
CREATE INDEX IF NOT EXISTS idx_videos_idea      ON videos(idea_id);
CREATE INDEX IF NOT EXISTS idx_cost_video       ON cost_log(video_id);
CREATE INDEX IF NOT EXISTS idx_perf_video       ON performance(video_id);


-- ─────────────────────────────────────────────────────────
-- VUE — coût réel par vidéo (le chiffre que tu veux voir)
-- ─────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW video_costs AS
SELECT
    v.id              AS video_id,
    i.title           AS idea_title,
    v.duration_sec,
    COALESCE(SUM(c.cost_usd), 0) AS total_cost_usd,
    json_object_agg(c.provider, c.cost_usd) FILTER (WHERE c.provider IS NOT NULL)
                      AS cost_breakdown,
    v.created_at
FROM videos v
LEFT JOIN ideas i    ON v.idea_id = i.id
LEFT JOIN cost_log c ON c.video_id = v.id
GROUP BY v.id, i.title, v.duration_sec, v.created_at;