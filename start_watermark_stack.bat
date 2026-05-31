@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "PARSE_VIDEO_BASE_URL=http://127.0.0.1:8000"
set "WATERMARK_REMOVER_AI_DIR=%ROOT%\external\WatermarkRemover-AI"
set "WATERMARK_REMOVER_AI_PYTHON=%CONDA_ENVS_ROOT%\watermark-ai\python.exe"
set "PATH=D:\AI\ffmpeg\bin;%CONDA_ENVS_ROOT%\comfyui\Library\cmd;%CONDA_ENVS_ROOT%\comfyui\Library\bin;%CONDA_ENVS_ROOT%\parse-video\Library\bin;%CONDA_ENVS_ROOT%\watermark-ai\Library\bin;%PATH%"
cd /d "%ROOT%"

if not exist "%CONDA_ENVS_ROOT%\parse-video\Scripts\parse-video-py.exe" (
  echo parse-video-py is not installed. Run %ROOT%\setup_parse_video_py.bat first.
  exit /b 1
)

start "parse-video-py" /min "%CONDA_ENVS_ROOT%\parse-video\Scripts\parse-video-py.exe" serve --port 8000
echo Waiting for parse-video-py on %PARSE_VIDEO_BASE_URL% ...
timeout /t 5 /nobreak >nul

"%CONDA_ENVS_ROOT%\comfyui\python.exe" -m watermark_tools.cli service --host 127.0.0.1 --port 8198
