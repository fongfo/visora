# Visora 实施任务路线图

依据：技术架构方案、MVP 执行契约和本地验证报告。任务源数据为 `JIRA_BACKLOG.json`，实际 Jira 编号与状态快照由 `JIRA_CREATED.json` 记录。

## 分解结构

| Epic | 范围 | 任务数 |
| --- | --- | ---: |
| [VIS-1 / E01](https://growth-more.atlassian.net/browse/VIS-1) | 工程基础与零成本管线验证 | 4 |
| [VIS-2 / E02](https://growth-more.atlassian.net/browse/VIS-2) | FastAPI 服务、数据持久化与素材管理 | 5 |
| [VIS-3 / E03](https://growth-more.atlassian.net/browse/VIS-3) | 可靠异步调度、幂等与版本失效 | 5 |
| [VIS-4 / E04](https://growth-more.atlassian.net/browse/VIS-4) | AI Director、结构化分镜与音频优先 | 4 |
| [VIS-5 / E05](https://growth-more.atlassian.net/browse/VIS-5) | 商品保真与关键帧生产 | 4 |
| [VIS-6 / E06](https://growth-more.atlassian.net/browse/VIS-6) | 真实 I2V Provider 与质量成本验证 | 4 |
| [VIS-7 / E07](https://growth-more.atlassian.net/browse/VIS-7) | 生产级 FFmpeg 后期与媒体验收 | 4 |
| [VIS-8 / E08](https://growth-more.atlassian.net/browse/VIS-8) | Next.js 视频制作工作台 | 6 |
| [VIS-9 / E09](https://growth-more.atlassian.net/browse/VIS-9) | 额度、账单与商业化 | 4 |
| [VIS-10 / E10](https://growth-more.atlassian.net/browse/VIS-10) | 端到端验收、运维与发布 | 4 |

共 10 个 Epic、44 个 Task、97 条任务依赖。BASE-01/02/03 已完成，有 development 提交 `26811ac` 和 54 项测试证据；其余 41 个任务待开发。Epic 本身不因部分基础工作完成而标记完成。

每项任务包含范围、至少三个验收条件、优先级和依赖。VIS 当前创建表单未开放 Priority 字段，使用 `priority-p0` / `priority-p1` 标签和描述表达优先级；不擅自修改 Jira 项目配置、分配人员或设定交付日期。

## 推荐执行顺序与阶段门禁

1. **工程与服务化**：BASE-04 → API-01，同时推进身份隔离 API-05 和 Worker JOB-01；随后完成 CRUD、素材、可靠投递、版本失效和 JOB-05。此阶段继续 Mock，不消耗模型额度。
2. **工作台 Mock 闭环**：WEB-01 可与后端推进；依次完成输入、脚本、关键帧确认、重抽和下载，并以 WEB-06 验证用户流程。
3. **真实管线准备与接入**：先做 VID-01 核实模型能力/当前费用；落实 BILL-01/02 的额度保护，再接 Director/TTS、商品抠图、图片和 I2V。真实调用须显式启用、具备有效预算；创建任务不等于授权实际消费。
4. **商品质量与媒体增强**：完成品牌文字图层、2.5D 降级、人工听感与保真复核，VID-04 记录真实质量和费用。执行契约中的费用是目标，不是已经验证的报价。
5. **商业化与上线验收**：测试模式支付、账单 UI、可观测性、部署/恢复演练和 OPS-04。生产部署与真实支付启用按明确授权执行。

优先级不等同于依赖顺序；以任务依赖图为准。当前最先可启动的未完成任务是 BASE-04（工程环境与 CI）和 VID-01（只读核实供应商能力与费用）。

## Jira 执行任务索引

| Jira | 计划编号 | 任务 |
| --- | --- | --- |
| [VIS-11](https://growth-more.atlassian.net/browse/VIS-11) | BASE-01 | Pydantic 契约与音频优先调度（已完成） |
| [VIS-12](https://growth-more.atlassian.net/browse/VIS-12) | BASE-02 | Mock Provider、单进程状态机与重抽（已完成） |
| [VIS-13](https://growth-more.atlassian.net/browse/VIS-13) | BASE-03 | 本地 FFmpeg 混音与合成验证（已完成） |
| [VIS-14](https://growth-more.atlassian.net/browse/VIS-14) | BASE-04 | 开发环境、容器与 CI |
| [VIS-15](https://growth-more.atlassian.net/browse/VIS-15) | API-01 | PostgreSQL 模型与迁移 |
| [VIS-16](https://growth-more.atlassian.net/browse/VIS-16) | API-02 | 项目/创意/分镜 CRUD 与确认 |
| [VIS-17](https://growth-more.atlassian.net/browse/VIS-17) | API-03 | 素材存储、安全上传与签名访问 |
| [VIS-18](https://growth-more.atlassian.net/browse/VIS-18) | API-04 | 进度、错误与下载 API |
| [VIS-19](https://growth-more.atlassian.net/browse/VIS-19) | API-05 | 身份认证与权限隔离 |
| [VIS-20](https://growth-more.atlassian.net/browse/VIS-20) | JOB-01 | Celery Worker 与队列 |
| [VIS-21](https://growth-more.atlassian.net/browse/VIS-21) | JOB-02 | 分布式幂等与事务投递 |
| [VIS-22](https://growth-more.atlassian.net/browse/VIS-22) | JOB-03 | 重试、超时、取消与回调 |
| [VIS-23](https://growth-more.atlassian.net/browse/VIS-23) | JOB-04 | 级联失效与单镜头重抽 |
| [VIS-24](https://growth-more.atlassian.net/browse/VIS-24) | JOB-05 | 零额度服务化端到端验收 |
| [VIS-25](https://growth-more.atlassian.net/browse/VIS-25) | AI-01 | 三套创意方案生成 |
| [VIS-26](https://growth-more.atlassian.net/browse/VIS-26) | AI-02 | 四场景分镜与文字预算 |
| [VIS-27](https://growth-more.atlassian.net/browse/VIS-27) | AI-03 | TTS 与句级字幕 |
| [VIS-28](https://growth-more.atlassian.net/browse/VIS-28) | AI-04 | 有界改写与音频预算 |
| [VIS-29](https://growth-more.atlassian.net/browse/VIS-29) | IMG-01 | 商品抠图与原始素材 |
| [VIS-30](https://growth-more.atlassian.net/browse/VIS-30) | IMG-02 | Image Provider 与场景融合 |
| [VIS-31](https://growth-more.atlassian.net/browse/VIS-31) | IMG-03 | 关键帧审核、确认与重生成 |
| [VIS-32](https://growth-more.atlassian.net/browse/VIS-32) | IMG-04 | 商品保真审核与分层素材 |
| [VIS-33](https://growth-more.atlassian.net/browse/VIS-33) | VID-01 | 核实模型能力与费用 |
| [VIS-34](https://growth-more.atlassian.net/browse/VIS-34) | VID-02 | I2V Provider 与安全回调 |
| [VIS-35](https://growth-more.atlassian.net/browse/VIS-35) | VID-03 | 视频能力、缓存与裁剪 |
| [VIS-36](https://growth-more.atlassian.net/browse/VIS-36) | VID-04 | 真实样片质量与成本实测 |
| [VIS-37](https://growth-more.atlassian.net/browse/VIS-37) | POST-01 | 生产渲染隔离与发布 |
| [VIS-38](https://growth-more.atlassian.net/browse/VIS-38) | POST-02 | 字幕、Logo 与 CTA |
| [VIS-39](https://growth-more.atlassian.net/browse/VIS-39) | POST-03 | 2.5D 保真降级合成 |
| [VIS-40](https://growth-more.atlassian.net/browse/VIS-40) | POST-04 | 混音听感与媒体验收 |
| [VIS-41](https://growth-more.atlassian.net/browse/VIS-41) | WEB-01 | 交互流程与 Next.js 基础 |
| [VIS-42](https://growth-more.atlassian.net/browse/VIS-42) | WEB-02 | 项目列表、上传与参数 |
| [VIS-43](https://growth-more.atlassian.net/browse/VIS-43) | WEB-03 | 创意选择与脚本编辑 |
| [VIS-44](https://growth-more.atlassian.net/browse/VIS-44) | WEB-04 | 关键帧看板与确认门禁 |
| [VIS-45](https://growth-more.atlassian.net/browse/VIS-45) | WEB-05 | 进度、重抽、播放器与下载 |
| [VIS-46](https://growth-more.atlassian.net/browse/VIS-46) | WEB-06 | Mock 工作台端到端验收 |
| [VIS-47](https://growth-more.atlassian.net/browse/VIS-47) | BILL-01 | 额度预占与费用流水 |
| [VIS-48](https://growth-more.atlassian.net/browse/VIS-48) | BILL-02 | 费用预估与预算熔断 |
| [VIS-49](https://growth-more.atlassian.net/browse/VIS-49) | BILL-03 | Stripe 测试模式支付 |
| [VIS-50](https://growth-more.atlassian.net/browse/VIS-50) | BILL-04 | 账户额度与账单界面 |
| [VIS-51](https://growth-more.atlassian.net/browse/VIS-51) | OPS-01 | 追踪、成本指标与告警 |
| [VIS-52](https://growth-more.atlassian.net/browse/VIS-52) | OPS-02 | 预发布部署与回滚 |
| [VIS-53](https://growth-more.atlassian.net/browse/VIS-53) | OPS-03 | 素材清理、备份与恢复 |
| [VIS-54](https://growth-more.atlassian.net/browse/VIS-54) | OPS-04 | MVP 全链路与上线验收 |

## 同步约定

`scripts/sync_jira_backlog.ps1` 默认只读 Inspect。Create 创建缺失条目，Link 建立前置依赖并将有证据的基线任务置为完成，Verify 逐项核对父 Epic、摘要、依赖和完成状态。凭据只读环境变量或显式传入的已有配置文件，不保存到仓库。

所有 Jira 条目带有唯一 `visora-plan-*` 标签以便恢复和去重。写请求遇到不确定响应时停止，不盲目重试；先查询并确认远端状态后继续。该脚本用于本次已授权的建档，不作为后台自动化运行。
