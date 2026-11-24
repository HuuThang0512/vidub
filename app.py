"""ViDub - local video subtitle + voice-over tool.
Run: python app.py  ->  http://localhost:7860
"""
import os, json, uuid, threading, subprocess, time, re, asyncio, wave, array, traceback, shutil
from flask import Flask, request, jsonify, send_file, send_from_directory, abort

ROOT = os.path.dirname(os.path.abspath(__file__))
PORTABLE = os.path.isdir(os.path.join(ROOT, '.venv'))  # installed by Cai_dat.bat
_ff = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin')
if os.path.isdir(_ff): os.environ['PATH'] = _ff + os.pathsep + os.environ.get('PATH', '')
if PORTABLE: os.environ.setdefault('HF_HOME', os.path.join(ROOT, 'models'))  # keep models inside the app folder
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
import sys
VERSION = (open(os.path.join(ROOT, 'VERSION'), encoding='utf-8').read().strip()
           if os.path.exists(os.path.join(ROOT, 'VERSION')) else 'dev')
JOBS = os.path.join(ROOT, 'jobs')
os.makedirs(JOBS, exist_ok=True)
CFG = os.path.join(ROOT, 'config.json')
app = Flask(__name__, static_folder=os.path.join(ROOT, 'static'))
STATE = {}  # job_id -> runtime status
LOCK = threading.Lock()

# ---------------- helpers ----------------
def jdir(j):
    if not re.fullmatch(r'[a-f0-9]{12}', j or ''): abort(404)
    p = os.path.join(JOBS, j)
    if not os.path.isdir(p): abort(404)
    return p

def load_cfg():
    try: return json.load(open(CFG, encoding='utf-8'))
    except Exception: return {}

def save_cfg(d):
    c = load_cfg(); c.update(d); json.dump(c, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def meta(j, **kw):
    p = os.path.join(jdir(j), 'meta.json')
    m = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    if kw:
        m.update(kw); json.dump(m, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    return m

def segs_path(j): return os.path.join(jdir(j), 'segs.json')
def get_segs(j):
    p = segs_path(j)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else []
def put_segs(j, s): json.dump(s, open(segs_path(j), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

def status(j, step=None, progress=None, msg=None, error=None, busy=None):
    with LOCK:
        s = STATE.setdefault(j, {'step': 'idle', 'progress': 0, 'msg': '', 'error': None, 'busy': False})
        if step is not None: s['step'] = step
        if progress is not None: s['progress'] = progress
        if msg is not None: s['msg'] = msg
        if error is not None or step is not None: s['error'] = error
        if busy is not None: s['busy'] = busy
        return dict(s)

class Cancelled(Exception): pass

def check(j):
    if STATE.get(j, {}).get('cancel'): raise Cancelled()

def run_bg(j, fn, *a):
    if STATE.get(j, {}).get('busy'): return False
    status(j, busy=True, error=None)
    STATE[j]['cancel'] = False
    def wrap():
        try: fn(j, *a)
        except Cancelled:
            STATE[j]['cancel'] = False
            status(j, step='cancelled', progress=0, msg='Đã hủy. Anh chỉnh lại rồi bấm chạy lại khi muốn.', busy=False)
        except Exception as e:
            traceback.print_exc(); status(j, step='error', error=str(e), busy=False)
        else: status(j, busy=False)
    threading.Thread(target=wrap, daemon=True).start(); return True

def probe(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height,codec_type',
                                   '-of', 'json', path])
    d = json.loads(out); w = h = None
    for s in d.get('streams', []):
        if s.get('codec_type') == 'video' and s.get('width'): w, h = s['width'], s['height']; break
    return float(d['format']['duration']), w, h

def dur(p):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p]).strip())

