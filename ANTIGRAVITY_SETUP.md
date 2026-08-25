# Opening & Developing This Project in Antigravity

Antigravity is an AI-powered IDE (a VS Code fork). This project runs on a remote
server, so the workflow is: **edit the code locally in Antigravity → deploy to the
server with one command → refresh the dashboard in your browser.**

---

## One-Time Setup (5 minutes)

### 1. Open the Project Folder

In Antigravity:
- **File → Open Folder**
- Select: `C:\Users\ANC\Downloads\LeadGen_Platform_Complete`

You'll see the full project tree in the left sidebar.

### 2. Install the Deploy Tool Dependency

Open the integrated terminal (**Terminal → New Terminal** or `` Ctrl+` ``) and run:

```
pip install paramiko
```

### 3. Confirm Your Server Details

The file `deploy.env` already contains your server connection info:

```
SERVER_IP=YOUR_SERVER_IP
SERVER_USER=root
SERVER_PASSWORD=...
REMOTE_DIR=/opt/leadgen
```

> `deploy.env` is gitignored — your password will never be committed if you push to GitHub.

---

## The Two Files You'll Actually Edit

| File | What It Is | After editing, run... |
|---|---|---|
| `server/leads_api.py` | The entire backend (Python). All endpoints, logic, AI calls. | **Deploy: API only** (restarts service) |
| `server/dashboard.html` | The entire frontend (React in one file). All pages, UI. | **Deploy: UI only** (no restart needed) |

Everything else (`docker-compose.yml`, `init.sql`, etc.) you rarely touch.

---

## The Development Loop

### Option A — Use the Built-In Tasks (Recommended)

Press **`Ctrl+Shift+B`** (Run Build Task) — or open the Command Palette
(`Ctrl+Shift+P`) and type **"Run Task"** — then pick one:

| Task | What It Does |
|---|---|
| **Deploy: API + UI (full)** | Upload both files + restart service (default — `Ctrl+Shift+B`) |
| **Deploy: API only (restart)** | Upload `leads_api.py` + restart |
| **Deploy: UI only (no restart)** | Upload `dashboard.html` (just refresh browser) |
| **Pull from server** | Download the live files into your local copy |
| **Tail server logs** | Watch live server logs (great for debugging) |
| **Server status** | Check service + Docker container health |

### Option B — Terminal Commands

In the Antigravity terminal:

```
python deploy.py all       # deploy both + restart
python deploy.py api       # deploy backend + restart
python deploy.py ui        # deploy frontend (refresh browser)
python deploy.py pull      # pull live files down to local
python deploy.py logs      # tail server logs
python deploy.py status    # service + container status
```

---

## Typical Workflow Examples

### Example 1 — Change a button color in the dashboard

1. Open `server/dashboard.html`
2. Find the component, edit the Tailwind class
3. Save (`Ctrl+S`)
4. Run task **Deploy: UI only** (or `python deploy.py ui`)
5. Refresh your browser at `http://YOUR_SERVER_IP:8080/` (hard-refresh: `Ctrl+F5`)

### Example 2 — Add a new API endpoint

1. Open `server/leads_api.py`
2. Add your function + the `elif p == '/your-endpoint':` branch
   (see **3_DEVELOPER_GUIDE.docx** section 2.2 for the pattern)
3. Save
4. Run task **Deploy: API only** (or `python deploy.py api`)
5. Test: `curl -X POST http://YOUR_SERVER_IP:8080/your-endpoint`

### Example 3 — Debug a server error

1. Run task **Tail server logs** (keeps streaming)
2. In another terminal, trigger the action that fails
3. Watch the error appear live in the logs
4. Fix the code, redeploy, retest

---

## Using Antigravity's AI Agent

Antigravity has a built-in AI assistant. To use it on this project:

- Open the AI panel (usually `Ctrl+L` or the chat icon in the sidebar)
- Reference files with `@server/leads_api.py` or `@server/dashboard.html`
- Ask things like:
  - "Add a new endpoint that exports leads filtered by date range"
  - "Find where email sending happens and add a retry on failure"
  - "Explain how the geocoding cache works"

The AI can read the whole project context (it sees both the code and the
guides). After it edits a file, just run a Deploy task to push it live.

> Tip: Keep **3_DEVELOPER_GUIDE.docx** and **4_API_REFERENCE.md** in the project
> so the AI has full context on the architecture.

---

## Important: Avoid Editing on the Server Directly

Once you start editing locally in Antigravity, **always edit locally and deploy** —
don't also edit `/opt/leadgen/leads_api.py` directly on the server via SSH. If you
do, the two will drift apart.

If the server ever has newer changes than your local copy (e.g. someone else edited
it), run **Pull from server** first to sync down, then continue editing locally.

---

## Putting It Under Git (Optional but Recommended)

To track your changes and back them up to GitHub:

```
cd C:\Users\ANC\Downloads\LeadGen_Platform_Complete
git init
git add .
git commit -m "Initial commit of Controva Intelligence Platform"
```

`deploy.env` and `server/config.json` are already in `.gitignore`, so your
passwords and API keys stay private.

To push to GitHub:
```
git remote add origin https://github.com/YOUR_USERNAME/controva-platform.git
git push -u origin main
```

---

## Recommended Antigravity Extensions

For the best experience, install these from the Extensions panel (`Ctrl+Shift+X`):

- **Python** (Microsoft) — syntax, linting for `leads_api.py`
- **Tailwind CSS IntelliSense** — autocomplete for the dashboard classes
- **Error Lens** — shows errors inline
- **GitLens** — better git history

---

## Quick Reference

| I want to... | Do this |
|---|---|
| Open the project | File → Open Folder → `LeadGen_Platform_Complete` |
| Deploy everything | `Ctrl+Shift+B` |
| Deploy only UI changes | Run Task → "Deploy: UI only" |
| Watch live logs | Run Task → "Tail server logs" |
| Pull latest from server | Run Task → "Pull from server" |
| See the live dashboard | Browser → `http://YOUR_SERVER_IP:8080/` |
| Get AI help on the code | Open AI panel, reference `@server/leads_api.py` |

That's it. Edit locally, deploy with one click, refresh the browser.
