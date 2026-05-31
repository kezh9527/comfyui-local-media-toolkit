# Security Policy

## Local-First Scope

ComfyAI Studio Local Toolkit is designed to run on the local machine. The
launcher, ComfyUI server, and watermark API bind to `127.0.0.1` by default.
Do not expose these services to an untrusted network without adding appropriate
authentication, authorization, and transport security.

Custom nodes, model files, downloaded third-party repositories, and platform
resolver integrations are external code or data. Review their licenses and
trust them as carefully as any other software installed on your machine.

## Report Here

Use this repository's private GitHub security advisory feature for
vulnerabilities in:

- `ai_studio_launcher.py`
- `watermark_tools/`
- `video_faceswap_pipeline.py`
- setup or start helpers added by this derivative project

Include reproduction steps, affected versions, operating system, and the impact
on a default localhost-only installation.

## Report Upstream

For a vulnerability reproducible in unmodified ComfyUI, use the
[upstream ComfyUI advisory page](https://github.com/comfyanonymous/ComfyUI/security/advisories/new).

Do not open a public issue for an unpatched vulnerability.
