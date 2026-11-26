-- Schema of a PredomicsApp v2.2.0 database (hand-written migrations v2..v23,
-- before Alembic), without any user data: table definitions plus the rows of
-- schema_versions. Used by the 'upgrade from the previous release' check in
-- .github/workflows/ci.yml and by scripts/check-upgrade.sh. Do not edit.

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

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
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id character varying(12) NOT NULL,
    user_id character varying(12) NOT NULL,
    name character varying(100) NOT NULL,
    key_hash character varying(255) NOT NULL,
    prefix character varying(8) NOT NULL,
    is_active boolean NOT NULL,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    user_id character varying(12),
    action character varying(50) NOT NULL,
    resource_type character varying(30),
    resource_id character varying(12),
    details json,
    ip_address character varying(45),
    created_at timestamp with time zone NOT NULL
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: dataset_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_files (
    id character varying(12) NOT NULL,
    dataset_id character varying(12) NOT NULL,
    filename character varying(255) NOT NULL,
    role character varying(20),
    disk_path text NOT NULL,
    uploaded_at timestamp with time zone NOT NULL
);


--
-- Name: dataset_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_versions (
    id character varying(12) NOT NULL,
    dataset_id character varying(12) NOT NULL,
    version_number integer NOT NULL,
    files_snapshot json NOT NULL,
    created_by character varying(12),
    note character varying(255),
    created_at timestamp with time zone NOT NULL
);


