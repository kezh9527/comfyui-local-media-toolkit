# 全新 clone 验证记录

本页记录公开仓库从全新目录启动的验证结果。验证目标是确认文档中的最小启动
流程不依赖维护机器上的固定仓库路径，例如 `D:\ComfyUI`。

## 2026-06-04：第 4 天验证

验证环境：

- 维护工作区：`D:\ComfyUI`
- 验证 clone 目录：`D:\ComfyUI\temp\day4-clone-validation-7328806`
- 验证提交：`7328806 Improve missing dependency diagnostics`
- Python：`D:\conda_envs\comfyui\python.exe`，Python 3.10.20

远端公开仓库检查：

```powershell
git ls-remote https://github.com/kezh9527/comfyui-local-media-toolkit.git HEAD
```

结果：成功返回远端 HEAD `7328806b44eae348d9dc13705ba5dedb7718514b`。

远端浅克隆尝试：

```powershell
git clone --depth 1 https://github.com/kezh9527/comfyui-local-media-toolkit.git temp\day4-clone-validation-7328806
```

结果：当前维护网络多次无法完成 GitHub 443 连接，`git clone` 失败或超时。失败
信息为 `Failed to connect to github.com port 443`。因此本次启动验证使用与
`origin/main` 相同提交的本地干净 clone 兜底执行：

```powershell
git clone --no-hardlinks . temp\day4-clone-validation-7328806
git -C temp\day4-clone-validation-7328806 rev-parse --short HEAD
```

最小启动流程：

```powershell
cd D:\ComfyUI\temp\day4-clone-validation-7328806
start_comfyui_cpu.bat
```

验证结果：

- `start_comfyui_cpu.bat` 从 clone 目录启动，不要求当前目录是 `D:\ComfyUI`。
- `http://127.0.0.1:8188/system_stats` 返回 200。
- 返回信息包含 CPU 设备、Python 3.10.20、PyTorch `2.12.0+cpu` 和
  ComfyUI `0.22.0`。
- 启动日志显示 `To see the GUI go to: http://127.0.0.1:8188`。

本次未发现需要修改的最小启动文档。仍需在网络可稳定访问 GitHub 时补做一次
真正从远端完成的浅克隆验证。
