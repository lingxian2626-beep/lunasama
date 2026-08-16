#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Luna 桌宠 LLM 后端（中文版 + 滴答清单集成）

- POST /chat     { "user": "..." }  -> { "emotion": "<E:...>", "sentence": "..." }
- GET  /reminders                   -> { "count": N, "text": "...", "items": [...] }
- GET  /health                      -> { "ok": true }

模型：Qwen2.5-1.5B-Instruct（小模型，推理快；从 ModelScope 下载，路径由 MODEL_DIR 指定）
"""
import os
import sys
import torch
import threading
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import (
    AutoTokenizer, AutoModelForCausalLM,
    BitsAndBytesConfig, TextIteratorStreamer
)
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticktick

# ------------ Config ------------
MODEL_DIR = os.environ.get("MODEL_DIR", "E:/dsh/luna-models/models/Qwen--Qwen2.5-1.5B-Instruct/snapshots/master")
LOAD_4BIT = os.environ.get("LOAD_4BIT", "1") == "1"

SYSTEM_PROMPT = (
    "你是【露娜】，一位住在用户电脑里的元气桌面宠物少女，性格温柔、调皮又有点小傲娇。"
    "始终用简体中文和用户对话，口语化、简短（一两句话），带一点卖萌语气词（如「~」「喵」「哦」「呀」）。"
    "每次回答第一行单独输出一个情绪标签（<E:smile>、<E:serious>、<E:surprised>、"
    "<E:sad>、<E:angry>、<E:thinking>、<E:smirk>、<E:embarrassed>、<E:skeptical>、<E:resigned>、<E:dislike>），"
    "第二行才是对用户说的话，不要输出其他内容。"
    "如果下面提供了【今日待办】，可以顺带提醒用户，用撒娇或关心的口吻。"
)

# ------------ Model Load ------------
def load_model_and_tokenizer(model_dir, load_in_4bit=True):
    tok = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True, use_fast=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    if load_in_4bit:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_dir,
            device_map={"": 0},   # 强制 GPU（1.5B 4bit 仅 ~1.2GB，与 TTS 共存）
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            quantization_config=bnb,
            trust_remote_code=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_dir,
            device_map={"": 0},
            torch_dtype=torch.float16,
            attn_implementation="sdpa",
            trust_remote_code=True,
        )
    model.eval()
    return model, tok


def format_inputs(tokenizer, messages):
    enc = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_tensors="pt", enable_thinking=False
    )
    # transformers>=5 返回 BatchEncoding，兼容旧版直接返回 tensor
    if hasattr(enc, "input_ids"):
        return enc.input_ids
    return enc


print("Loading model…", file=sys.stderr, flush=True)
model, tok = load_model_and_tokenizer(MODEL_DIR, load_in_4bit=LOAD_4BIT)
print("Model loaded.", file=sys.stderr, flush=True)

# 启动滴答清单后台刷新
ticktick.start_reminder_loop(interval=180)
try:
    ticktick.refresh(force=True)
    _t = ticktick._cache.get("tasks", [])
    print(f"[ticktick] initial: {len(_t)} open tasks", file=sys.stderr, flush=True)
except Exception as e:
    print(f"[ticktick] init failed: {e}", file=sys.stderr, flush=True)

# ------------ API Server ------------
app = FastAPI(title="Luna LLM API (zh)")

class ChatRequest(BaseModel):
    user: str

class ChatResponse(BaseModel):
    emotion: str
    sentence: str

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/reminders")
def reminders():
    return ticktick.get_reminders()

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # 简要注入今日待办（最多 5 条，避免 prompt 过长拖慢推理）
    reminders = ticktick.get_reminders()
    sys_msg = SYSTEM_PROMPT
    today_items = reminders.get("items", [])
    due_today = reminders.get("due_today", 0)
    if due_today or today_items:
        brief = []
        for it in today_items[:5]:
            brief.append(it["text"])
        if due_today > len(today_items):
            brief.append(f"还有 {due_today - len([i for i in today_items if i['kind']=='task'])} 个任务今天到期")
        sys_msg += "\n\n【今日待办】\n" + "\n".join(brief)

    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": req.user},
    ]
    input_ids = format_inputs(tok, messages).to(model.device)

    eos_id = tok.convert_tokens_to_ids("<|im_end|>")
    gen_kwargs = dict(
        max_new_tokens=80,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.05,
        eos_token_id=[tok.eos_token_id, eos_id],
        pad_token_id=tok.pad_token_id,
    )

    # 非流式生成（简单可靠；1.5B 模型生成仅需 1-2 秒）
    with torch.no_grad():
        out = model.generate(
            inputs=input_ids,
            **{k: v for k, v in gen_kwargs.items() if v is not None}
        )
    text = tok.decode(out[0][input_ids.shape[1]:], skip_special_tokens=True).strip()

    lines = [ln for ln in text.split("\n") if ln.strip()]
    emotion, sentence = "", ""
    if len(lines) >= 1:
        first = lines[0].strip()
        # 第一行可能形如 "<E:smile> 台词…"（模型把情绪和台词写在同一行）
        import re
        m = re.match(r"^(<E:[^>]+>)\s*(.*)$", first)
        if m:
            emotion = m.group(1)
            rest = m.group(2).strip()
            if rest:
                sentence = rest
            elif len(lines) >= 2:
                sentence = lines[1].strip()
        elif first.startswith("<E:"):
            emotion = first
            if len(lines) >= 2:
                sentence = lines[1].strip()
        else:
            emotion = "<E:smile>"
            sentence = first

    if not sentence:
        sentence = "嗯嗯，我在听你说哦~"

    return ChatResponse(emotion=emotion, sentence=sentence)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
