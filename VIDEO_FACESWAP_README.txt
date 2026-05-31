Video face replacement pipeline

Use only with videos and identity images you own or have permission to edit.
Obtain the informed consent of depicted people. See docs/RESPONSIBLE_USE.md.

What it does:
  1. Extracts frames from a target video.
  2. Detects the target face on each frame with InsightFace.
  3. Builds a soft head/face mask for each frame.
  4. Sends each frame to local ComfyUI InstantID inpaint.
  5. Reassembles processed frames into MP4 and maps the original audio back.

Usage:
  Run run_video_faceswap_example.bat from the repository root after adjusting
  the TARGET_VIDEO and IDENTITY_IMAGE values if needed.

  Equivalent command:
    %CONDA_ENVS_ROOT%\comfyui\python.exe video_faceswap_pipeline.py ^
      --video input\target_video.mp4 ^
      --identity input\identity.png ^
      --out output\video_faceswap_result.mp4 ^
      --fps 2 ^
      --max-side 640

CPU preview defaults:
  --fps 2
  --max-side 640
  --steps 4
  --cfg 1.2
  --denoise 0.56
  --ip-weight 0.62
  --cn-strength 0.78

Naturalness tuning:
  More natural / less pasted:
    --denoise 0.48 to 0.56
    --ip-weight 0.50 to 0.62
    --mask-feather 24 to 36

  More identity similarity:
    --denoise 0.60 to 0.70
    --ip-weight 0.70 to 0.85

  If the face flickers:
    Keep the seed stable, lower denoise, lower fps for a preview, or process
    with a GPU at higher FPS. Frame-by-frame SDXL has no temporal model, so
    some flicker is expected.

Output:
  output\video_faceswap_result.mp4

On CPU, a full video can take a long time. Test first with --limit-frames 3
or --fps 1.
