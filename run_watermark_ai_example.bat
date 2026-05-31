@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "WATERMARK_REMOVER_AI_DIR=%ROOT%\external\WatermarkRemover-AI"
set "WATERMARK_REMOVER_AI_PYTHON=%CONDA_ENVS_ROOT%\watermark-ai\python.exe"
set "PATH=D:\AI\ffmpeg\bin;%PATH%"
cd /d "%ROOT%"

REM High-quality image mode:
REM "%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli image "%ROOT%\input\sample.png" --engine external-ai --output "%ROOT%\output\sample_ai_clean.png"

REM High-quality video mode:
REM "%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli video "%ROOT%\input\sample.mp4" --engine external-ai --output "%ROOT%\output\sample_ai_clean.mp4" --ai-detection-skip 3 --ai-fade-in 0.5 --ai-fade-out 0.5

REM High-quality platform cleanup after download:
REM set PARSE_VIDEO_BASE_URL=http://127.0.0.1:8000
REM "%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli link "https://weibo.com/tv/show/1034:..." --download --clean-platform-watermark --clean-engine external-ai
