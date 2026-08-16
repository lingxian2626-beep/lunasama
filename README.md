# Luna 桌宠（中文版 + 滴答清单提醒 + 露娜原声音色）

基于 [annali07/luna-sama](https://github.com/annali07/luna-sama) 改造：
- **中文输入输出**：LLM 后端为 Qwen2.5-1.5B-Instruct（4bit 量化，推理约 1 秒），露娜用中文说话
- **露娜原声音色**：GPT-SoVITS 加载作者训练的露娜音色权重（v2ProPlus + SV 声纹），
  参考音频用露娜原声片段，跨语言合成**露娜音色的中文语音**（提醒与对话播报）
- **滴答清单（TickTick）提醒**：接入官方 Open API（中国版 api.dida365.com），
  每 90 秒自动检查：
  - **当天到期任务**：dueDate 为今天的未完成任务，当天提醒一次
  - **习惯按时间点提醒**：如「早起 07:00」「吃早餐 08:00」「喝水 09:00/12:00/18:00/20:00」
    「Exercise 15:00」「早睡 22:00」，每个时间点到点提醒一次（当天补提醒错过的点），不会重复轰炸

## 目录结构

```
luna-sama/
├── backend/
│   ├── api.py            # LLM 后端（FastAPI :8000，中文 + 滴答清单集成）
│   ├── luna_tts.py       # 露娜音色 TTS（FastAPI :9880，GPT-SoVITS）
│   ├── tts.py            # （备用）edge-tts 中文语音
│   ├── ticktick.py       # 滴答清单客户端（api.dida365.com）+ 提醒调度
│   └── reminder_state.json  # 已提醒状态（自动管理，可删除重置）
├── gsv-src/              # GPT-SoVITS 推理源码 + 露娜音色权重
│   └── gsv/
│       ├── weights/      # xxx-gpt-e50.ckpt + xxx_sovits_e24_s456.pth（露娜音色）
│       ├── pretrained_models/  # hubert + bert + SV 声纹模型
│       └── extracted_ogg/      # v_lun0022.ogg 露娜原声参考音频
├── app/luna/             # 桌宠 C++ 源码（Qt 6.9.1）
│   └── dist/             # 编译产物（luna_sama.exe + Qt DLL + assets）
├── out_audio/            # TTS 生成的音频
├── logs/                 # 运行日志
├── start-luna.ps1        # 一键启动（PowerShell）
└── run.py                # 一键启动（Python）
```

## 使用

```powershell
powershell -ExecutionPolicy Bypass -File start-luna.ps1
```

启动后：
1. LLM 后端加载模型约 5 秒；露娜音色 TTS 加载约 1 分钟（GPT-SoVITS 4 个模型）
2. 桌宠出现在屏幕右下角，输入框输入中文即可对话（约 1-2 秒回复）
3. 启动 15 秒后开始每 90 秒检查滴答清单，按当天任务和习惯时间点提醒，**露娜音色播报**

## 露娜音色说明

- 音色来自作者训练的 GPT-SoVITS 权重（`xxx-gpt-e50.ckpt` + `xxx_sovits_e24_s456.pth`，v2ProPlus）
- 参考音频 `v_lun0022_4s.wav`（从露娜原声 9.1 秒裁剪 4 秒，跨语言克隆用中文参考文本）
- 合成耗时约 1-3 秒/句；显卡需 ≥6GB 显存（hubert+bert+gpt+sovits+sv ≈ 4.4GB，与 LLM 共存）
- 已知修复：v2ProPlus 权重文件头 b"06" 被误判为 v2 的问题已在 `loaders.py` 修正

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `TICKTICK_TOKEN` | `dp_...` | 滴答清单 Open API token（在滴答清单开放平台申请） |
| `MODEL_DIR` | `E:/dsh/luna-models/models/Qwen--Qwen2.5-1.5B-Instruct/snapshots/master` | LLM 模型目录 |
| `LUNA_REF_WAV` | `gsv-src/gsv/extracted_ogg/v_lun0022_4s.wav` | 露娜参考音频 |
| `LOAD_4BIT` | `1` | 4bit 量化加载 LLM |

## 提醒规则说明

- **任务**：只提醒「今天到期」的未完成任务，当天提醒一次
- **习惯**：`GET /open/v1/habit` 获取每个习惯的 `reminders` 时间点数组，到点提醒；
  状态保存在 `backend/reminder_state.json`，删除该文件可重置当天提醒
- 若想调提醒频率：改 `app/luna/ui/MainWindow.cpp` 里 `reminderTimer_->setInterval(90'000)` 并重编译

## 从源码构建桌宠（可选）

需要 Qt 6.9.1 + MinGW 13.1：

```powershell
$env:Path = "E:\Qt\Tools\mingw1310_64\bin;E:\Qt\6.9.1\mingw_64\bin;E:\Qt\Tools\CMake_64\bin;$env:Path"
cmake -S app/luna -B app/luna/build -G "MinGW Makefiles" `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_PREFIX_PATH="E:/Qt/6.9.1/mingw_64"
cmake --build app/luna/build --config Release -j
# 部署
windeployqt app/luna/build/luna_sama.exe --release
```

## 滴答清单 API

使用官方 Open API（中国版）：
- 项目列表：`GET https://api.dida365.com/open/v1/project`
- 项目数据：`GET https://api.dida365.com/open/v1/project/{id}/data`
- 认证：`Authorization: Bearer <token>`

## 常见问题

- **LLM 后端启动慢**：首次加载 8GB 模型需要几分钟，属正常现象
- **无 GPU**：可设置 `LOAD_4BIT=0`，但会非常慢，建议有 NVIDIA GPU（8GB 显存即可）
- **提醒不响**：检查 logs/llm.log 中滴答清单初始化是否成功、token 是否有效
