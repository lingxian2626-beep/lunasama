#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Luna 桌宠 TTS 后端（edge-tts 中文语音）
兼容原 GPT-SoVITS 的 /speak 接口：
  GET /speak?text=...&text_lang=zh  -> { "ok":true, "sample_rate":N, "url":"/audio/xxx.mp3", "path":"..." }
"""
import os
import sys
import time
import uuid
import asyncio
import threading
from pathlib import Path

import edge_tts
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
import uvicorn

OUT_DIR = os.environ.get("TTS_OUT_DIR", "E:/dsh/luna-sama/out_audio")
VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
RATE = os.environ.get("TTS_RATE", "+0%")

os.makedirs(OUT_DIR, exist_ok=True)
app = FastAPI(title="Luna TTS API (edge-tts)")
app.mount("/audio", StaticFiles(directory=OUT_DIR), name="audio")

_sem = threading.Semaphore(1)  # 串行合成，避免并发冲突


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/speak")
def speak(
    text: str = Query(..., description="要合成的文本"),
    text_lang: str = Query(None, description="语言（兼容参数，忽略）"),
    speed: float = Query(1.0, description="语速倍率（0.5~2.0）"),
    basename: str = Query(None, description="输出文件名前缀"),
):
    if not text.strip():
        return {"ok": False, "url": "", "path": "", "sample_rate": 0}

    stem = (basename or "luna").strip() or "luna"
    fname = f"{stem}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.mp3"
    out_path = os.path.join(OUT_DIR, fname)

    rate_str = RATE
    if abs(speed - 1.0) > 0.01:
        pct = int(round((speed - 1.0) * 100))
        rate_str = f"{pct:+d}%"

    async def _synth():
        tts = edge_tts.Communicate(text, voice=VOICE, rate=rate_str)
        await tts.save(out_path)

    try:
        with _sem:
            asyncio.run(_synth())
    except Exception as e:
        return {"ok": False, "url": "", "path": "", "sample_rate": 0,
                "error": str(e)}

    return {
        "ok": True,
        "sample_rate": 24000,
        "url": f"/audio/{fname}",
        "path": os.path.abspath(out_path),
        "text_lang": text_lang or "zh",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9880)
