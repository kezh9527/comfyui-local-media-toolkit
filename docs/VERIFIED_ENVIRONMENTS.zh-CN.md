# 已验证环境与限制

本页记录本项目衍生工具层在维护过程中的真实验证环境。首次记录时间：
2026-06-01；最近更新：2026-06-02。

这些信息只代表当前维护机器的验证结果，不等同于上游 ComfyUI 的完整硬件
兼容性声明。没有实际运行过的配置会明确标为“待验证”。

## 当前维护机器

| 项目 | 值 |
| --- | --- |
| 设备型号 | ThinkBook 16 G5+ IRH |
| 操作系统 | Microsoft Windows 11 家庭版 中文版 |
| 版本号 | 25H2 |
| Windows 版本 | 10.0.26200 |
| Build | 26200.8457 |
| 系统架构 | 64-bit |
| CPU | 13th Gen Intel(R) Core(TM) i5-13500H |
| CPU 核心 / 线程 | 12 cores / 16 logical processors |
| 内存 | 32.0 GB |
| 显卡 | Intel(R) Iris(R) Xe Graphics |
| 显卡驱动 | 32.0.101.6733 |
| 远程 / 虚拟显示驱动 | OrayIddDriver Device, MuMu Virtual Display Adapter |
| 仓库路径 | `D:\ComfyUI` |

## Python 与 Conda

| 项目 | 值 |
| --- | --- |
| 默认 `python --version` | Python 3.12.9 |
| 默认 Python 路径 | `D:\Miniconda3\python.exe` |
| 备用 Python 路径 | `C:\Python312\python.exe` |
| Conda 版本 | conda 25.1.1 |
| Conda 根目录 | `D:\Miniconda3` |
| Conda 环境根目录 | `D:\conda_envs` |
| Conda 包缓存目录 | `D:\conda_pkgs` |
| Conda 环境搜索目录 | `D:\conda_envs`; `C:\Users\70224\.conda\envs`; `D:\Miniconda3\envs`; `C:\Users\70224\AppData\Local\conda\conda\envs` |
| Conda 平台 | `win-64` |
| Conda solver | `libmamba` |

已发现的 Conda 环境：

| 环境 | 路径 | Python | 验证状态 |
| --- | --- | --- | --- |
| `base` | `D:\Miniconda3` | 3.12.9 | 已通过 `python --version` 验证 |
| `comfyui` | `D:\conda_envs\comfyui` | 3.10.20 | 已通过 `python.exe --version` 验证 |
| `parse-video` | `D:\conda_envs\parse-video` | 3.10.20 | 已通过 `python.exe --version` 验证 |
| `watermark-ai` | `D:\conda_envs\watermark-ai` | 3.10.20 | 已通过 `python.exe --version` 验证 |
| `facefusion` | `D:\conda_envs\facefusion` | 3.12.9 | 已通过 `python.exe --version` 验证 |
| `ncds-land-backend-b-type-realtime-plan` | `D:\conda_envs\ncds-land-backend-b-type-realtime-plan` | 待验证 | 非本项目必需环境 |
| `rppg_denvs` | `D:\conda_envs\rppg_denvs` | 待验证 | 非本项目必需环境 |
| `scoliosis` | `D:\conda_envs\scoliosis` | 待验证 | 非本项目必需环境 |

## FFmpeg

| 项目 | 值 |
| --- | --- |
| FFmpeg 路径 | `D:\AI\ffmpeg\bin\ffmpeg.exe` |
| FFmpeg 版本 | 8.1.1 essentials build by gyan.dev |

如果本地路径不同，可以在启动前设置：

```bat
set FFMPEG_BIN_DIR=C:\ffmpeg\bin
```

## 已验证命令

以下命令在 `D:\ComfyUI` 执行：

```powershell
python --version
where.exe python
conda --version
where.exe conda
conda info --envs
conda config --show envs_dirs pkgs_dirs channels
Get-CimInstance Win32_OperatingSystem
Get-CimInstance Win32_Processor
Get-CimInstance Win32_VideoController
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
D:\conda_envs\comfyui\python.exe --version
D:\conda_envs\parse-video\python.exe --version
D:\conda_envs\watermark-ai\python.exe --version
D:\conda_envs\facefusion\python.exe --version
where.exe ffmpeg
ffmpeg -version
```

## 当前验证结论

- 维护机器是 Windows 11 x64，使用 Intel 集成显卡。
- 本项目的 Windows helper 默认适配 `D:\conda_envs` 布局。
- `comfyui`、`parse-video`、`watermark-ai` 环境均可直接调用
  `python.exe --version`。
- `facefusion` 环境存在并可调用 Python，但它不是当前本地工具链的必需环境。
- 当前记录只验证环境发现和版本查询；完整安装流程、启动流程和功能烟测需在
  后续维护日中继续补充。
- NVIDIA CUDA、AMD ROCm、Intel Arc XPU、macOS、Linux 均未在此记录中验证。
- 模型权重、用户输入、输出结果、第三方下载项目、日志和本地数据库仍不应
  提交到公开仓库。

## 已知限制

- 模型文件需要用户按各模型许可证自行下载，并放入对应的 `models/` 子目录。
- `external/` 下的可选第三方项目由脚本在本机下载，不随仓库发布。
- 当前维护机器没有独立 NVIDIA/AMD 显卡，因此不能声明 CUDA 或 ROCm 路径已验证。
- 如果 Conda 根目录或环境目录不同，需要先设置 `CONDA_ROOT` 和
  `CONDA_ENVS_ROOT`。
- 如果 FFmpeg 不在 `PATH` 中，需要设置 `FFMPEG_BIN_DIR`。
- 当前记录没有验证 `ncds-land-backend-b-type-realtime-plan`、`rppg_denvs` 和
  `scoliosis` 环境，因为它们不是本项目公开工具层的必需环境。