# ---------------- 1. transcribe ----------------
WHISPER = {}
def do_transcribe(j, model_size, lang):
    d = jdir(j)
    status(j, step='transcribe', progress=0, msg='Đang tách âm thanh...')
    wav = os.path.join(d, 'audio16k.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(d, 'input.mp4'), '-ac', '1', '-ar', '16000', wav], check=True)
    total = dur(wav)
    status(j, msg=f'Đang tải model Whisper "{model_size}" (lần đầu sẽ tải về, hơi lâu)...')
    from faster_whisper import WhisperModel
    key = model_size
    if key not in WHISPER:
        try:
            mm = WhisperModel(model_size, device='cuda', compute_type='float16')
            import numpy as np
            list(mm.transcribe(np.zeros(32000, dtype=np.float32), language='en')[0])  # generator is lazy: force a real GPU run
            WHISPER[key] = mm
        except Exception:
            WHISPER[key] = WhisperModel(model_size, device='cpu', compute_type='int8')
    m = WHISPER[key]
    # decode the 16k mono wav ourselves (avoids PyAV version incompatibilities in faster-whisper)
    import numpy as np
    with wave.open(wav) as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs_iter, info = m.transcribe(pcm, language=(lang or None), vad_filter=True, word_timestamps=True)
    words = []
    for s in segs_iter:
        check(j)
        status(j, progress=min(99, int(s.end / total * 100)), msg=f'Đang nghe lời thoại... {int(s.end)}s / {int(total)}s')
        for w in (s.words or []): words.append([w.start, w.end, w.word])
    # group words into sentence-ish cues
    cues, cur = [], None
    for ws, we, t in words:
        if cur and (ws - cur[1] > 1.2): cues.append(cur); cur = None
        if cur is None: cur = [ws, we, t.strip()]
        else: cur[1] = we; cur[2] += t
        txt = cur[2].strip()
        if (re.search(r'[.?!。？！]["”」]?$', txt) and (cur[1] - cur[0] > 2.5 or len(txt) > 50)) or cur[1] - cur[0] > 8 or (re.search(r'[,;:，、；：]$', txt) and cur[1] - cur[0] > 5):
            cues.append(cur); cur = None
    if cur: cues.append(cur)
    out = [{'start': round(a, 2), 'end': round(b, 2), 'src': t.strip(), 'tgt': ''} for a, b, t in cues if t.strip()]
    put_segs(j, out); meta(j, src_lang=info.language)
    status(j, step='transcribed', progress=100, msg=f'Xong: {len(out)} câu (ngôn ngữ: {info.language})')

# ---------------- 2. translate ----------------
def gemini_models(key):
    from google import genai
    c = genai.Client(api_key=key)
    names = []
    for m in c.models.list():
        acts = getattr(m, 'supported_actions', None) or []
        n = m.name.replace('models/', '')
        if 'generateContent' in acts and 'gemini' in n and not any(x in n for x in ('embedding', 'tts', 'image', 'audio', 'live')):
            names.append(n)
    return names

def tr_gemini(key, model, texts, target, context):
    from google import genai
    from google.genai import types
    c = genai.Client(api_key=key)
    prompt = (f"Translate each subtitle line into natural, spoken {target} for a voice-over. "
              "Keep it concise (similar length to the source, it must be read aloud in the same time). "
              "Keep product names and common technical terms (API, prompt, token, model names, eval...) in English. "
              "Return ONLY a JSON array of strings with exactly the same number of items, same order.\n"
              + (f"Context: {context}\n" if context else '') + "Lines:\n" + json.dumps(texts, ensure_ascii=False))
    for attempt in range(4):
        try:
            r = c.models.generate_content(model=model, contents=prompt,
                                          config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0.3))
            arr = json.loads(r.text)
            if isinstance(arr, list) and len(arr) == len(texts): return [str(x) for x in arr]
            raise ValueError(f'Gemini trả về {len(arr)} dòng thay vì {len(texts)}')
        except Exception as e:
            if attempt == 3: raise
            time.sleep(3 * (attempt + 1))

def tr_cloud(key, texts, target_code):
    import requests
    r = requests.post('https://translation.googleapis.com/language/translate/v2', params={'key': key},
                      json={'q': texts, 'target': target_code, 'format': 'text'}, timeout=60)
    if r.status_code != 200: raise RuntimeError('Cloud Translation lỗi: ' + r.text[:300])
    import html
    return [html.unescape(t['translatedText']) for t in r.json()['data']['translations']]

