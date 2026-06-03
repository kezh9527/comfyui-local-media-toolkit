# ComfyAI Studio Local Toolkit 使用说明

## 1. 仓库边界

公开仓库只包含源码和文档，不包含以下本地内容：

- `models/` 下的模型权重
- `input/`、`output/` 下的用户素材和生成结果
- `user/` 下的数据库和配置
- `custom_nodes/` 下自行安装的第三方节点
- `external/` 下由脚本下载的第三方项目
- `build/`、`dist/`、日志、缓存和 EXE

这些目录仍可在本机正常使用，只是不会被提交到 GitHub。

## 2. 环境变量

脚本会根据自身位置识别仓库根目录，不再要求项目必须放在 `D:\ComfyUI`。
为兼容现有工作区，Conda 环境默认仍位于 `D:\conda_envs`。路径不同时先设置：

```bat
set CONDA_ROOT=C:\Miniconda3
set CONDA_ENVS_ROOT=C:\conda_envs
set FFMPEG_BIN_DIR=C:\ffmpeg\bin
```

当前维护机器的 Windows、Python、Conda、FFmpeg 和硬件记录见
[VERIFIED_ENVIRONMENTS.zh-CN.md](VERIFIED_ENVIRONMENTS.zh-CN.md)。该记录只
代表真实验证过的环境，不代表未测试硬件或操作系统也已经可用。

## 3. 合成演示

公开演示素材位于 [DEMO.zh-CN.md](DEMO.zh-CN.md)。演示图由代码生成，不是
用户私有素材；清理结果由本地 `watermark_tools` CLI 生成。

## 4. 启动 ComfyUI

CPU 模式：

```bat
start_comfyui_cpu.bat
```

启动后打开 `http://127.0.0.1:8188`。

需要启动本地控制台时，直接运行源码：

```powershell
$env:CONDA_ENVS_ROOT = "D:\conda_envs"
& "$env:CONDA_ENVS_ROOT\comfyui\python.exe" .\ai_studio_launcher.py
```

构建本地 EXE：

```bat
build_ai_studio_exe.bat
```

构建结果位于 `dist/` 和仓库根目录，两处 EXE 都会被 Git 忽略。

## 5. 本地图片去水印

以下示例从仓库根目录执行：

```powershell
$python = "D:\conda_envs\comfyui\python.exe"
& $python -m watermark_tools.cli image .\input\sample.png `
  --box 20,20,220,80 `
  --output .\output\sample_clean.png
```

可选参数：

- `--smart`：在矩形区域内只处理较可能是水印的笔画。
- `--dilate 2`：调整掩码膨胀范围。
- `--mask .\input\mask.png`：使用黑白掩码，白色区域会被修复。
- `--auto`：尝试自动识别边缘区域的高对比度水印。

## 6. 本地视频去水印

```powershell
& $python -m watermark_tools.cli video .\input\sample.mp4 `
  --box 20,20,220,80 `
  --smart `
  --output .\output\sample_clean.mp4
```

调试时可增加 `--limit-frames 10`，只处理前 10 帧。

## 7. 可选的平台链接解析

该功能依赖单独安装的 `parse-video-py`：

```bat
setup_parse_video_py.bat
start_parse_video_py.bat
```

另开一个 PowerShell 窗口：

```powershell
$env:PARSE_VIDEO_BASE_URL = "http://127.0.0.1:8000"
& $python -m watermark_tools.cli link "https://..." --download
```

请只下载你拥有或已获得授权的媒体，并遵守对应平台规则。

## 8. 可选的 AI 去水印模式

首次安装：

```bat
setup_watermark_ai.bat
```

图片处理：

```powershell
& $python -m watermark_tools.cli image .\input\sample.png --engine external-ai
```

该脚本会将 `D-Ogi/WatermarkRemover-AI` 下载到 `external/`。首次运行还可能
下载额外模型权重。`external/` 和模型文件均不会提交到 GitHub。

## 9. 本地 API

启动水印服务：

```bat
start_watermark_service.bat
```

同时启动平台解析服务和水印服务：

```bat
start_watermark_stack.bat
```

默认地址为 `http://127.0.0.1:8198`。主要接口：

- `GET /health`
- `POST /api/watermark/link`
- `POST /api/watermark/image`
- `POST /api/watermark/video`
- `GET /api/jobs/{id}`

图片任务示例：

```powershell
$body = @{
  input = ".\input\sample.png"
  box = @("20,20,220,80")
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8198/api/watermark/image" `
  -ContentType "application/json" `
  -Body $body
```

## 10. 可选的 InstantID 人脸替换

模型文件需要自行下载并放置在以下位置：

```text
models/checkpoints/sdxl_lightning_4step.safetensors
models/instantid/ip-adapter.bin
models/controlnet/instantid_controlnet.safetensors
models/insightface/models/antelopev2/
```

先启动 ComfyUI，再执行：

```bat
run_video_faceswap_example.bat
```

该功能仅用于已获得明确授权的素材和人脸。完整参数说明见
[../VIDEO_FACESWAP_README.txt](../VIDEO_FACESWAP_README.txt)。

## 11. 公开仓库发布前检查

初始化或更新 Git 暂存区后执行：

```powershell
python .\scripts\check_public_source.py
python -m compileall -q ai_studio_launcher.py video_faceswap_pipeline.py watermark_tools
```

发布步骤和申请材料建议见
[OPEN_SOURCE_RELEASE_CHECKLIST.md](OPEN_SOURCE_RELEASE_CHECKLIST.md)。
