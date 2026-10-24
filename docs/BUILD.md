# 构建说明

发布包包含完整运行时及两个模型；普通用户无需执行以下步骤。

## 固定版本

- Electron 45.0.0，官方 GitHub Release 的 darwin-arm64 / win32-x64 ZIP，使用官方 SHASUMS256 验证。
- Astral python-build-standalone / uv 提供的 CPython 3.12.14，对应 macOS aarch64、Windows x86_64。
- Python 精确版本清单在 requirements/。Windows PyTorch 采用 2.10.0+cu128，来自官方 CUDA 12.8 wheel 索引。
- VoxCPM 源码固定提交 cce58a5b59303c9bd63d12f23afe6a49a4a80c59，vendor 目录保持上游代码，许可证随目录附带。
- 两个模型固定 revision 和每文件 SHA256 位于 models-manifest.json。

## 准备离线输入

使用 uv 安装对应独立 Python，安装依赖到该运行时的 site-packages。Mac 用 requirements/macos-arm64.txt；Windows 使用 requirements/windows-x64.txt，并给 torch / torchaudio 配置官方 https://download.pytorch.org/whl/cu128 索引。跨平台准备时须指定目标 Python 3.12、目标平台、only-binary，不能把本机 venv 复制为 Windows 运行时。

从 Hugging Face 对应仓库的固定 revision 下载两个模型，保持模型清单内的相对目录结构。目录命名为 VoxCPM2 和 Qwen3-ASR-1.7B。下载完成后用 scripts/verify_models.py 校验，不接受模型缺文件或摘要不同。

## 组装

```sh
python3 scripts/verify_models.py /path/to/models
python3 scripts/assemble.py --platform darwin-arm64 --runtime /path/to/python-runtime --models /path/to/models --electron-zip /path/to/electron-v45.0.0-darwin-arm64.zip --output /path/to/new-output
```

Windows 将 platform 改成 win32-x64，并提供对应运行时和 Electron ZIP。输出目录必须尚不存在，避免覆盖已在使用的构建。

Mac 使用 ditto 提取官方 Electron ZIP，以正确保留 Framework 符号链接。组装后可用 `codesign --force --deep --sign - ".../VoxCPM Desktop.app"` 进行本地 ad-hoc 签名。这不是 Developer ID 签名或公证。使用 DMG 保留应用结构，再压成 7z 分卷。

Windows 输出为便携完整目录，运行 exe 后有图形安装页。可在 Windows 上对 exe 添加签名；当前发布无 Authenticode 签名。不得把 Windows 静态检查写成实机通过。

## 开发与边界

主进程在 bundle.json 相邻目录定位 engine、python、models，界面在 app/ 中。可用 VOX_DESKTOP_BUNDLE 指向测试 bundle、VOX_DESKTOP_DATA 指向隔离的用户数据目录；发布包不设置这些变量。

引擎每次只处理一个 JSON 请求，输出 JSONL 进度和结果；主进程对操作设置总时限并终止进程树。渲染进程关闭 Node 集成，启用沙箱、上下文隔离及 CSP，只有预加载白名单 IPC。

公开或分享发布包前检查没有 reference-cache、outputs、jobs、settings.json、draft.json、私人路径或游戏素材。模型和依赖许可证必须随包保留。
