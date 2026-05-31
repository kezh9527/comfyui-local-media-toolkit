@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "PARSE_EXE=%CONDA_ENVS_ROOT%\parse-video\Scripts\parse-video-py.exe"
cd /d "%ROOT%"

if not exist "%PARSE_EXE%" (
  echo parse-video-py is not installed. Run %ROOT%\setup_parse_video_py.bat first.
  exit /b 1
)

"%PARSE_EXE%" serve --port 8000
