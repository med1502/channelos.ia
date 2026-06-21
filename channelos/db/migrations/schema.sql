--
-- PostgreSQL database dump
--

\restrict jjaOKcrmXeH1NtzoQ6cvA4LXIADWqMg0vylx0OOlCfSjhT7zpYYwJkaUOlq4GEE

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg13+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: channels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.channels (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name text NOT NULL,
    niche text NOT NULL,
    language text DEFAULT 'EN'::text NOT NULL,
    platform text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    niche_key text
);


--
-- Name: channels_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.channels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: channels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.channels_id_seq OWNED BY public.channels.id;


--
-- Name: cost_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_log (
    id integer NOT NULL,
    video_id integer,
    idea_id integer,
    provider text NOT NULL,
    operation text,
    units numeric,
    unit_type text,
    cost_usd numeric(10,5),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cost_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cost_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cost_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cost_log_id_seq OWNED BY public.cost_log.id;


--
-- Name: ideas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ideas (
    id integer NOT NULL,
    channel_id integer,
    title text NOT NULL,
    hook text,
    angle text,
    structure jsonb,
    broll_query text,
    affiliate_angle text,
    viral_score integer,
    score_reason text,
    based_on_trend text,
    brand_safe boolean DEFAULT true,
    status text DEFAULT 'generated'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    format text DEFAULT 'single'::text
);


--
-- Name: ideas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ideas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ideas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ideas_id_seq OWNED BY public.ideas.id;


--
-- Name: performance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.performance (
    id integer NOT NULL,
    video_id integer,
    platform text,
    views integer DEFAULT 0,
    likes integer DEFAULT 0,
    shares integer DEFAULT 0,
    comments integer DEFAULT 0,
    retention_pct numeric,
    clicks integer DEFAULT 0,
    measured_at timestamp with time zone DEFAULT now() NOT NULL,
    hook_pattern text,
    arm text,
    format text,
    niche text,
    lang text,
    CONSTRAINT performance_arm_check CHECK ((arm = ANY (ARRAY['bandit'::text, 'baseline'::text])))
);


--
-- Name: performance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.performance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: performance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.performance_id_seq OWNED BY public.performance.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: videos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.videos (
    id integer NOT NULL,
    idea_id integer,
    spoken_text text,
    caption text,
    hashtags jsonb,
    broll_url text,
    video_url text,
    local_path text,
    duration_sec numeric,
    status text DEFAULT 'rendered'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    hook_pattern text,
    format text,
    niche text,
    lang text,
    channel_id integer,
    yt_video_id text,
    arm text DEFAULT 'baseline'::text NOT NULL,
    published_at timestamp with time zone,
    CONSTRAINT videos_arm_check CHECK ((arm = ANY (ARRAY['bandit'::text, 'baseline'::text])))
);


--
-- Name: video_costs; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.video_costs AS
 WITH cost_by_provider AS (
         SELECT COALESCE(c.video_id, v2.id) AS video_id,
            c.provider,
            round(sum(c.cost_usd), 5) AS provider_cost
           FROM (public.cost_log c
             LEFT JOIN public.videos v2 ON (((v2.idea_id = c.idea_id) AND (c.video_id IS NULL))))
          GROUP BY COALESCE(c.video_id, v2.id), c.provider
        )
 SELECT v.id AS video_id,
    i.title AS idea_title,
    v.created_at,
    COALESCE(sum(cbp.provider_cost), (0)::numeric) AS total_cost_usd,
    jsonb_object_agg(cbp.provider, cbp.provider_cost) FILTER (WHERE (cbp.provider IS NOT NULL)) AS cost_breakdown
   FROM ((public.videos v
     JOIN public.ideas i ON ((i.id = v.idea_id)))
     LEFT JOIN cost_by_provider cbp ON ((cbp.video_id = v.id)))
  GROUP BY v.id, i.title, v.created_at;


--
-- Name: videos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.videos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: videos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.videos_id_seq OWNED BY public.videos.id;


--
-- Name: channels id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channels ALTER COLUMN id SET DEFAULT nextval('public.channels_id_seq'::regclass);


--
-- Name: cost_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_log ALTER COLUMN id SET DEFAULT nextval('public.cost_log_id_seq'::regclass);


--
-- Name: ideas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ideas ALTER COLUMN id SET DEFAULT nextval('public.ideas_id_seq'::regclass);


--
-- Name: performance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.performance ALTER COLUMN id SET DEFAULT nextval('public.performance_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: videos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.videos ALTER COLUMN id SET DEFAULT nextval('public.videos_id_seq'::regclass);


--
-- Name: channels channels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (id);


--
-- Name: cost_log cost_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_log
    ADD CONSTRAINT cost_log_pkey PRIMARY KEY (id);


--
-- Name: ideas ideas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ideas
    ADD CONSTRAINT ideas_pkey PRIMARY KEY (id);


--
-- Name: performance performance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.performance
    ADD CONSTRAINT performance_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: videos videos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_pkey PRIMARY KEY (id);


--
-- Name: idx_cost_video; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_video ON public.cost_log USING btree (video_id);


--
-- Name: idx_ideas_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ideas_channel ON public.ideas USING btree (channel_id);


--
-- Name: idx_ideas_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ideas_status ON public.ideas USING btree (status);


--
-- Name: idx_perf_experiment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_perf_experiment ON public.performance USING btree (arm, hook_pattern);


--
-- Name: idx_perf_video; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_perf_video ON public.performance USING btree (video_id);


--
-- Name: idx_videos_experiment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_videos_experiment ON public.videos USING btree (niche, lang, format, arm, hook_pattern);


--
-- Name: idx_videos_idea; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_videos_idea ON public.videos USING btree (idea_id);


--
-- Name: channels channels_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channels
    ADD CONSTRAINT channels_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: cost_log cost_log_idea_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_log
    ADD CONSTRAINT cost_log_idea_id_fkey FOREIGN KEY (idea_id) REFERENCES public.ideas(id);


--
-- Name: cost_log cost_log_video_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_log
    ADD CONSTRAINT cost_log_video_id_fkey FOREIGN KEY (video_id) REFERENCES public.videos(id);


--
-- Name: ideas ideas_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ideas
    ADD CONSTRAINT ideas_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channels(id);


--
-- Name: performance performance_video_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.performance
    ADD CONSTRAINT performance_video_id_fkey FOREIGN KEY (video_id) REFERENCES public.videos(id);


--
-- Name: videos videos_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE SET NULL;


--
-- Name: videos videos_idea_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_idea_id_fkey FOREIGN KEY (idea_id) REFERENCES public.ideas(id);


--
-- PostgreSQL database dump complete
--

\unrestrict jjaOKcrmXeH1NtzoQ6cvA4LXIADWqMg0vylx0OOlCfSjhT7zpYYwJkaUOlq4GEE

