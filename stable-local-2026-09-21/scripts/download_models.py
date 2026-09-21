#!/usr/bin/env python3
"""Pre-download every model so `make demo` never reaches the network.

The review room WiFi will be bad. Cold start under 60 seconds is a hard
constraint, and fetching a model at launch breaks it.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

# The Hugging Face Xet transfer backend stalls on some networks and leaves a
# zero byte .incomplete file behind. Plain HTTPS from the CDN is slower in
# theory and reliable in practice, which is what a review room needs.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import (ASR_COMPUTE_TYPE, ASR_MODEL_SIZE, EMBED_MODEL, ENROLMENT_VOICES,  # noqa: E402
                        MODEL_DIR, PIPER_VOICES, SPOOF_VOICE)

ST_LOCAL_DIR = MODEL_DIR / "sentence_transformers" / EMBED_MODEL.split("/")[-1]
KOKORO_BASE = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
               "model-files-v1.0")
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_PATHS = {
    "en_US-amy-medium": "en/en_US/amy/medium/en_US-amy-medium.onnx",
    "hi_IN-pratham-medium": "hi/hi_IN/pratham/medium/hi_IN-pratham-medium.onnx",
    # Extra voices stand in for distinct enrolled speakers and for the spoof
    # attacker in the anti-spoof baseline.
    "en_US-lessac-medium": "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en_GB-alan-medium": "en/en_GB/alan/medium/en_GB-alan-medium.onnx",
    "en_US-ryan-medium": "en/en_US/ryan/medium/en_US-ryan-medium.onnx",
}


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  have  {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetch {dest.name}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)


def main() -> int:
    print("sentence-transformers:", EMBED_MODEL)
    # snapshot_download with an allow list rather than SentenceTransformer's own
    # fetch: the repo carries safetensors, a pytorch bin, ONNX, OpenVINO, Rust
    # and TensorFlow copies of the same weights, several gigabytes in total, and
    # exactly one of them is needed. This is also why cold start stays fast.
    from huggingface_hub import snapshot_download
    snapshot_download(
        EMBED_MODEL, local_dir=str(ST_LOCAL_DIR),
        allow_patterns=["*.json", "*.txt", "*.model", "model.safetensors",
                        "1_Pooling/*", "2_Dense/*"],
        ignore_patterns=["onnx/*", "openvino/*", "*.h5", "*.ot", "*.msgpack"])
    from sentence_transformers import SentenceTransformer
    SentenceTransformer(str(ST_LOCAL_DIR), device="cpu")

    print(f"faster-whisper: {ASR_MODEL_SIZE} ({ASR_COMPUTE_TYPE})")
    from faster_whisper import WhisperModel
    WhisperModel(ASR_MODEL_SIZE, device="cpu", compute_type=ASR_COMPUTE_TYPE,
                 download_root=str(MODEL_DIR / "faster-whisper"))

    print("speechbrain ECAPA-TDNN")
    from speechbrain.inference.speaker import EncoderClassifier
    EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                   savedir=str(MODEL_DIR / "ecapa"),
                                   run_opts={"device": "cpu"})

    print("silero-vad")
    from silero_vad import load_silero_vad
    load_silero_vad(onnx=True)

    print("piper voices")
    for name in sorted(set(PIPER_VOICES.values()) | set(ENROLMENT_VOICES) | {SPOOF_VOICE}):
        rel = PIPER_PATHS.get(name)
        if not rel:
            print(f"  skip  {name}: no download path registered")
            continue
        fetch(f"{PIPER_BASE}/{rel}", MODEL_DIR / "piper" / f"{name}.onnx")
        fetch(f"{PIPER_BASE}/{rel}.json", MODEL_DIR / "piper" / f"{name}.onnx.json")

    print("kokoro-82m (primary voice)")
    kdir = MODEL_DIR / "kokoro"
    for name, url in (
        ("kokoro-v1.0.onnx", f"{KOKORO_BASE}/kokoro-v1.0.onnx"),
        ("voices-v1.0.bin", f"{KOKORO_BASE}/voices-v1.0.bin"),
    ):
        fetch(url, kdir / name)

    print("\nall models present under", MODEL_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
