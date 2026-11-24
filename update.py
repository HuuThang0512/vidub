# -*- coding: utf-8 -*-
"""ViDub updater: downloads the latest code from GitHub and replaces the app files.
Keeps user data (jobs/, config.json) and the installed runtime (.venv, tools, models).
Usage:  python update.py          (or via Cap_nhat.bat / the "Cập nhật" button)
"""
import os, sys, io, json, shutil, zipfile, subprocess, urllib.request, filecmp, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_FILE = os.path.join(ROOT, 'REPO')
REPO = open(REPO_FILE, encoding='utf-8').read().strip() if os.path.exists(REPO_FILE) else ''
BRANCH = 'main'
KEEP = {'jobs', 'config.json', '.venv', 'tools', 'models', 'uv', '.git', '__pycache__'}

def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'ViDub-updater', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()

def current_version():
    p = os.path.join(ROOT, 'VERSION')
    return open(p, encoding='utf-8').read().strip() if os.path.exists(p) else 'dev'

def latest_version():
    if not REPO: return None
    import time
    try:  # GitHub API: no CDN cache, shows a new version immediately
        req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/contents/VERSION?ref={BRANCH}',
                                     headers={'User-Agent': 'ViDub-updater', 'Accept': 'application/vnd.github.raw'})
        with urllib.request.urlopen(req, timeout=15) as r: return r.read().decode().strip()
    except Exception:  # rate-limited / offline -> raw CDN (may lag ~5 min)
        return _get(f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/VERSION?t={int(time.time())}', 15).decode().strip()

def apply():
    if not REPO: raise RuntimeError('Chưa cấu hình nguồn cập nhật (file REPO)')
    old_req = os.path.join(ROOT, 'requirements.txt')
    old_req_txt = open(old_req, encoding='utf-8').read() if os.path.exists(old_req) else ''
    data = _get(f'https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip', 300)
    z = zipfile.ZipFile(io.BytesIO(data))
    top = z.namelist()[0].split('/')[0]
    n = 0
    for info in z.infolist():
        rel = info.filename[len(top) + 1:]
        if not rel or rel.split('/')[0] in KEEP: continue
        dst = os.path.join(ROOT, *rel.split('/'))
        if info.is_dir(): os.makedirs(dst, exist_ok=True); continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        new = z.read(info)
        if os.path.exists(dst) and open(dst, 'rb').read() == new: continue
        tmp = dst + '.new'
        open(tmp, 'wb').write(new); os.replace(tmp, dst); n += 1
    new_req_txt = open(old_req, encoding='utf-8').read() if os.path.exists(old_req) else ''
    extra = ''
    if new_req_txt != old_req_txt:
        uv = os.path.join(ROOT, 'uv', 'uv.exe')
        py = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')
        if os.path.exists(uv) and os.path.exists(py):
            env = dict(os.environ, UV_CACHE_DIR=os.path.join(ROOT, 'uv', 'cache'))
            subprocess.run([uv, 'pip', 'install', '--python', py, '-r', old_req], check=True, env=env)
            extra = ', đã cài thêm thư viện mới'
    return f'Đã cập nhật lên bản {current_version()} ({n} file thay đổi{extra})'

if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    print('Phiên bản hiện tại:', current_version())
    try: lv = latest_version()
    except Exception as e: print('Không kiểm tra được bản mới:', e); sys.exit(1)
    print('Bản mới nhất     :', lv)
    if lv == current_version() and '--force' not in sys.argv:
        print('Anh đang dùng bản mới nhất rồi.'); sys.exit(0)
    print(apply())
