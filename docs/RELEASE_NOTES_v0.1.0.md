# v0.1.0 Release Notes

Release date: 2026-06-04

This is the first documented release of ComfyAI Studio Local Toolkit, a
local-first derivative workspace built on ComfyUI. The release focuses on making
the public repository safe to inspect, easier to start on Windows, and clearer
about what is intentionally not bundled.

## Highlights

- Added public-source guardrails for model weights, user media, generated
  outputs, local databases, secrets, and oversized files.
- Added derivative-project documentation, attribution notes, responsible-use
  guidance, and a maintainer release checklist.
- Added a synthetic demo image and reproduction notes so the README can show a
  public example without private or unlicensed media.
- Documented the verified Windows CPU maintenance environment and known
  limitations.
- Improved missing-dependency diagnostics for FFmpeg, optional services,
  workflow model files, and required workflow inputs.
- Added a new clone startup validation record and CI-backed maintenance tests.

## Verification

The release was checked locally with:

```powershell
python -m unittest discover -s tests-public
python .\scripts\check_public_source.py
python -m compileall -q ai_studio_launcher.py video_faceswap_pipeline.py watermark_tools scripts\check_public_source.py tests-public
```

The public-source CI now runs the source boundary check, the maintenance test
suite, and compile checks.

## Known Limitations

- Model weights, user inputs, generated outputs, custom nodes, logs, local
  databases, and downloaded third-party projects are intentionally excluded from
  the repository.
- GPU startup paths are not claimed as verified by this release; the current
  maintained record covers the Windows CPU environment.
- The 2026-06-04 remote GitHub shallow clone attempt was blocked by intermittent
  GitHub 443 connectivity from the maintenance machine, so startup was verified
  from a clean local clone at the same commit and recorded in
  `docs/CLONE_VALIDATION.zh-CN.md`.

## Completed Issues

- #2 Document reproducible Windows CPU and GPU setup matrix
- #3 Add synthetic demo assets and README screenshots
- #4 Improve error messages for missing FFmpeg, models, and optional dependencies

Issue #1 remains open for deeper image cleanup, API validation, and job
lifecycle tests.
