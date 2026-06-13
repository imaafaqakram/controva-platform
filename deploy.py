#!/usr/bin/env python3
"""
Deploy local changes to the live server.
Usage:
    python deploy.py            # deploy both leads_api.py + dashboard.html, restart service
    python deploy.py api        # deploy only leads_api.py + restart
    python deploy.py ui         # deploy only dashboard.html (no restart needed - served from disk)
    python deploy.py pull       # download the live files FROM the server to local (overwrites local)
    python deploy.py logs       # tail the live server logs
    python deploy.py status     # show service + container status

Requires: pip install paramiko
Reads connection settings from deploy.env (copy deploy.env.example first).
"""
import sys, os, io

try:
    import paramiko
except ImportError:
    print("Missing dependency. Run: pip install paramiko")
    sys.exit(1)

# ── Load settings from deploy.env ─────────────────────────────
def load_env():
    env = {}
    env_file = os.path.join(os.path.dirname(__file__), 'deploy.env')
    if not os.path.exists(env_file):
        print("ERROR: deploy.env not found.")
        print("Copy deploy.env.example to deploy.env and fill in your server details.")
        sys.exit(1)
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env

ENV = load_env()
HOST = ENV.get('SERVER_IP', '')
PORT = int(ENV.get('SERVER_PORT', '22'))
USER = ENV.get('SERVER_USER', 'root')
PASS = ENV.get('SERVER_PASSWORD', '')
REMOTE_DIR = ENV.get('REMOTE_DIR', '/opt/leadgen')

LOCAL_SERVER = os.path.join(os.path.dirname(__file__), 'server')

# ── SSH helpers ───────────────────────────────────────────────
def get_client():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASS, timeout=20)
    return c

def run(cmd, timeout=60):
    c = get_client()
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode('utf-8', errors='replace')
    err = se.read().decode('utf-8', errors='replace')
    c.close()
    return out, err

def upload(local_name, remote_name):
    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    sftp.put(os.path.join(LOCAL_SERVER, local_name), f'{REMOTE_DIR}/{remote_name}')
    sftp.close()
    transport.close()
    size = os.path.getsize(os.path.join(LOCAL_SERVER, local_name))
    print(f'  Uploaded {local_name} -> {REMOTE_DIR}/{remote_name} ({size:,} bytes)')

def download(remote_name, local_name):
    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    sftp.get(f'{REMOTE_DIR}/{remote_name}', os.path.join(LOCAL_SERVER, local_name))
    sftp.close()
    transport.close()
    print(f'  Downloaded {REMOTE_DIR}/{remote_name} -> {local_name}')

def restart():
    print('Restarting leadgen-api service...')
    out, _ = run('systemctl restart leadgen-api && sleep 4 && systemctl is-active leadgen-api')
    print(f'  Service: {out.strip()}')
    # Quick health check
    out2, _ = run('curl -s http://localhost:8080/health')
    print(f'  Health: {out2.strip()[:80]}')

# ── Commands ──────────────────────────────────────────────────
def cmd_deploy_api():
    print('Deploying API server...')
    upload('leads_api.py', 'leads_api.py')
    restart()

def cmd_deploy_ui():
    print('Deploying dashboard...')
    upload('dashboard.html', 'dashboard.html')
    print('  Dashboard served from disk - no restart needed. Refresh browser (Ctrl+F5).')

def cmd_deploy_all():
    print('Deploying API + dashboard...')
    upload('leads_api.py', 'leads_api.py')
    upload('dashboard.html', 'dashboard.html')
    restart()

def cmd_pull():
    print('Pulling live files from server (overwrites local)...')
    download('leads_api.py', 'leads_api.py')
    download('dashboard.html', 'dashboard.html')
    print('Done. Your local copies now match the server.')

def cmd_logs():
    print('Live server logs (Ctrl+C to stop)...')
    print('=' * 60)
    c = get_client()
    chan = c.get_transport().open_session()
    chan.exec_command('journalctl -u leadgen-api -f -n 30 --no-pager')
    try:
        while True:
            if chan.recv_ready():
                sys.stdout.write(chan.recv(4096).decode('utf-8', errors='replace'))
                sys.stdout.flush()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        c.close()

def cmd_status():
    print('=== Service status ===')
    out, _ = run('systemctl is-active leadgen-api')
    print(f'API service: {out.strip()}')
    print()
    print('=== Docker containers ===')
    out2, _ = run('docker ps --format "{{.Names}}: {{.Status}}"')
    print(out2)
    print('=== Health ===')
    out3, _ = run('curl -s http://localhost:8080/health')
    print(out3.strip()[:200])

# ── Main ──────────────────────────────────────────────────────
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    arg = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if not HOST or not PASS:
        print('ERROR: SERVER_IP or SERVER_PASSWORD missing in deploy.env')
        sys.exit(1)

    cmds = {
        'all': cmd_deploy_all, 'api': cmd_deploy_api, 'ui': cmd_deploy_ui,
        'pull': cmd_pull, 'logs': cmd_logs, 'status': cmd_status,
    }
    if arg not in cmds:
        print(f'Unknown command: {arg}')
        print('Valid: all | api | ui | pull | logs | status')
        sys.exit(1)
    cmds[arg]()
