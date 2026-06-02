# Open Source Release Checklist

Use this checklist before publishing the derivative repository and before
applying to an open-source maintainer program.

## Repository Preparation

- Keep the repository public and preserve [LICENSE](../LICENSE).
- Keep the upstream ComfyUI attribution in [NOTICE.md](../NOTICE.md).
- Do not commit model weights, user media, generated outputs, databases, logs,
  downloaded third-party projects, build artifacts, or local secrets.
- Keep the optional dependency boundary explicit: setup scripts download those
  projects at setup time.
- Run the public source check and compile the local toolkit sources.

```powershell
git add -A
python .\scripts\check_public_source.py
python -m compileall -q ai_studio_launcher.py video_faceswap_pipeline.py watermark_tools
git status --short --ignored
```

## Release Quality

- Publish a clear first release with a concise changelog.
- Enable GitHub Issues and use them for the derivative components.
- Add screenshots or a short demo that uses synthetic or authorized media.
- Record tested operating systems, Conda layout, and known limitations.
  Current records live in
  [VERIFIED_ENVIRONMENTS.zh-CN.md](VERIFIED_ENVIRONMENTS.zh-CN.md).
- Keep a small roadmap and respond to issues consistently.

## Maintainer Application Notes

Describe this project honestly as a community-maintained ComfyUI derivative with
its own local launcher and media-tooling layer.

Useful evidence:

- Links to commits you authored and releases you published.
- Installation documentation and CI results.
- Issue triage, pull-request reviews, and a maintenance roadmap.
- Real usage metrics for this derivative repository, when available.
- A concrete explanation of how coding-agent access would improve maintenance,
  tests, documentation, and issue resolution.

Do not claim upstream ComfyUI stars, downloads, users, or maintainer status as
your own. A new repository may be eligible to apply, but reviewers decide
whether its independent maintenance activity and ecosystem value are strong
enough.
