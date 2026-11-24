# -*- coding: utf-8 -*-
"""Long-running VieNeu worker. Runs inside srt2voice/.venv-vieneu.
Protocol: one JSON per line on stdin -> one JSON per line on stdout.
  {"cmd":"voices"}                         -> {"ok":true,"voices":[[label,id],...]}
  {"cmd":"synth","text":..,"voice":..,"out":..} -> {"ok":true}
"""
import sys, json, os, io, contextlib
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, '..', 'srt2voice'))
sys.path.insert(0, _here)  # prefer the copy shipped with ViDub
out = sys.stdout
sys.stdout = sys.stderr  # library prints must not corrupt the protocol
import engine_vieneu as ev

def reply(d):
    out.write(json.dumps(d, ensure_ascii=False) + "\n"); out.flush()

reply({"ok": True, "ready": True})
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        req = json.loads(line)
        if req.get("cmd") == "voices":
            reply({"ok": True, "voices": [list(v) for v in ev.list_voices()]})
        elif req.get("cmd") == "synth":
            ev.synth(req["text"], req["voice"], req["out"])
            reply({"ok": True})
        else:
            reply({"ok": False, "error": "unknown cmd"})
    except Exception as e:
        reply({"ok": False, "error": f"{type(e).__name__}: {e}"})
