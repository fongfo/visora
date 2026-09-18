# Visora AI Video Studio — 技术方案与落地实施指南

> **核心定位**：AI 原生商品短视频制作平台（AI-Native Video Production Studio），通过「分镜驱动（Storyboard-driven）+ 关键帧图生视频（Keyframe-to-Video）+ 确定性后期合成（FFmpeg Composer）」的完整制作管线，将商品图片和信息自动化生成为高商业质感的 10–30 秒广告短视频。

---

## 目录

1. [系统整体架构与数据流](#1-系统整体架构与数据流)  
2. [核心数据契约 (Data Schemas)](#2-核心数据契约-data-schemas)  
3. [五大核心技术子系统设计](#3-五大核心技术子系统设计)  
   - 3.1 AI Director 结构化分镜引擎  
   - 3.2 商品保真与 Keyframe 生成管线  
   - 3.3 音频优先与节奏时序对齐机制  
   - 3.4 统一多模型提供商抽象层 (Provider Layer)  
   - 3.5 确定性后期渲染合成引擎 (FFmpeg Composer)  
4. [推荐技术栈与工程目录规范](#4-推荐技术栈与工程目录规范)  
5. [MVP 分阶段实施路线图](#5-mvp-分阶段实施路线图)  
6. [生产环境避坑与成本控制策略](#6-生产环境避坑与成本控制策略)

---

## 1\. 系统整体架构与数据流

Visora 坚决摒弃脆弱的“单次 Prompt 直接生成完整视频”模式，采用类似专业影视工业的模块化管线：

\[用户输入\] (商品图/卖点/风格/时长)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[AI Director (LLM)\] ───► 生成 3 个 Creative Concepts ───► 用户选定

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[Storyboard Engine\] ───► 结构化分镜拆解 (4-5 个 3-4s Scene)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[Audio-First Engine\] ──► TTS 语音生成 ──► 提取精确字/句时间戳 (确定镜头精准时长)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[Keyframe Pipeline\] ───► 商品抠图 (SAM/BiRefNet) \+ 场景打光融合 (Flux Inpainting) ──► 审查确认

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[I2V Video Providers\] ─► 并发生成各个独立 Scene MP4 视频片段 (支持单镜头重抽)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[FFmpeg Composer\] ─────► 视频拼接 \+ 转场 \+ 语音对齐 \+ BGM 自动闪避(Ducking) \+ 字幕/Logo

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▼

\[Final Deliverable\] ───► 15s 高清商业广告 (1080x1920 / 1920x1080)

---

## 2\. 核心数据契约 (Data Schemas)

系统内部以两个标准 JSON 契约作为各服务间解耦的唯一事实来源：

### 2.1 StoryboardSchema (分镜元数据契约)

interface StoryboardSchema {

&nbsp;&nbsp;concept\_title: string;

&nbsp;&nbsp;target\_aspect\_ratio: "9:16" | "16:9" | "1:1";

&nbsp;&nbsp;total\_target\_duration: number;

&nbsp;&nbsp;product\_metadata: {

&nbsp;&nbsp;&nbsp;&nbsp;name: string;

&nbsp;&nbsp;&nbsp;&nbsp;brand?: string;

&nbsp;&nbsp;&nbsp;&nbsp;selling\_points: string\[\];

&nbsp;&nbsp;&nbsp;&nbsp;isolated\_image\_url: string;

&nbsp;&nbsp;};

&nbsp;&nbsp;scenes: Array\<{

&nbsp;&nbsp;&nbsp;&nbsp;scene\_index: number;

&nbsp;&nbsp;&nbsp;&nbsp;shot\_type: string; // e.g., "Macro close-up", "Wide hero shot"

&nbsp;&nbsp;&nbsp;&nbsp;camera\_motion: string; // e.g., "Slow push-in, subtle orbital drift"

&nbsp;&nbsp;&nbsp;&nbsp;lighting\_style: string;

&nbsp;&nbsp;&nbsp;&nbsp;keyframe\_prompt: string;

&nbsp;&nbsp;&nbsp;&nbsp;motion\_prompt: string;

&nbsp;&nbsp;&nbsp;&nbsp;voiceover\_script: string;

&nbsp;&nbsp;&nbsp;&nbsp;subtitle\_text: string;

&nbsp;&nbsp;&nbsp;&nbsp;planned\_duration: number; // 初始预估秒数

&nbsp;&nbsp;&nbsp;&nbsp;actual\_audio\_duration?: number; // TTS 生成后的精确时长

&nbsp;&nbsp;}\>;

}

### 2.2 TimelineSchema (合成器时间轴契约)

interface TimelineSchema {

&nbsp;&nbsp;canvas: {

&nbsp;&nbsp;&nbsp;&nbsp;width: number;

&nbsp;&nbsp;&nbsp;&nbsp;height: number;

&nbsp;&nbsp;&nbsp;&nbsp;fps: number;

&nbsp;&nbsp;};

&nbsp;&nbsp;tracks: {

&nbsp;&nbsp;&nbsp;&nbsp;video\_clips: Array\<{

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;scene\_index: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;source\_url: string;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;timeline\_start: number; // 秒

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;duration: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;transition\_out?: "fade" | "dissolve" | "wipe";

&nbsp;&nbsp;&nbsp;&nbsp;}\>;

&nbsp;&nbsp;&nbsp;&nbsp;voiceover\_tracks: Array\<{

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;scene\_index: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;audio\_url: string;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;timeline\_start: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;duration: number;

&nbsp;&nbsp;&nbsp;&nbsp;}\>;

&nbsp;&nbsp;&nbsp;&nbsp;background\_music: {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;audio\_url: string;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;volume: number; // 0.0 \- 1.0

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ducking: {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;target\_volume: number; // 0.15 (人声说话时自动压低)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;fade\_time: number; // 0.3s

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;};

&nbsp;&nbsp;&nbsp;&nbsp;};

&nbsp;&nbsp;&nbsp;&nbsp;subtitles: Array\<{

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;text: string;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;start\_time: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;end\_time: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;style: "minimal\_modern" | "bold\_impact";

&nbsp;&nbsp;&nbsp;&nbsp;}\>;

&nbsp;&nbsp;&nbsp;&nbsp;overlays: Array\<{

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;type: "logo" | "cta\_button";

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;asset\_url: string;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;position: { x: number; y: number; alignment: "center" | "bottom\_center" };

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;start\_time: number;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;duration: number;

&nbsp;&nbsp;&nbsp;&nbsp;}\>;

&nbsp;&nbsp;};

}

---

## 3\. 五大核心技术子系统设计

### 3.1 AI Director 结构化分镜引擎

* **核心职责**：将模糊的商业需求转化为遵循视听语言（镜头景别、运镜方向、光影设定、声画关系）的严格 JSON 输出。  
* **实现方式**：  
  - 采用结构化输出（OpenAI Structured Outputs / Anthropic Tools API）。  
  - 内置商业广告经典模版节奏库：例如「3s 痛点引入 $\\rightarrow$ 4s 产品登场 $\\rightarrow$ 4s 特写功能展示 $\\rightarrow$ 3s 品牌结语与 CTA」。

### 3.2 商品保真与 Keyframe 生成管线

* **核心难点**：直接文生图或图生视频极易造成商品包装字体变形、Logo 模糊、材质失真。  
* **工程管线**：  
  1. **背景剥离**：调用 FastSAM / BiRefNet 提取透明通道商品主体。  
  2. **场景打光融合**：通过 Flux Inpainting / SDXL ControlNet (Depth \+ Canny)，将商品置于生成的广告场景中，重新计算阴影与环境光反射，输出 4K 商业级 Keyframe。  
  3. **预先确认机制**：用户先审查 Keyframe 静态分镜图，满意后再触发视频生成，避免盲目消耗 GPU 额度。

### 3.3 音频优先与节奏时序对齐机制

* **核心逻辑**：杜绝“先定死 4 秒视频，再让配音去削足适履”。  
* **执行步骤**：  
  1. AI Director 生成各场景配音文案。  
  2. TTS 引擎生成高质感商业人声（如 ElevenLabs 或 OpenAI Onyx）。  
  3. 测量实际人声时长（精确至毫秒）。  
  4. 若配音耗时 3.6s，则该 Scene 目标视频长度动态调整为 4.0s（预留 0.4s 呼吸留白）；若配音耗时 4.8s，则调度扩展视频生成时长。

### 3.4 统一多模型提供商抽象层 (Provider Layer)

* **标准接口定义**：  
  class BaseVideoProvider(ABC):  
  &nbsp;&nbsp;&nbsp;&nbsp;@abstractmethod  
  &nbsp;&nbsp;&nbsp;&nbsp;async def submit\_i2v\_job(self, keyframe\_url: str, prompt: str, duration: float, aspect\_ratio: str) \-\> str:  
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"""提交图生视频任务，返回 job\_id"""  
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pass  
  &nbsp;  
  &nbsp;&nbsp;&nbsp;&nbsp;@abstractmethod  
  &nbsp;&nbsp;&nbsp;&nbsp;async def poll\_status(self, job\_id: str) \-\> JobResult:  
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"""轮询或解析 Webhook 返回的生成状态与视频下载链接"""  
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pass  
* **适配实现**：  
  - 首选聚合 API（如 `fal.ai` / `Replicate`）：可极速调度 Kling 1.5、Wan2.1、Luma Ray 等模型。  
  - 支持官方直连：Runway Gen-3 Alpha、Google Veo。  
  - 支持按成本/质量策略自动切换 Provider。

### 3.5 确定性后期渲染合成引擎 (FFmpeg Composer)

* **核心优势**：纯程序化处理所有文字、商标和混音，零幻觉、零延迟。  
* **主要特性**：  
  - **动态转场**：支持 `xfade` 实现 Cross-dissolve、Fade-to-black。  
  - **智能音频闪避 (Audio Ducking)**：利用 FFmpeg `sidechaincompress` 滤镜，当人声轨道发声时，BGM 自动下压 80%，人声结束后平滑恢复。  
  - **品牌元素合成**：最后一秒自动叠加高清晰度 Logo、Slogan 及 CTA 动态淡入。

---

## 4\. 推荐技术栈与工程目录规范

### 4.1 技术选型

* **前端 (Web)**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, shadcn/ui, Zustand / React Query  
* **后端 (API)**: Python FastAPI, Pydantic v2, SQLAlchemy / SQLModel  
* **数据与缓存**: PostgreSQL, Redis  
* **异步任务队列**: Celery 或 ARQ  
* **对象存储**: Cloudflare R2 / AWS S3  
* **音视频处理**: FFmpeg 6.0+  
* **AI 聚合调度**: OpenAI SDK, fal-client / replicate-python

### 4.2 仓库目录结构

visora/

├── apps/

│   ├── web/                     \# Next.js 前端应用

│   │   ├── app/                 \# 页面路由 (/create, /project/\[id\], etc.)

│   │   ├── components/          \# UI 组件库 (Storyboard, Timeline, Player)

│   │   └── lib/                 \# 客户端工具库与 API 请求

│   └── api/                     \# FastAPI 后端服务

│       ├── main.py              \# 服务入口

│       ├── routers/             \# API 端点路由

│       ├── models/              \# 数据库 ORM 模型

│       ├── schemas/             \# Pydantic 输入输出契约

│       └── workers/             \# Celery 异步任务处理器

├── packages/

│   ├── engine/                  \# 核心视频生成与合成模块

│   │   ├── director/            \# AI Director 逻辑与 Prompts

│   │   ├── providers/           \# Video & Image 适配器 (fal, runway, etc.)

│   │   ├── audio/               \# TTS 与音频测速

│   │   └── composer/            \# FFmpeg 模版与构建器

│   └── shared/                  \# 跨端共享常量与类型

├── docker-compose.yml           \# 本地基础设施编排 (Postgres, Redis)

└── README.md

---

## 5\. MVP 分阶段实施路线图

* **阶段 1：核心管线验证 (Pipeline Spike \- 2天)**  
  - 编写单文件脚本，串联商品输入 $\\rightarrow$ LLM 分镜 $\\rightarrow$ TTS 生成 $\\rightarrow$ Keyframe $\\rightarrow$ I2V $\\rightarrow$ FFmpeg 拼接。  
  - 产出首个完整 15 秒 MP4 广告样片，验证质量与成本模型。  
* **阶段 2：服务化与任务调度 (FastAPI \+ Workers \- 3天)**  
  - 实现 Project CRUD 与分镜状态管理。  
  - 搭建 Redis 异步任务队列，支持单 Scene 异步轮询与重抽。  
* **阶段 3：前端工作台开发 (Next.js \- 3天)**  
  - 落地商品上传表单、3 套 Concept 选择卡片、分镜逐帧审查看板、播放与下载页。  
* **阶段 4：商业化增强与发布 (2天)**  
  - 接入用户鉴权 (Clerk / Supabase Auth)、额度扣减系统与 Stripe 支付。

---

## 6\. 生产环境避坑与成本控制策略

1. **分级确认，防止额度暴击**：  
   - 严禁用户点击一次就立刻烧钱生成 4 段视频。严格推行「脚本确认 $\\rightarrow$ 关键帧确认 $\\rightarrow$ 单独/批量视频生成」三级确认体系。  
2. **异步回调优先于死循环轮询**：  
   - 优先使用 Video Provider 的 Webhook 回调通知状态，轮询设置指数退避重试（Exponential Backoff），防止 API 速率受限。  
3. **分片视频缓存机制**：  
   - Scene 的 Keyframe URL \+ Motion Prompt 作为唯一哈希键。如果用户重新编辑了其他镜头，未改动的镜头直接复用本地/R2 缓存切片，大幅降低重复渲染成本。

&nbsp;