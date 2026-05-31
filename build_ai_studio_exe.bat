@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "PYTHON=%CONDA_ENVS_ROOT%\comfyui\python.exe"
cd /d "%ROOT%"
if not exist "%PYTHON%" (
  echo Missing Python: %PYTHON%
  exit /b 1
)

"%PYTHON%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
  echo Installing PyInstaller into the local ComfyUI Python environment...
  "%PYTHON%" -m pip install pyinstaller
  if errorlevel 1 exit /b 1
)

"%PYTHON%" -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo Installing pywebview into the local ComfyUI Python environment...
  "%PYTHON%" -m pip install pywebview
  if errorlevel 1 exit /b 1
)

echo Building ComfyAI Studio launcher...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name ComfyAI-Studio-Launcher --collect-submodules webview --collect-submodules clr_loader --collect-submodules pythonnet --add-binary "%CONDA_ENVS_ROOT%\comfyui\Library\bin\libssl-3-x64.dll;." --add-binary "%CONDA_ENVS_ROOT%\comfyui\Library\bin\libcrypto-3-x64.dll;." ai_studio_launcher.py
if errorlevel 1 exit /b 1

copy /Y "%ROOT%\dist\ComfyAI-Studio-Launcher.exe" "%ROOT%\ComfyAI-Studio-Launcher.exe" >nul
if errorlevel 1 (
  echo Failed to copy launcher to %ROOT%\ComfyAI-Studio-Launcher.exe
  echo Close the launcher if it is running, then run this script again.
  exit /b 1
)

echo.
echo Done:
echo   %ROOT%\dist\ComfyAI-Studio-Launcher.exe
echo   %ROOT%\ComfyAI-Studio-Launcher.exe
echo.
echo It reuses conda envs under %CONDA_ENVS_ROOT%.
