# -*- coding: utf-8 -*-
"""将下载的分片组装到 modelscope 缓存目录（幂等）"""
import os, shutil, glob

MASTER = "E:/dsh/luna-models/models/Qwen--Qwen3-4B-Instruct-2507/snapshots/master"
DL = "E:/dsh/luna-models/dl"

os.makedirs(MASTER, exist_ok=True)

# 1) 复制小文件（若 master 缺失）
for f in glob.glob(os.path.join(DL, "*")):
    name = os.path.basename(f)
    if name.startswith("model-") or name == "shard3.safetensors":
        continue
    dst = os.path.join(MASTER, name)
    if not os.path.exists(dst):
        shutil.copy2(f, dst)
        print("copy", name)

# 2) 复制分片（跳过 .incomplete/.aria2）
for shard in ["model-00001-of-00003.safetensors",
              "model-00002-of-00003.safetensors",
              "model-00003-of-00003.safetensors"]:
    src = os.path.join(DL, shard)
    dst = os.path.join(MASTER, shard)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print("copy shard", shard)

# 3) 清理 aria2 残留
for f in glob.glob(os.path.join(MASTER, "*.aria2")) + glob.glob(os.path.join(MASTER, "*.incomplete")):
    os.remove(f)
    print("remove", os.path.basename(f))

# 4) 校验
total = 0
for f in glob.glob(os.path.join(MASTER, "*.safetensors")):
    sz = os.path.getsize(f)
    total += sz
    print(f"{os.path.basename(f)}: {sz/1e9:.2f} GB")
print(f"TOTAL: {total/1e9:.2f} GB (期望约 8.05 GB)")
