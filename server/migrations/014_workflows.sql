-- Migration 014: user-defined visual workflows (M13)
-- A workflow is a small DAG (nodes + edges) of existing platform steps
-- (search/enrich/score/generate_assets/send_email/filter_score), stored as
-- JSONB and executed by run_workflow_bg(). n8n integration is read-only
-- (listing your n8n workflows) and needs no new tables — see 013 for the
-- api_usage username column this feature also reports through.
--
-- Table is named wf_canvas_runs, NOT workflow_runs: init.sql already
-- defines an unrelated (and, confirmed live, currently unused — 0 rows,
-- referenced nowhere in leads_api.py) workflow_runs table for "n8n
-- workflow executions". A first version of this migration reused that
-- name; CREATE TABLE IF NOT EXISTS silently no-opped against its
-- incompatible columns, then the index statement below failed loudly
-- ("column workflow_id does not exist"). Renamed to avoid the collision;
-- the pre-existing table is left untouched since its actual purpose/
-- consumers aren't established.

CREATE TABLE IF NOT EXISTS workflows (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    graph JSONB NOT NULL DEFAULT '{"nodes": [], "edges": []}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wf_canvas_runs (
    id SERIAL PRIMARY KEY,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    log TEXT,
    node_results JSONB
);

CREATE INDEX IF NOT EXISTS idx_wf_canvas_runs_workflow_id ON wf_canvas_runs(workflow_id);
