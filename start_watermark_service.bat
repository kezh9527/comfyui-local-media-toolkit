@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "WATERMARK_REMOVER_AI_DIR=%ROOT%\external\WatermarkRemover-AI"
set "WATERMARK_REMOVER_AI_PYTHON=%CONDA_ENVS_ROOT%\watermark-ai\python.exe"
set "PATH=D:\AI\ffmpeg\bin;%CONDA_ENVS_ROOT%\comfyui\Library\cmd;%CONDA_ENVS_ROOT%\comfyui\Library\bin;%CONDA_ENVS_ROOT%\watermark-ai\Library\bin;%PATH%"
if "%PARSE_VIDEO_BASE_URL%"=="" set PARSE_VIDEO_BASE_URL=http://127.0.0.1:8000
cd /d "%ROOT%"
"%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli service --host 127.0.0.1 --port 8198
