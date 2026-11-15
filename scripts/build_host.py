"""Prepare the frozen server resources and the production frontend."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    # Publisher files remain private function resources, never CDN assets.
    subprocess.run([sys.executable, str(ROOT/'scripts/bootstrap.py')], cwd=ROOT, check=True)
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm: raise RuntimeError('Node.js/npm is required to build the frontend')
    subprocess.run([npm,'ci','--no-audit','--no-fund'],cwd=ROOT/'frontend',check=True)
    subprocess.run([npm,'run','build'],cwd=ROOT/'frontend',check=True)

if __name__ == '__main__': main()
