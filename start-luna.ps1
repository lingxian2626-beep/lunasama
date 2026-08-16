# Luna 桌宠一键启动脚本（PowerShell）
# 用法: powershell -ExecutionPolicy Bypass -File start-luna.ps1
$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PY = "python"
$LOG = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $LOG | Out-Null

Write-Host "=== 启动 Luna 桌宠（中文 + 滴答清单提醒 + 露娜音色）===" -ForegroundColor Cyan

# 1) TTS 服务 :9880（露娜音色 GPT-SoVITS）
$tts = Start-Process -FilePath $PY -ArgumentList "$ROOT\backend\luna_tts.py" -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $LOG "tts.out.log") `
  -RedirectStandardError (Join-Path $LOG "tts.err.log") -PassThru
Write-Host "[1/3] 露娜音色 TTS 已启动 (pid $($tts.Id)) :9880（加载模型约 1 分钟）" -ForegroundColor Green

# 2) LLM 后端 :8000
$llm = Start-Process -FilePath $PY -ArgumentList "$ROOT\backend\api.py" -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $LOG "llm.out.log") `
  -RedirectStandardError (Join-Path $LOG "llm.err.log") -PassThru
Write-Host "[2/3] LLM 后端已启动 (pid $($llm.Id)) :8000（加载约 5 秒）" -ForegroundColor Green

# 3) 桌宠本体
$exe = Join-Path $ROOT "app\luna\dist\luna_sama.exe"
if (Test-Path $exe) {
    $pet = Start-Process -FilePath $exe -PassThru
    Write-Host "[3/3] 桌宠已启动 (pid $($pet.Id))" -ForegroundColor Green
} else {
    Write-Host "[3/3] 未找到 $exe，请先编译" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "启动完成！日志位于 $LOG\" -ForegroundColor Cyan
Write-Host "提示: 桌宠每 90 秒检查滴答清单，按当天任务和习惯时间点提醒，露娜音色播报。" -ForegroundColor Cyan