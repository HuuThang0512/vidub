# -*- coding: utf-8 -*-
"""Bọc VieNeu-TTS v3 Turbo (free, offline). Lazy-load model 1 lần."""
import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_model = None


def _get():
    global _model
    if _model is None:
        from vieneu import Vieneu
        _model = Vieneu()  # CPU/ONNX, fp32, 48kHz
    return _model


def list_voices():
    """Trả [(label, voice_id), ...] - 25 giọng preset."""
    return _get().list_preset_voices()


def synth(text, voice, out_path):
    """Sinh audio 1 đoạn -> lưu wav 48kHz."""
    m = _get()
    audio = m.infer(text, voice=voice)
    m.save(audio, out_path)
    return out_path


if __name__ == "__main__":
    for label, vid in list_voices():
        print(f"{vid}\t{label}")
