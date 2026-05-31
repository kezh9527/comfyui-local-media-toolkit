# Attribution and Optional Dependencies

## Upstream ComfyUI

This repository is a derivative workspace based on
[ComfyUI](https://github.com/comfyanonymous/ComfyUI). The upstream project is
licensed under GPL-3.0. The GPL-3.0 license text is preserved in [LICENSE](LICENSE).

The upstream ComfyUI maintainers do not maintain or endorse the local launcher,
watermark tools, face replacement pipeline, or third-party setup helpers added
in this derivative repository.

## Local Additions

The derivative workspace adds:

- `ai_studio_launcher.py`
- `watermark_tools/`
- `video_faceswap_pipeline.py`
- Windows helper scripts and derivative documentation

Unless a file states otherwise, these additions are distributed under the
repository's GPL-3.0 license.

## Optional Dependencies

Optional setup scripts download third-party projects at setup time. Their source
code is intentionally excluded from this repository:

- [D-Ogi/WatermarkRemover-AI](https://github.com/D-Ogi/WatermarkRemover-AI),
  licensed separately under MIT.
- [wujunwei928/parse-video-py](https://github.com/wujunwei928/parse-video-py),
  licensed separately by its maintainers.

Model weights are not distributed with this repository. Obtain each model from
its original source and comply with its license and usage restrictions.
