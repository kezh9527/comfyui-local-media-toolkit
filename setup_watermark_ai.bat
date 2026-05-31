@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ROOT set "CONDA_ROOT=D:\Miniconda3"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "CONDA_ENVS_PATH=%CONDA_ENVS_ROOT%"
set "AI_DIR=%ROOT%\external\WatermarkRemover-AI"
set "AI_ZIP=%ROOT%\external\WatermarkRemover-AI.zip"
set "CONDA=%CONDA_ROOT%\Scripts\conda.exe"
set "AI_ENV=watermark-ai"
set "AI_PY=%CONDA_ENVS_ROOT%\watermark-ai\python.exe"
cd /d "%ROOT%"

if not exist "%ROOT%\external" mkdir "%ROOT%\external"

if not exist "%AI_DIR%\remwm.py" (
  echo Downloading WatermarkRemover-AI...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/D-Ogi/WatermarkRemover-AI/archive/refs/heads/main.zip' -OutFile '%AI_ZIP%'; if (Test-Path '%AI_DIR%') { Remove-Item -LiteralPath '%AI_DIR%' -Recurse -Force }; Expand-Archive -Path '%AI_ZIP%' -DestinationPath '%ROOT%\external' -Force; Move-Item -LiteralPath '%ROOT%\external\WatermarkRemover-AI-main' -Destination '%AI_DIR%'; Remove-Item -LiteralPath '%AI_ZIP%' -Force"
  if errorlevel 1 exit /b 1
)

if not exist "%CONDA%" (
  echo Missing conda: %CONDA%
  exit /b 1
)

"%CONDA%" env list | findstr /C:"%AI_ENV%" >nul
if errorlevel 1 (
  echo Creating conda AI env %AI_ENV%...
  "%CONDA%" create -n %AI_ENV% python=3.10 -y
  if errorlevel 1 exit /b 1
)

echo Installing AI dependencies. This can take a while...
"%AI_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1

"%AI_PY%" -m pip install -r "%ROOT%\watermark_tools\requirements-watermark-ai.txt" --use-deprecated=legacy-resolver
if errorlevel 1 exit /b 1

"%AI_PY%" -m pip install --upgrade iopaint --no-deps
if errorlevel 1 exit /b 1

"%AI_PY%" -m pip install "safetensors>=0.8.0rc0" "typer>=0.20,<0.26" "typer-config==1.4.0"
if errorlevel 1 exit /b 1

echo.
echo WatermarkRemover-AI is installed.
echo Directory: %AI_DIR%
echo Conda env: %AI_ENV%
echo Python:    %AI_PY%
echo.
echo Optional environment variables:
echo   set WATERMARK_REMOVER_AI_DIR=%AI_DIR%
echo   set WATERMARK_REMOVER_AI_PYTHON=%AI_PY%
echo.
echo First high-quality run may download Florence-2 and LaMA models.