LANGS = {'vi': 'Vietnamese', 'en': 'English', 'ja': 'Japanese', 'ko': 'Korean', 'zh-CN': 'Simplified Chinese', 'fr': 'French', 'th': 'Thai'}

def do_translate(j, key, provider, model, target, context, only_empty):
    segs = get_segs(j)
    idx = [i for i, s in enumerate(segs) if not (only_empty and s.get('tgt'))]
    status(j, step='translate', progress=0, msg='Đang dịch...')
    used = provider
    B = 40
    for b in range(0, len(idx), B):
        check(j)
        part = idx[b:b + B]; texts = [segs[i]['src'] for i in part]
        res = None
        if provider in ('auto', 'gemini'):
            try: res = tr_gemini(key, model or 'gemini-2.5-flash', texts, LANGS.get(target, target), context); used = 'gemini'
            except Exception as e:
                if provider == 'gemini': raise RuntimeError('Gemini lỗi: ' + str(e)[:300])
                status(j, msg=f'Gemini không dùng được ({str(e)[:80]}), chuyển sang Cloud Translation...')
        if res is None: res = tr_cloud(key, texts, target); used = 'cloud'
        for i, t in zip(part, res): segs[i]['tgt'] = t
        put_segs(j, segs)
        status(j, progress=int((b + len(part)) / max(1, len(idx)) * 100), msg=f'Đã dịch {b + len(part)}/{len(idx)} câu ({used})')
    status(j, step='translated', progress=100, msg=f'Dịch xong bằng {"Gemini" if used == "gemini" else "Cloud Translation"}')

# ---------------- 3. subtitles (ASS) ----------------
def ass_color(hexc, opacity=1.0):
    hexc = (hexc or '#FFFFFF').lstrip('#')
    r, g, b = hexc[0:2], hexc[2:4], hexc[4:6]
    a = int(round((1 - float(opacity)) * 255))
    return f'&H{a:02X}{b}{g}{r}'.upper()

def ass_time(x):
    cs = int(round(x * 100)); return f'{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}'

