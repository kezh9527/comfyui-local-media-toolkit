@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "PYTHON=%CONDA_ENVS_ROOT%\comfyui\python.exe"
set "PATH=%CONDA_ENVS_ROOT%\comfyui\Library\cmd;%CONDA_ENVS_ROOT%\comfyui\Library\bin;D:\AI\ffmpeg\bin;%PATH%"
cd /d "%ROOT%"
"%PYTHON%" main.py --cpu --listen 127.0.0.1 --port 8188
