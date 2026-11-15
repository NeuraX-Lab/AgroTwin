"""Run the complete local demo from this checkout; Ctrl+C stops its processes."""
from pathlib import Path
import argparse
import os
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a1-port', type=int, default=8000)
    parser.add_argument('--v4-port', type=int, default=8184)
    parser.add_argument('--ui-port', type=int, default=5174)
    args = parser.parse_args()
    ports = [args.a1_port, args.v4_port, args.ui_port]
    if len(set(ports)) != 3 or not all(1024 <= p <= 65535 for p in ports):
        parser.error('Use three distinct ports between 1024 and 65535.')
    for port in ports:
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1', port))
            except OSError: parser.error(f'Port {port} is busy. Stop your old demo or choose alternate ports.')
    node = shutil.which('node')
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.is_file(): parser.error('Install Node.js and run npm ci in frontend first.')
    if not (ROOT / 'backend/runs/research-selected/artifact-manifest.json').is_file():
        parser.error('Run python scripts/bootstrap.py --offline first.')
    env = dict(os.environ, PYTHONUTF8='1',
               AGROTWIN_A1_URL=f'http://127.0.0.1:{args.a1_port}',
               AGROTWIN_V4_URL=f'http://127.0.0.1:{args.v4_port}',
               FIELDSHIFT_DASHBOARD_ORIGINS=f'http://127.0.0.1:{args.ui_port},http://localhost:{args.ui_port}')
    jobs = [
        (ROOT/'a1', [sys.executable,'-m','uvicorn','neurax.api:app','--host','127.0.0.1','--port',str(args.a1_port)]),
        (ROOT/'backend', [sys.executable,'-m','uvicorn','scripts.selected_v4_api:app','--host','127.0.0.1','--port',str(args.v4_port)]),
        (ROOT/'frontend', [node,str(vite),'--host','127.0.0.1','--port',str(args.ui_port),'--strictPort']),
    ]
    processes = []
    try:
        for cwd, command in jobs: processes.append(subprocess.Popen(command,cwd=cwd,env=env))
        print(f'\nAgroTwin: http://127.0.0.1:{args.ui_port}/w/my-thanh/farmer\nCtrl+C stops this demo.\n', flush=True)
        while all(p.poll() is None for p in processes): time.sleep(.5)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None: process.terminate()
        for process in processes:
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait()

if __name__ == '__main__': sys.exit(main())