--
-- Name: datasets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.datasets (
    id character varying(12) NOT NULL,
    user_id character varying(12),
    description text DEFAULT ''::text,
    name character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    tags json DEFAULT '[]'::json,
    archived boolean DEFAULT false,
    data_meta json
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id character varying(12) NOT NULL,
    project_id character varying(12) NOT NULL,
    status character varying(20) NOT NULL,
    config json,
    results_path text,
    error_message text,
    created_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    name character varying(255),
    user_id character varying(12),
    config_hash character varying(32),
    disk_size_bytes bigint,
    batch_id character varying(12),
    best_auc double precision,
    best_k integer,
    scitq_task_id integer
);


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    id character varying(12) NOT NULL,
    user_id character varying(12) NOT NULL,
    token_hash character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: project_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_comments (
    id character varying(12) NOT NULL,
    project_id character varying(12) NOT NULL,
    user_id character varying(12) NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: project_datasets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_datasets (
    id character varying(12) NOT NULL,
    project_id character varying(12) NOT NULL,
    dataset_id character varying(12) NOT NULL,
    assigned_at timestamp with time zone NOT NULL
);


--
-- Name: project_shares; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_shares (
    id character varying(12) NOT NULL,
    project_id character varying(12) NOT NULL,
    user_id character varying(12) NOT NULL,
    role character varying(10) NOT NULL,
    shared_at timestamp with time zone NOT NULL,
    shared_by character varying(12)
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id character varying(12) NOT NULL,
    name character varying(255) NOT NULL,
    user_id character varying(12) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    description character varying(500) DEFAULT ''::character varying,
    updated_at timestamp with time zone,
    class_names json,
    archived boolean DEFAULT false
);


--
-- Name: public_shares; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_shares (
    id character varying(12) NOT NULL,
    project_id character varying(12) NOT NULL,
    token character varying(64) NOT NULL,
    created_by character varying(12) NOT NULL,
    expires_at timestamp with time zone,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: schema_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_versions (
    id integer NOT NULL,
    version character varying(50) NOT NULL,
    applied_at timestamp with time zone NOT NULL
);


--
-- Name: schema_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.schema_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: schema_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.schema_versions_id_seq OWNED BY public.schema_versions.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id character varying(12) NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    is_admin boolean DEFAULT false,
    email_verified boolean DEFAULT false
);


--
-- Name: webhooks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.webhooks (
    id character varying(12) NOT NULL,
    user_id character varying(12) NOT NULL,
    name character varying(100) NOT NULL,
    url character varying(500) NOT NULL,
    events json,
    secret character varying(64) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: schema_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_versions ALTER COLUMN id SET DEFAULT nextval('public.schema_versions_id_seq'::regclass);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: dataset_files dataset_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_files
    ADD CONSTRAINT dataset_files_pkey PRIMARY KEY (id);


--
-- Name: dataset_versions dataset_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_versions
    ADD CONSTRAINT dataset_versions_pkey PRIMARY KEY (id);


--
-- Name: datasets datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: project_comments project_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_comments
    ADD CONSTRAINT project_comments_pkey PRIMARY KEY (id);


--
-- Name: project_datasets project_datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_datasets
    ADD CONSTRAINT project_datasets_pkey PRIMARY KEY (id);


--
-- Name: project_shares project_shares_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_shares
    ADD CONSTRAINT project_shares_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: public_shares public_shares_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_shares
    ADD CONSTRAINT public_shares_pkey PRIMARY KEY (id);


--
-- Name: schema_versions schema_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_versions
    ADD CONSTRAINT schema_versions_pkey PRIMARY KEY (id);


--
-- Name: schema_versions schema_versions_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_versions
    ADD CONSTRAINT schema_versions_version_key UNIQUE (version);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: webhooks webhooks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhooks
    ADD CONSTRAINT webhooks_pkey PRIMARY KEY (id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_jobs_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_batch_id ON public.jobs USING btree (batch_id);


--
-- Name: ix_jobs_config_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_config_hash ON public.jobs USING btree (config_hash);


--
-- Name: ix_public_shares_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_public_shares_token ON public.public_shares USING btree (token);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: dataset_files dataset_files_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_files
    ADD CONSTRAINT dataset_files_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(id) ON DELETE CASCADE;


--
-- Name: dataset_versions dataset_versions_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_versions
    ADD CONSTRAINT dataset_versions_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(id) ON DELETE CASCADE;


--
-- Name: jobs jobs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: jobs jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_comments project_comments_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_comments
    ADD CONSTRAINT project_comments_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_comments project_comments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_comments
    ADD CONSTRAINT project_comments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_datasets project_datasets_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_datasets
    ADD CONSTRAINT project_datasets_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(id) ON DELETE CASCADE;


--
-- Name: project_datasets project_datasets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_datasets
    ADD CONSTRAINT project_datasets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_shares project_shares_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_shares
    ADD CONSTRAINT project_shares_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_shares project_shares_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_shares
    ADD CONSTRAINT project_shares_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: projects projects_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: public_shares public_shares_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_shares
    ADD CONSTRAINT public_shares_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: public_shares public_shares_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_shares
    ADD CONSTRAINT public_shares_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: webhooks webhooks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhooks
    ADD CONSTRAINT webhooks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

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

--
-- Data for Name: schema_versions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.schema_versions (id, version, applied_at) FROM stdin;
1	v2_dataset_library	2026-02-13 18:59:16.880892+00
2	v3_composite_datasets	2026-02-13 20:30:49.643558+00
3	v4_admin_flag	2026-02-13 21:44:22.533599+00
4	v5_job_name	2026-02-14 10:46:47.053929+00
5	v6_job_user_id	2026-02-14 15:15:21.410371+00
6	v7_job_config_hash	2026-02-14 15:15:21.444894+00
7	v8_job_disk_size	2026-02-14 16:22:41.92755+00
8	v9_dataset_tags	2026-02-15 09:29:53.851391+00
9	v10_job_batch_id	2026-02-15 10:09:33.115833+00
10	v11_audit_log	2026-02-15 21:45:46.672806+00
11	v12_password_reset	2026-02-15 21:45:46.673974+00
12	v13_api_keys	2026-02-15 21:45:46.682107+00
13	v14_webhooks	2026-02-15 21:45:46.683302+00
14	v15_dataset_versions	2026-02-15 21:45:46.684551+00
15	v16_job_best_auc	2026-02-15 21:45:46.685472+00
16	v17_project_comments	2026-02-16 02:16:11.285651+00
17	v18_public_shares	2026-02-16 02:16:11.286845+00
18	v19_project_class_names	2026-02-16 13:34:27.318631+00
19	v20_dataset_archived	2026-02-16 13:50:07.351472+00
20	v21_dataset_data_meta	2026-02-16 14:22:38.067678+00
21	v22_scitq_task_id	2026-02-16 15:26:12.903439+00
22	v23_project_archived	2026-02-16 15:59:01.361183+00
\.


--
-- PostgreSQL database dump complete
--


