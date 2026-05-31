@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined CONDA_ENVS_ROOT set "CONDA_ENVS_ROOT=D:\conda_envs"
set "PATH=D:\AI\ffmpeg\bin;%CONDA_ENVS_ROOT%\comfyui\Library\cmd;%CONDA_ENVS_ROOT%\comfyui\Library\bin;%PATH%"
cd /d "%ROOT%"

REM Replace these two paths with your files.
set "TARGET_VIDEO=%ROOT%\input\target_video.mp4"
set "IDENTITY_IMAGE=%ROOT%\input\identity.png"

"%CONDA_ENVS_ROOT%\comfyui\python.exe" "%ROOT%\video_faceswap_pipeline.py" ^
  --video "%TARGET_VIDEO%" ^
  --identity "%IDENTITY_IMAGE%" ^
  --out "%ROOT%\output\video_faceswap_result.mp4" ^
  --fps 2 ^
  --max-side 640 ^
  --steps 4 ^
  --cfg 1.2 ^
  --denoise 0.56 ^
  --ip-weight 0.62 ^
  --cn-strength 0.78
