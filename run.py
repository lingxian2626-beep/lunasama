# -*- coding: utf-8 -*-
"""
启动 Luna 桌宠全栈：
  1. LLM 后端（:8000）—— Qwen3 中文 + 滴答清单提醒
  2. TTS 后端（:9880）—— edge-tts 中文语音
  3. 桌宠本体（luna_sama.exe）
"""
import os
import sys
import time
import subprocess
import signal

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

procs = []
log_dir = os.path.join(ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)


def start(name, cmd, env=None):
    logf = open(os.path.join(log_dir, name + ".log"), "a", encoding="utf-8")
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=e,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    procs.append((name, p, logf))
    print(f"[start] {name} pid={p.pid}")
    return p


def wait_port(port, timeout=180):
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
            return True
        except Exception:
            time.sleep(3)
    return False


def main():
    env = {
        "MODEL_DIR": os.environ.get("MODEL_DIR", "E:/dsh/luna-models/Qwen/Qwen3-4B-Instruct-2507"),
        "TICKTICK_TOKEN": os.environ.get("TICKTICK_TOKEN", "dp_cd390e58e4c74119bc195792edc7ed90"),
        "TTS_OUT_DIR": os.path.join(ROOT, "out_audio"),
    }

    print("=== 启动 Luna 桌宠 ===")
    print("1) TTS 服务 :9880")
    start("tts", [PY, os.path.join(ROOT, "backend", "tts.py")], env)
    ok = wait_port(9880, timeout=60)
    print("   TTS 就绪" if ok else "   TTS 未就绪（继续尝试）")

    print("2) LLM 后端 :8000（首次加载模型可能需几分钟）")
    start("llm", [PY, os.path.join(ROOT, "backend", "api.py")], env)

    print("3) 等待 LLM 后端…")
    ok = wait_port(8000, timeout=900)
    if not ok:
        print("   LLM 后端未在 15 分钟内就绪，请查看 logs/llm.log")
        # 仍然尝试启动桌宠（对话不可用但提醒仍可走 /reminders？不行，reminders 也在 LLM 后端）
        # 这里直接退出码提示
    else:
        print("   LLM 后端就绪")

    exe = os.path.join(ROOT, "app", "luna", "dist", "luna_sama.exe")
    if os.path.exists(exe):
        print("4) 启动桌宠")
        start("pet", [exe])
    else:
        print(f"   未找到 {exe}，请先编译")

    print("=== 全部启动完成。按 Ctrl+C 退出 ===")
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        for name, p, f in reversed(procs):
            print(f"[stop] {name}")
            try:
                p.terminate()
            except Exception:
                pass
            f.close()


if __name__ == "__main__":
    main()
