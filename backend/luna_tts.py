# -*- coding: utf-8 -*-
"""
露娜音色 TTS 服务（GPT-SoVITS 跨语言克隆）
- 参考音频：v_lun0022.ogg（露娜原声，日语）
- 参考文本：中文（跨语言：露娜音色 + 中文发音）
- 提供与原 edge-tts 相同的 /speak 接口（9880 端口兼容）
"""
import os
import sys
import time
import uuid
import threading

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
import uvicorn

# 加入 gsv 源码路径（gsv-src 在项目根目录，与 backend 同级）
BASE = os.path.dirname(os.path.abspath(__file__))
GSV_ROOT = os.path.join(os.path.dirname(BASE), "gsv-src")
sys.path.insert(0, GSV_ROOT)
# sv.py 依赖 os.getcwd() 定位权重，把工作目录切到 gsv-src
os.chdir(GSV_ROOT)

from gsv.api import make_app
from gsv.config_infer import Config
from gsv.service import TTSService

OUT_DIR = os.environ.get("TTS_OUT_DIR", "E:/dsh/luna-sama/out_audio")
os.makedirs(OUT_DIR, exist_ok=True)

# ---- 模型路径（相对项目根） ----
REF_WAV = os.environ.get("LUNA_REF_WAV", os.path.join(GSV_ROOT, "gsv", "extracted_ogg", "v_lun0022_4s.wav"))
SOVITS = os.environ.get("LUNA_SOVITS", os.path.join(GSV_ROOT, "gsv", "weights", "xxx_sovits_e24_s456.pth"))
GPT = os.environ.get("LUNA_GPT", os.path.join(GSV_ROOT, "gsv", "weights", "xxx-gpt-e50.ckpt"))
HUBERT = os.environ.get("LUNA_HUBERT", os.path.join(GSV_ROOT, "gsv", "pretrained_models", "chinese-hubert-base"))
BERT = os.environ.get("LUNA_BERT", os.path.join(GSV_ROOT, "gsv", "pretrained_models", "chinese-roberta-wwm-ext-large"))

# 参考文本：短中文句（跨语言克隆用，音色取自参考音频）
REF_TEXT = os.environ.get("LUNA_REF_TEXT", "你好呀，今天也要加油哦")
REF_LANG = "zh"

print("=== 露娜音色 TTS（GPT-SoVITS）===", flush=True)
print(f"参考音频: {REF_WAV} ({os.path.getsize(REF_WAV)} bytes)", flush=True)
print("加载模型中…", flush=True)

import torch
is_half = torch.cuda.is_available()
device = "cuda" if torch.cuda.is_available() else "cpu"

# 用 gsv 的 TTSService 直接加载
svc = TTSService(device, is_half, HUBERT, BERT, GPT, SOVITS)
print("模型加载完成", flush=True)

app = FastAPI(title="Luna TTS (GPT-SoVITS 露娜音色)")
app.mount("/audio", StaticFiles(directory=OUT_DIR), name="audio")

_sem = threading.Semaphore(1)  # GPU 推理串行


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/speak")
def speak(
    text: str = Query(..., description="要合成的文本"),
    text_lang: str = Query(None, description="语言（zh/en/ja…，默认 zh）"),
    speed: float = Query(0.7, description="语速（0.5~1.5）"),
    basename: str = Query(None, description="输出文件名前缀"),
):
    if not text.strip():
        return {"ok": False, "url": "", "path": "", "sample_rate": 0}
    lang = (text_lang or "zh").strip()
    stem = (basename or "luna").strip() or "luna"
    fname = f"{stem}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.wav"
    out_path = os.path.join(OUT_DIR, fname)

    try:
        with _sem:
            sr, wav = svc.synth(
                REF_WAV, REF_TEXT, REF_LANG,
                text, lang,
                top_k=15, top_p=0.6, temperature=0.6,
                speed=speed, sample_steps=32,
            )
        sf.write(out_path, wav, sr)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "url": "", "path": "", "sample_rate": 0, "error": str(e)}

    return {
        "ok": True,
        "sample_rate": sr,
        "url": f"/audio/{fname}",
        "path": os.path.abspath(out_path),
        "text_lang": lang,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9880)
