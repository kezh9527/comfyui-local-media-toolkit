@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ROOT set "CONDA_ROOT=D:\Miniconda3"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "CONDA_ENVS_PATH=%CONDA_ENVS_ROOT%"
set "CONDA=%CONDA_ROOT%\Scripts\conda.exe"
set "ENV_NAME=parse-video"
set "ENV_PY=%CONDA_ENVS_ROOT%\parse-video\python.exe"
cd /d "%ROOT%"

if not exist "%CONDA%" (
  echo Missing conda: %CONDA%
  exit /b 1
)

"%CONDA%" env list | findstr /C:"%ENV_NAME%" >nul
if errorlevel 1 (
  "%CONDA%" create -n %ENV_NAME% python=3.10 -y
  if errorlevel 1 exit /b 1
)

"%ENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1

"%ENV_PY%" -m pip install "parse-video-py[all] @ https://github.com/wujunwei928/parse-video-py/archive/refs/heads/master.zip"
if errorlevel 1 exit /b 1

echo.
echo parse-video-py installed in conda env: %ENV_NAME%
echo Start it with: %ROOT%\start_parse_video_py.bat
