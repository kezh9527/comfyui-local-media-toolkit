ComfyUI + InstantID/inpaint CPU setup

Use only with images you own or have permission to edit. Obtain the informed
consent of depicted people. See docs/RESPONSIBLE_USE.md.

Start:
  Double-click start_comfyui_cpu.bat from the repository root.
  Open http://127.0.0.1:8188

Workflow:
  Load workflows\instantid_inpaint_cpu_min.json in ComfyUI.

Input files expected in input\:
  target_pose.png  = image 1, the composition/pose/base image to preserve
  identity.png     = image 2, the person identity reference
  head_mask.png    = black/white mask, white where ComfyUI should repaint

Mask guidance:
  Use white over face, hair, ears, neck edge, and head outline that may need
  repainting. Keep clothing, body, and background black if you want to
  preserve image 1.

CPU minimum runnable parameters:
  Resolution: start with image 1 resized to about 512-640 px on the long side.
  Steps: 4
  CFG: 1.0-1.5
  Denoise: 0.50-0.65
  InstantID ip_weight: 0.55-0.70
  InstantID cn_strength: 0.65-0.85
  Sampler/scheduler: euler + sgm_uniform

Quality tuning:
  More natural: lower ip_weight to 0.50-0.60, denoise 0.50-0.58.
  More similar: raise ip_weight to 0.70-0.85, denoise 0.60-0.72.
  If the face is over-burned or waxy: lower CFG and ip_weight first.
  If pose drifts: raise cn_strength or make head_mask tighter.

Model files to download separately:
  models\checkpoints\sdxl_lightning_4step.safetensors
  models\instantid\ip-adapter.bin
  models\controlnet\instantid_controlnet.safetensors
  models\insightface\models\antelopev2\