def build_ass(path, items, st, w, h):
    # items: list of (start, end, text)
    size = int(float(st.get('size', 5)) / 100 * h)  # size as % of video height
    align = {'bottom': 2, 'middle': 5, 'top': 8}.get(st.get('position', 'bottom'), 2)
    marginv = int(float(st.get('margin', 6)) / 100 * h)
    box = st.get('mode', 'outline') == 'box'
    primary = ass_color(st.get('color', '#FFFFFF'))
    if box:
        outline_col = ass_color(st.get('bg', '#000000'), st.get('bgOpacity', 0.6))
        border, outline, shadow, back = 3, max(1, int(size * 0.25)), 0, outline_col
    else:
        outline_col = ass_color(st.get('outlineColor', '#000000'))
        border, outline, shadow = 1, float(st.get('outlineWidth', 2)) * h / 720, float(st.get('shadow', 1)) * h / 720
        back = ass_color(st.get('shadowColor', '#000000'), 0.6)
    font = st.get('font', 'Arial'); bold = -1 if st.get('bold') else 0; italic = -1 if st.get('italic') else 0
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{primary},{outline_col},{back},{bold},{italic},0,0,100,100,0,0,{border},{outline:.1f},{shadow:.1f},{align},{int(w*0.06)},{int(w*0.06)},{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for a, b, t in items:
        t = (t or '').replace('\n', ' ').replace('{', '(').replace('}', ')')
        if st.get('upper'): t = t.upper()
        mc = int(st.get('maxChars', 42))
        if mc > 0 and len(t) > mc:
            ws, rows, cur = t.split(' '), [], ''
            for w_ in ws:
                if cur and len(cur) + 1 + len(w_) > mc: rows.append(cur); cur = w_
                else: cur = (cur + ' ' + w_).strip()
            if cur: rows.append(cur)
            if len(rows) == 2 and len(rows[1]) < len(rows[0]) * 0.4:  # balance 2 lines
                half = len(t) // 2; k = t.rfind(' ', 0, half + 8)
                if k > 0: rows = [t[:k], t[k + 1:]]
            t = r'\N'.join(rows)
        lines.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{t}')
    open(path, 'w', encoding='utf-8-sig').write(hdr + '\n'.join(lines) + '\n')

def split_sub(text, maxc):
    """Split text into chunks <= maxc chars, preferring sentence / clause boundaries."""
    text = ' '.join((text or '').split())
    if maxc <= 0 or len(text) <= maxc: return [text]
    parts = re.split(r'(?<=[.!?…。！？])\s+', text)
    out = []
    for p in parts:
        if len(p) <= maxc: out.append(p); continue
        clauses = re.split(r'(?<=[,;:，、；：])\s+', p)
        cur = ''
        for c in clauses:
            if len(c) > maxc:  # still too long -> split by words
                if cur: out.append(cur); cur = ''
                w = ''
                for word in c.split(' '):
                    if w and len(w) + 1 + len(word) > maxc: out.append(w); w = word
                    else: w = (w + ' ' + word).strip()
                cur = w
            elif cur and len(cur) + 1 + len(c) > maxc: out.append(cur); cur = c
            else: cur = (cur + ' ' + c).strip()
        if cur: out.append(cur)
    # merge tiny tails (<12 chars) into the previous chunk when it still fits loosely
    res = []
    for c in out:
        if res and len(c) < 12 and len(res[-1]) + len(c) + 1 <= maxc * 1.25: res[-1] += ' ' + c
        else: res.append(c)
    return res

def split_items(items, maxc):
    out = []
    for a, b, t in items:
        ch = split_sub(t, maxc)
        if len(ch) == 1: out.append((a, b, ch[0])); continue
        tot = sum(len(c) for c in ch); x = a
        for k, c in enumerate(ch):
            y = b if k == len(ch) - 1 else x + (b - a) * len(c) / tot
            out.append((x, y, c)); x = y
    return out

def blur_vf(opt, vh):
    bl = opt.get('blur') or {}
    if not bl.get('on'): return ''
    h = max(2, min(60, float(bl.get('height', 12)))) / 100
    pos = max(0, min(95, float(bl.get('bottom', 4)))) / 100
    top = max(0.0, 1 - pos - h)
    ch = max(4, int(vh * h) // 2 * 2)            # band height in px (even)
    y = int(vh * top) // 2 * 2
    # boxblur radius must be <= half of the plane size (chroma plane is half height for yuv420)
    lr = max(1, min(int(bl.get('strength', 35)), ch // 2 - 1))
    cr = max(1, min(lr, ch // 4 - 1))
    return (f"split[v0][v1];[v1]crop=iw:{ch}:0:{y},boxblur=luma_radius={lr}:luma_power=2:chroma_radius={cr}:chroma_power=2[bl];"
            f"[v0][bl]overlay=0:{y},")

def srt_time(x):
    ms = int(round(x * 1000)); return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'

# ---------------- 4. TTS + render ----------------
def _find_vieneu_py():
    import importlib.util
    if importlib.util.find_spec('vieneu'): return sys.executable          # same env (portable install)
    old = os.path.join(ROOT, '..', 'srt2voice', '.venv-vieneu', 'Scripts', 'python.exe')
    return old if os.path.exists(old) else ''
VIENEU_PY = _find_vieneu_py()

class VieNeu:
    """Keeps one VieNeu worker process alive (model loads once, ~10s)."""
    def __init__(self): self.p = None; self.lock = threading.Lock(); self.voices = None
    def available(self): return bool(VIENEU_PY) and os.path.exists(VIENEU_PY)
    def _start(self):
        if self.p and self.p.poll() is None: return
        self.p = subprocess.Popen([VIENEU_PY, os.path.join(ROOT, 'vieneu_worker.py')], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        r = json.loads(self.p.stdout.readline() or '{}')
        if not r.get('ready'): raise RuntimeError('VieNeu không khởi động được')
    def call(self, req):
        with self.lock:
            self._start()
            self.p.stdin.write(json.dumps(req, ensure_ascii=False) + '\n'); self.p.stdin.flush()
            line = self.p.stdout.readline()
            if not line: self.p = None; raise RuntimeError('VieNeu bị dừng đột ngột')
            r = json.loads(line)
            if not r.get('ok'): raise RuntimeError('VieNeu lỗi: ' + r.get('error', ''))
            return r
    def list(self):
        if self.voices is None: self.voices = self.call({'cmd': 'voices'})['voices']
        return self.voices
VIENEU = VieNeu()

def tts_vieneu(text, out, voice, rate, pitch):
    raw = out + '.raw.wav'
    VIENEU.call({'cmd': 'synth', 'text': text, 'voice': voice, 'out': raw})
    r = 1 + int(rate.rstrip('%')) / 100; p = int(pitch.rstrip('Hz'))
    af = []
    if p: f = 2 ** (p / 120); af += [f'asetrate=48000*{f:.4f}', 'aresample=48000']; r /= f
    if abs(r - 1) > 0.01: af.append(f'atempo={max(0.5, min(2.0, r)):.3f}')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw] + (['-af', ','.join(af)] if af else []) + [out], check=True)
    os.remove(raw)

async def _tts(text, out, voice, rate, pitch):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)

def tts(text, out, voice, rate, pitch, on_wait=None, cancel=None):
    if voice.startswith('vieneu:'):
        return tts_vieneu(text, out, voice[7:], rate, pitch)
    for attempt in range(25):
        try:
            asyncio.run(_tts(text, out, voice, rate, pitch))
            if os.path.exists(out) and os.path.getsize(out) > 500: return
            raise RuntimeError('file rỗng')
        except Exception as e:
            if attempt == 24: raise RuntimeError(f'Edge TTS lỗi liên tục: {e}')
            if on_wait: on_wait(attempt)
            for _ in range(min(4 + attempt * 4, 60)):
                if cancel: cancel()
                time.sleep(1)

def do_render(j, opt):
    d = jdir(j); segs = [s for s in get_segs(j) if (s.get('tgt') or '').strip()]
    if not segs: raise RuntimeError('Chưa có câu nào được dịch')
    src = os.path.join(d, 'input.mp4'); total, w, h = probe(src)
    voice = opt.get('voice', 'vi-VN-NamMinhNeural')
    rate = f"{int(opt.get('rate', 0)):+d}%"; pitch = f"{int(opt.get('pitch', 0)):+d}Hz"
    maxspeed = float(opt.get('maxSpeed', 1.6)); dub = opt.get('dub', True)
    tdir = os.path.join(d, 'tts'); os.makedirs(tdir, exist_ok=True)
    SR = 24000
    items = []
    if dub:
        buf = array.array('h', bytes(2 * int((total + 2) * SR)))
        for i, s in enumerate(segs):
            check(j)
            nxt = segs[i + 1]['start'] if i + 1 < len(segs) else total
            slot = max(nxt - s['start'] - 0.08, 0.4)
            tag = re.sub(r'[^\w]', '', f"{voice}{rate}{pitch}")
            ext = 'wav' if voice.startswith('vieneu:') else 'mp3'
            mp3 = os.path.join(tdir, f"{i}_{__import__('hashlib').md5((s['tgt'] + voice).encode()).hexdigest()[:10]}_{tag}.{ext}")
            status(j, step='render', progress=int(i / len(segs) * 80),
                   msg=('Đang tải model VieNeu (lần đầu ~10-60 giây)...' if ext == 'wav' and i == 0 else f'Đang đọc giọng câu {i + 1}/{len(segs)}...'))
            if not (os.path.exists(mp3) and os.path.getsize(mp3) > 500):
                tts(s['tgt'], mp3, voice, rate, pitch,
                    on_wait=lambda a, i=i: status(j, msg=f'Edge TTS đang giới hạn lượt gọi, chờ thử lại câu {i + 1} (lần {a + 1})... Mẹo: hủy rồi chọn giọng VieNeu sẽ nhanh hơn.'),
                    cancel=lambda: check(j))
            d0 = dur(mp3); sp = min(max(d0 / slot, 1.0), maxspeed)
            wv = os.path.join(tdir, 'seg.wav')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp3, '-af', f'atempo={sp:.3f}', '-ac', '1', '-ar', str(SR), '-sample_fmt', 's16', wv], check=True)
            with wave.open(wv) as f: pcm = array.array('h', f.readframes(f.getnframes()))
            off = int(s['start'] * SR); n = min(len(pcm), len(buf) - off)
            if n > 0: buf[off:off + n] = pcm[:n]
            end = min(nxt - 0.05, s['start'] + max(s['end'] - s['start'], d0 / sp))
            items.append((s['start'], max(end, s['start'] + 0.5), s['tgt']))
        vw = os.path.join(d, 'voice.wav')
        with wave.open(vw, 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(buf.tobytes())
    else:
        for i, s in enumerate(segs):
            nxt = segs[i + 1]['start'] if i + 1 < len(segs) else total
            items.append((s['start'], min(nxt - 0.05, max(s['end'], s['start'] + 1)), s['tgt']))
    # subtitle files
    open(os.path.join(d, 'output.srt'), 'w', encoding='utf-8').write(
        '\n'.join(f'{k + 1}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n' for k, (a, b, t) in enumerate(items)))
    maxc = int(opt.get('style', {}).get('maxChars', 42)) * int(opt.get('style', {}).get('maxLines', 2))
    items = split_items(items, maxc)
    burn = opt.get('burn', True)
    if burn: build_ass(os.path.join(d, 'subs.ass'), items, opt.get('style', {}), w, h)
    status(j, progress=82, msg='Đang ghép video (bước cuối)...')
    bgv = float(opt.get('bgVolume', 15)) / 100; vv = float(opt.get('voiceVolume', 100)) / 100
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', 'input.mp4']
    if dub:
        cmd += ['-i', 'voice.wav', '-filter_complex',
                f'[0:a]volume={bgv}[bg];[1:a]volume={vv}[vo];[bg][vo]amix=inputs=2:normalize=0:duration=first[aout]',
                '-map', '0:v', '-map', '[aout]']
    else:
        cmd += ['-map', '0:v', '-map', '0:a?']
    vf = blur_vf(opt, h) + ('ass=subs.ass' if burn else '')
    vf = vf.rstrip(',')
    if vf: cmd += ['-vf', vf, '-c:v', 'libx264', '-crf', '21', '-preset', 'fast']
    else: cmd += ['-c:v', 'copy']
    out = 'output.mp4'
    cmd += ['-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', out]
    p = subprocess.Popen(cmd + ['-progress', 'pipe:1', '-nostats'], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        if STATE.get(j, {}).get('cancel'):
            p.kill(); p.wait(); raise Cancelled()
        if line.startswith('out_time_us='):
            try: status(j, progress=82 + int(int(line.split('=')[1]) / 1e6 / total * 17))
            except ValueError: pass
    err = p.stderr.read()
    if p.wait() != 0: raise RuntimeError('ffmpeg lỗi: ' + err[-400:])
    meta(j, rendered=time.time())
    status(j, step='done', progress=100, msg='Xong! Video đã sẵn sàng.')

# ---------------- routes ----------------
@app.get('/')
def index():
    r = send_from_directory(app.static_folder, 'index.html', max_age=0)
    r.headers['Cache-Control'] = 'no-store'; return r

@app.get('/api/config')
def get_config():
    c = load_cfg(); k = c.get('key', '')
    return jsonify({**{x: y for x, y in c.items() if x != 'key'}, 'hasKey': bool(k), 'keyHint': (k[:4] + '…' + k[-4:]) if k else ''})

@app.post('/api/config')
def set_config():
    d = request.json or {}
    if 'key' in d and not d['key']: d.pop('key')
    save_cfg(d); return get_config()

@app.post('/api/models')
def models():
    k = (request.json or {}).get('key') or load_cfg().get('key')
    if not k: return jsonify({'error': 'Chưa nhập key'}), 400
    try: return jsonify({'models': gemini_models(k)})
    except Exception as e: return jsonify({'error': str(e)[:300]}), 400

VOICES = []
@app.get('/api/voices')
def voices():
    global VOICES
    if not VOICES:
        import edge_tts
        VOICES = sorted(asyncio.run(edge_tts.list_voices()), key=lambda v: v['ShortName'])
    out = []
    if VIENEU.available():
        try:
            for label, vid in VIENEU.list():
                g = 'Female' if '— Nữ' in label else 'Male'
                out.append({'id': 'vieneu:' + vid, 'locale': 'vi-VN (VieNeu)', 'gender': g, 'name': label, 'engine': 'vieneu'})
        except Exception as e:
            print('VieNeu unavailable:', e)
    out += [{'id': v['ShortName'], 'locale': v['Locale'], 'gender': v['Gender'], 'engine': 'edge',
             'name': v.get('FriendlyName', v['ShortName'])} for v in VOICES]
    return jsonify(out)

@app.post('/api/voice-sample')
def voice_sample():
    d = request.json or {}
    vce = d.get('voice', '')
    out = os.path.join(JOBS, f"sample_{uuid.uuid4().hex[:8]}.{'wav' if vce.startswith('vieneu:') else 'mp3'}")
    try: tts(d.get('text') or 'Xin chào, đây là giọng đọc thử.', out, d.get('voice', 'vi-VN-NamMinhNeural'),
        f"{int(d.get('rate', 0)):+d}%", f"{int(d.get('pitch', 0)):+d}Hz")
    except Exception as e: return jsonify({'error': str(e)[:300]}), 500
    resp = send_file(out, mimetype='audio/wav' if out.endswith('.wav') else 'audio/mpeg')
    threading.Timer(30, lambda: os.path.exists(out) and os.remove(out)).start()
    return resp

@app.get('/api/jobs')
def jobs():
    out = []
    for j in sorted(os.listdir(JOBS), key=lambda x: -os.path.getmtime(os.path.join(JOBS, x))):
        if os.path.isdir(os.path.join(JOBS, j)) and re.fullmatch(r'[a-f0-9]{12}', j):
            m = meta(j); out.append({'id': j, 'name': m.get('name'), 'created': m.get('created'), 'done': bool(m.get('rendered'))})
    return jsonify(out)

@app.post('/api/upload')
def upload():
    f = request.files.get('file')
    if not f: return jsonify({'error': 'Không có file'}), 400
    j = uuid.uuid4().hex[:12]; d = os.path.join(JOBS, j); os.makedirs(d)
    raw = os.path.join(d, 'raw' + os.path.splitext(f.filename)[1].lower()); f.save(raw)
    # normalise to mp4 (copy if possible)
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-c', 'copy', '-movflags', '+faststart', os.path.join(d, 'input.mp4')])
    if r.returncode != 0:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-c:v', 'libx264', '-crf', '20', '-c:a', 'aac', os.path.join(d, 'input.mp4')], check=True)
    os.remove(raw)
    total, w, h = probe(os.path.join(d, 'input.mp4'))
    meta(j, name=f.filename, created=time.time(), duration=total, width=w, height=h)
    run_bg(j, do_transcribe, request.form.get('model', 'small'), request.form.get('lang') or None)
    return jsonify({'id': j})

@app.get('/api/job/<j>')
def job(j):
    jdir(j); st = STATE.get(j) or {'step': 'idle', 'progress': 0, 'msg': '', 'error': None, 'busy': False}
    return jsonify({'id': j, 'meta': meta(j), 'status': st, 'segs': get_segs(j),
                    'hasOutput': os.path.exists(os.path.join(jdir(j), 'output.mp4'))})

@app.post('/api/job/<j>/retranscribe')
def retranscribe(j):
    jdir(j); d = request.json or {}
    ok = run_bg(j, do_transcribe, d.get('model', 'small'), d.get('lang') or None)
    return jsonify({'ok': ok})

@app.post('/api/job/<j>/segs')
def save_segs(j):
    jdir(j); s = (request.json or {}).get('segs')
    if not isinstance(s, list): return jsonify({'error': 'bad'}), 400
    put_segs(j, s); return jsonify({'ok': True})

@app.post('/api/job/<j>/translate')
def translate(j):
    jdir(j); d = request.json or {}; c = load_cfg()
    key = d.get('key') or c.get('key')
    if not key: return jsonify({'error': 'Chưa nhập Google API key'}), 400
    ok = run_bg(j, do_translate, key, d.get('provider', 'auto'), d.get('model') or c.get('model'),
                d.get('target', 'vi'), d.get('context', ''), d.get('onlyEmpty', False))
    return jsonify({'ok': ok})

@app.post('/api/job/<j>/render')
def render(j):
    jdir(j); ok = run_bg(j, do_render, request.json or {}); return jsonify({'ok': ok})

@app.get('/api/version')
def version():
    import update
    try: latest = update.latest_version()
    except Exception as e: latest = None
    return jsonify({'current': VERSION, 'latest': latest, 'canUpdate': bool(latest) and latest != VERSION and VERSION != 'dev'})

@app.post('/api/update')
def do_update():
    import update
    if any(s.get('busy') for s in STATE.values()):
        return jsonify({'error': 'Đang có tác vụ chạy, hủy hoặc chờ xong rồi cập nhật'}), 400
    try: msg = update.apply()
    except Exception as e: return jsonify({'error': str(e)[:300]}), 500
    def restart():
        time.sleep(1.5)
        bat = os.path.join(ROOT, 'ViDub.bat')
        subprocess.Popen(['cmd', '/c', 'start', '', bat], cwd=ROOT, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
        os._exit(0)
    threading.Thread(target=restart, daemon=True).start()
    return jsonify({'ok': True, 'msg': msg})

@app.post('/api/job/<j>/cancel')
def cancel(j):
    jdir(j)
    if not STATE.get(j, {}).get('busy'): return jsonify({'ok': False, 'msg': 'Không có tác vụ nào đang chạy'})
    STATE[j]['cancel'] = True; status(j, msg='Đang hủy...')
    return jsonify({'ok': True})

@app.post('/api/job/<j>/preview')
def preview(j):
    d = jdir(j); body = request.json or {}; m = meta(j)
    t = float(body.get('time', 1)); text = body.get('text') or 'Phụ đề xem thử — Preview subtitle'
    ass = os.path.join(d, 'preview.ass')
    st = body.get('style', {})
    first = split_sub(text, int(st.get('maxChars', 42)) * int(st.get('maxLines', 2)))[0]
    build_ass(ass, [(0, 100, first)], st, m['width'], m['height'])
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', 'input.mp4', '-frames:v', '1', '-vf',
                    'setpts=PTS-STARTPTS,' + blur_vf(body, m['height']) + 'ass=preview.ass', 'preview.jpg'], cwd=d, check=True)
    return send_file(os.path.join(d, 'preview.jpg'), mimetype='image/jpeg', max_age=0)

@app.get('/api/job/<j>/file/<name>')
def jfile(j, name):
    if name not in ('input.mp4', 'output.mp4', 'output.srt'): abort(404)
    p = os.path.join(jdir(j), name)
    if not os.path.exists(p): abort(404)
    base = os.path.splitext(meta(j).get('name') or 'video')[0]
    dl = request.args.get('dl')
    return send_file(p, conditional=True, as_attachment=bool(dl),
                     download_name=f"{base}_vi{os.path.splitext(name)[1]}" if dl else None)

@app.delete('/api/job/<j>')
def delete(j):
    shutil.rmtree(jdir(j), ignore_errors=True); STATE.pop(j, None); return jsonify({'ok': True})

if __name__ == '__main__':
    import webbrowser
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:7860')).start()
    app.run(host='127.0.0.1', port=7860, threaded=True)
