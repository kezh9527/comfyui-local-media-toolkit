# Changelog

## Unreleased

### Added

- Public-source boundary checks for model weights, user media, generated
  artifacts, local databases, secrets, and oversized files.
- Derivative-project documentation, attribution notes, responsible-use guidance,
  and a maintainer release checklist.
- Example runtime configuration in `ai_studio_config.example.json`.

### Changed

- Windows helpers now discover the repository from their own location.
- Conda environment paths can be overridden with `CONDA_ROOT` and
  `CONDA_ENVS_ROOT`.
- FFmpeg lookup can be overridden with `FFMPEG_BIN_DIR`.
- Missing FFmpeg, optional service, workflow model, and input diagnostics now
  include actionable resolution steps in the launcher and API responses.
- Public documentation describes optional third-party dependencies as
  setup-time downloads instead of bundled source.
