# Multi-tenant simulation suite

`simulate.py` is a self-contained (stdlib only) end-to-end test of `server/leads_api.py`
against an already-running server. It does not start or stop anything.

## Run

    python3 testing/simulation/simulate.py \
        --base http://127.0.0.1:8080 --admin-user admin --admin-pass localdev123

Needs: Python 3, the server running, and `psql` access to the server's database (used to insert
leads/contacts, which cannot be created through the API without paid providers, and to verify DB
state). Two modes:

- Default: runs `su postgres -c "psql -d leadgen_db ..."` on the same machine (needs root/sudo).
- `SIM_DATABASE_URL` set: runs `psql "$SIM_DATABASE_URL" -Atc <sql>` directly (no `su`, no shell),
  e.g. `SIM_DATABASE_URL=postgresql://leadgen:PASS@127.0.0.1:5432/leadgen_db`. The role needs
  read/write on the app tables. Used by CI.

## CI

`.github/workflows/tests.yml` runs on every push and pull request: it starts a `postgres:16-alpine`
service, loads `server/init.sql`, starts `server/leads_api.py` in the background, waits for
`/health`, then runs this suite with `SIM_DATABASE_URL` set. `last_report.json` and the server
log are uploaded as the `simulation-results` artifact; the server log tail is printed on failure.

Exit code 0 = all checks PASS, 1 = at least one FAIL. A JSON report is written to
`testing/simulation/last_report.json` (override with `--report`).

## What it does

Each run picks a random suffix, so it is re-runnable and never relies on existing data.

1. Admin creates companies A and B (+ a second user in A), logs all three users in.
2. Seeds each company: ICP, channel figures, company settings (incl. an IMAP password),
   a webhook CRM connection (secret `s3cret-value`), a workflow; plus leads, contacts, an
   intent lead, an outreach row, a sequence enrollment and a batch id via psql; B also starts an
   `/enrich` job.
3. Isolation matrix (read): A reads ~24 endpoints and nothing of B's (ids, names, emails, ICP,
   workflow, CRM, channel labels, company/brand names, job) may appear; positive controls check A
   does see its own data.
4. Isolation matrix (write): A attempts every id-taking write/action against B's objects; each must
   be refused and a before/after DB snapshot of everything B owns must be identical.
5. Bulk jobs: A runs `/enrich /score /verify-emails /reenrich-missing-emails /research/queue
   /generate-assets /check-replies`; B's data must not change.
6. Admin-only endpoints refuse clients; unauthenticated requests get 401 on non-public routes.
7. Functional: performance math vs. hand calculation, outcome round-trip, erase, validation.
8. Billing: plans are admin-only, unsigned Stripe webhooks are refused, the subscription gate
   blocks and unblocks the right companies, comps work. With `SIM_STRIPE_WHSEC` set to the server's
   `STRIPE_WEBHOOK_SECRET`, also signed checkout / duplicate / cancel events, plan budget and seats.
9. Inbox: each company sees only its own replies and cannot draft, send or act on another's;
   draft, outcomes, reopen.
10. Report, DNS, viewer: the report is the caller's own company and escapes reply text; DNS checks
    only on own domains; a viewer reads its company's data and every write is refused.
11. Secrets: every response a client received is scanned for `s3cret-value`, real secret values
    from the server config / DB, and unmasked secret-named fields.

Test data (companies named `AlphaCo-A-<suffix>` / `BetaCo-B-<suffix>`) is left in the database.
