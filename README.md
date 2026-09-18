# Visora

本阶段实现离线生产管线验证：Pydantic v2 契约、音频预算、Mock 图片/视频 Provider、任务状态机、FFmpeg 合成和混音测量。没有接入收费 API。

## 本地运行（Windows PowerShell）

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[test]'
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m visora_engine.validation
```

需要 Python 3.11+、FFmpeg 6+ 和 ffprobe。依赖中的 imageio-ffmpeg 提供本地 FFmpeg；ffprobe 需自行安装，或设置 `FFPROBE_BINARY`。也可将完整工具包解压到 `.tools/`，验收入口会发现其中的 ffprobe.exe。使用 `FFMPEG_BINARY` 可覆盖默认 FFmpeg。

Windows 测试人声来自系统自带的离线英语语音，需要安装英语声音；BGM 是本地合成的三音和弦。其他系统可通过 `--speech-dir` 提供 `speech-raw-1.wav` 至 `speech-raw-4.wav`。自备音频必须与测试台词相符并符合时长预算。字体默认使用 Arial 或 DejaVu Sans，也可设置 `VISORA_FONT`。

首次安装会下载免费的开发依赖；安装后验证无需网络、API Key、Redis 或数据库。生成文件写入忽略目录 `artifacts/local-validation/`：

- `final.mp4` / `rerolled.mp4`：初次成片和 Scene 2 重抽后的成片。
- `mixed.wav` / `speech-spec-mix.wav`：校准混音与规范原参数的对照试听。
- `report.json`：编码、帧数、状态轨迹、重抽复用及闪避曲线。
- `storyboard.json` / `timeline.json` / `*.schema.json`：运行数据和契约。

## 模块边界

`packages/engine/visora_engine/` 中，`schemas` 定义契约，`scheduler` 计算预算，`providers` 隔离生成模型，`jobs` 管理单进程异步任务，`state` 管理状态与失效，`audio` 处理混音，`composer` 渲染视频，`pipeline` 串联模块。`director` 当前仅提供确定性分镜样例。

`apps/api`、`apps/web` 和 `packages/shared` 预留服务化与前端边界。本阶段没有实现 FastAPI HTTP 服务、Celery/Redis 分布式幂等、持久化或收费模型。

执行依据：`project/Visora_MVP_Execution_Spec.md`。测试结果与实现解释见 `project/LOCAL_VALIDATION_REPORT.md`。不得直接向 main 提交；推送前运行测试。

完整实施任务见 [实施路线图](project/IMPLEMENTATION_ROADMAP.md)；[Jira 任务源数据](project/JIRA_BACKLOG.json) 定义范围、验收与依赖，[实际 Jira 编号](project/JIRA_CREATED.json) 保存同步结果。
