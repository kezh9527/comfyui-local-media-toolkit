@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "PATH=D:\AI\ffmpeg\bin;%CONDA_ENVS_ROOT%\comfyui\Library\cmd;%CONDA_ENVS_ROOT%\comfyui\Library\bin;%PATH%"
cd /d "%ROOT%"

REM Image example:
REM "%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli image "%ROOT%\input\sample.png" --box 20,20,220,80 --output "%ROOT%\output\sample_clean.png"

REM Video example:
REM "%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli video "%ROOT%\input\sample.mp4" --box 20,20,220,80 --output "%ROOT%\output\sample_clean.mp4" --limit-frames 10

REM Platform link example, requires PARSE_VIDEO_BASE_URL:
REM set PARSE_VIDEO_BASE_URL=http://127.0.0.1:8000
REM "%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli link "https://..." --download
