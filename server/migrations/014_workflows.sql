-- Migration 014: user-defined visual workflows (M13)
-- A workflow is a small DAG (nodes + edges) of existing platform steps
-- (search/enrich/score/generate_assets/send_email/filter_score), stored as
-- JSONB and executed by run_workflow_bg(). n8n integration is read-only
-- (listing your n8n workflows) and needs no new tables — see 013 for the
-- api_usage username column this feature also reports through.

CREATE TABLE IF NOT EXISTS workflows (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    graph JSONB NOT NULL DEFAULT '{"nodes": [], "edges": []}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id SERIAL PRIMARY KEY,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    log TEXT,
    node_results JSONB
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_wf ON workflow_runs(workflow_id);
