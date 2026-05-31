# Contributing

Thank you for contributing to ComfyAI Studio Local Toolkit. This repository is a
community-maintained derivative of ComfyUI. Please route changes to the right
project so both maintainers and users get a clear signal.

## Scope

Open an issue or pull request here for:

- `ai_studio_launcher.py`
- `watermark_tools/`
- `video_faceswap_pipeline.py`
- Windows setup and start helpers
- Documentation for this derivative workspace

For an issue reproducible in unmodified ComfyUI, use the
[upstream ComfyUI issue tracker](https://github.com/comfyanonymous/ComfyUI/issues).
For an upstream contribution, follow the
[ComfyUI contribution guide](https://github.com/comfyanonymous/ComfyUI/wiki/How-to-Contribute-Code).

## Pull Requests

Keep changes focused. Explain the problem, the behavior change, and how you
tested it. Do not commit model weights, generated media, user data, local
databases, downloaded third-party repositories, built executables, or secrets.

Before opening a pull request:

```powershell
python scripts/check_public_source.py
python -m compileall -q ai_studio_launcher.py video_faceswap_pipeline.py watermark_tools
```

Media editing contributions must follow
[docs/RESPONSIBLE_USE.md](docs/RESPONSIBLE_USE.md).
