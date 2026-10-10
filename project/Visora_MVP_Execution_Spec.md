# Visora MVP 执行契约与落地验收规范 (Execution Spec)

> **目标定位**：本文档为 Visora MVP 开发的唯一执行与验收准绳。约定单商品、9:16、单语言、3–4 个场景、约 15 秒广告短视频的完整数据契约、计算规则、状态转移与降级方案。

---

## 1\. MVP 交付范围与验收准则 (DoD)

### 1.1 基础交付参数

* **画幅与分辨率**：严格锁定 **9:16 (1080 × 1920\)**，帧率固定为 **30 fps**，像素格式 `yuv420p`。  
* **首发语言**：单一语言（首版采用**英文 English**，可配置支持中文）。  
* **镜头数量**：**固定 4 个场景**（Scene 1: 痛点/场景引入 $\\rightarrow$ Scene 2: 产品外观亮相 $\\rightarrow$ Scene 3: 核心卖点特写 $\\rightarrow$ Scene 4: 品牌结语与 CTA）。  
* **目标总时长与公差**：  
  * **目标时长**：15.0 秒。  
  * **允许公差**：**±1.0 秒（即 14.0s \~ 16.0s 均为合格交付）**。

### 1.2 合格成片验收条件 (Definition of Done)

1. **商品几何与文字保真**：商品包装轮廓无畸变，Logo 与主要印刷文字在关键帧及视频运动中无融化、无乱码（达到商业展示可用标准）。  
2. **声画卡点与留白**：4 个镜头的配音完整清晰播放，句首句尾不得被转场吞字；每个镜头结尾保留 200ms \~ 400ms 的视听呼吸留白。  
3. **音画与混音质量**：画面无明显马赛克与编码撕裂；人声清晰饱满；BGM 在人声响起时平滑下潜（-15dB），人声结束后 300ms 内平滑恢复。  
4. **单镜头可维护性**：在前端单独对 Scene 2 执行“重抽视频”，耗时不超过服务商单次生成时长，且重抽后能自动重新触发 FFmpeg 组装，不破坏其他 3 个场景。

---

## 2\. 时长调度算法与音频优先预算规则

严禁视频镜头无上限延长。系统通过\*\*“预算约束 \+ 双向适配”\*\*确保严格控制在 14–16 秒。

### 2.1 基础配额划分 (15.0s 标称)

* **Scene 1 (Hook)**: 3.0s  
* **Scene 2 (Product Hero)**: 4.0s  
* **Scene 3 (Feature Macro)**: 4.5s  
* **Scene 4 (Brand CTA)**: 3.5s

### 2.2 配音字数预约束与超长改写策略

1. **Director 字数熔断**：  
   * 英文语速按标称 $2.5 \\sim 2.8$ 词/秒计算（中文 3.5 字/秒）。  
   * AI Director 生成台词时，硬性限制：3s 镜头 $\\le 7$ 词；4s 镜头 $\\le 10$ 词；4.5s 镜头 $\\le 11$ 词。  
2. **超长兜底策略**：  
   * 实际生成 TTS 后，通过 `ffprobe` 获取音频实际时长 $T\_{\\text{audio}}$。  
   * **情况 A（轻度超长 $\\le 0.4s$）**：若 $T\_{\\text{audio}} \+ 0.3s \> T\_{\\text{scene}}$，且未超过相邻镜头缓冲，自动微调镜头时长，只要总时长在 $\[14.0s, 16.0s\]$ 内则放行。  
   * **情况 B（重度超长 $\> 0.4s$）**：自动触发 LLM 缩写任务（Condense Prompt），要求压缩 25% 字数，重新生成 TTS，**绝不允许无限顺延镜头时长**。  
3. **无配音镜头处理**：  
   * 若用户选择无配音或纯音乐镜头，该镜头时长严格锁定为基准配额时长（如 3.5s），BGM 保持全音量播放。

### 2.3 转场与模型步长适配

1. **转场重叠补偿**：  
   * 当使用 $0.3s$ 交叉溶解（`xfade=dissolve`）时，两镜头重叠耗费 $0.3s$。  
   * 合成公式： $$T\_{\\text{final}} \= \\sum\_{i=1}^{4} T\_{\\text{clip\_i}} \- (4 \- 1\) \\times 0.3$$  
   * 调度器在为每个镜头定长时，会自动补入 $0.3s$ 的预留冗余。  
2. **供应商固定步长裁剪 (Trimming)**：  
   * 现阶段主流 I2V 模型（如 Kling、Luma、Runway）通常以固定的 5.0 秒为步长输出。  
   * **裁剪规则**：无论生成出来的是 5.0s 还是 4.0s，FFmpeg 统一按照算定的目标时长 $T\_{\\text{target}}$ 进行精准 Trim：  
     - 若运镜平稳，默认保留 `[0.0, T_target]`；  
     - 若模型前 0.5s 存在起始伪影，选取 `[0.5, 0.5 + T_target]`。

---

## 3\. 字幕时序与生成规范

* **首版方案**：采用**句级字幕（Sentence-level Subtitles）**，不引入逐字跑马灯。  
* **时间戳生成逻辑**：  
  * 以各 Scene 的配音音频作为基准。  
  * `subtitle.start` \= 该 Scene 在总时间轴上的起点 $T\_{\\text{start}} \+ 0.15s$。  
  * `subtitle.end` \= `subtitle.start` \+ $T\_{\\text{audio}}$。  
* **边界越界校验**：  
  * 强制校验：`subtitle.end` 必须 $\\le T\_{\\text{next\_scene\_start}} \- 0.2s$。若越界，强制截断至当前镜头切点前 0.2s，保证字幕绝不串入下一镜头。

---

## 4\. 任务状态机、版本控制与级联失效规则

### 4.1 核心状态定义

* **Project**: `DRAFT` $\\rightarrow$ `CONCEPT_READY` $\\rightarrow$ `STORYBOARD_CONFIRMED` $\\rightarrow$ `PROCESSING` $\\rightarrow$ `COMPLETED` / `FAILED`  
* **Scene**: `PENDING` $\\rightarrow$ `KEYFRAME_GENERATING` $\\rightarrow$ `KEYFRAME_READY` $\\rightarrow$ `VIDEO_GENERATING` $\\rightarrow$ `VIDEO_READY` $\\rightarrow$ `FAILED`  
* **Job**: `QUEUED` $\\rightarrow$ `RUNNING` $\\rightarrow$ `SUCCESS` $\\rightarrow$ `FAILED` $\\rightarrow$ `CANCELLED`

### 4.2 级联失效规则 (Cascading Invalidation)

修改不同层级的内容，触发精准的受限失效，防止不必要的重新计费：

| 用户操作 | 影响范围 | 失效与保留规则 |
| :---- | :---- | :---- |
| **修改商品主图或全局卖点** | 全局 | 所有 Concepts、Storyboard、Keyframes、Videos 全部作废，项目版本升号 (v1 $\\rightarrow$ v2)。 |
| **修改某个 Scene 的台词** | 单镜头局部 | **仅**重新生成该 Scene 的 TTS 音频与字幕；**保留**现存已生成的 Keyframe 与 Video 切片，重新触发 FFmpeg 对齐合成。 |
| **修改某个 Scene 的 Keyframe 提示词** | 单镜头局部 | 重新生成 Keyframe；原 Video 标记为 `OUTDATED`（不自动删除），提示用户是否基于新帧重抽视频。 |
| **点击“单镜头重抽视频 (Reroll Video)”** | 单镜头局部 | 复用已有 Keyframe 与音频，仅向 Video Provider 提交该镜头的新生成任务，完成后触发局部切片替换与整体合成。 |

### 4.3 任务幂等性与防重复生成

* **Job 指纹计算**： $$\\text{Fingerprint} \= \\text{SHA256}(\\text{SceneID} \+ \\text{ModelName} \+ \\text{KeyframeURL} \+ \\text{MotionPrompt} \+ \\text{ParamsHash})$$  
* 后端收到请求时比对 Redis 中的 Job 指纹。若存在相同且处于 `QUEUED` 或 `RUNNING` 的任务，直接返回现有 Job ID，拒绝重复扣费/调用。

---

## 5\. 统一 Provider 接口规范与错误字典

from abc import ABC, abstractmethod

from pydantic import BaseModel

from typing import Optional, Dict, Any

from enum import Enum

&nbsp;

class ProviderErrorCode(str, Enum):

&nbsp;&nbsp;&nbsp;&nbsp;AUTH\_INVALID \= "AUTH\_INVALID"

&nbsp;&nbsp;&nbsp;&nbsp;RATE\_LIMITED \= "RATE\_LIMITED"

&nbsp;&nbsp;&nbsp;&nbsp;CONTENT\_FLAGGED \= "CONTENT\_FLAGGED"

&nbsp;&nbsp;&nbsp;&nbsp;TIMEOUT \= "TIMEOUT"

&nbsp;&nbsp;&nbsp;&nbsp;UPSTREAM\_UNAVAILABLE \= "UPSTREAM\_UNAVAILABLE"

&nbsp;&nbsp;&nbsp;&nbsp;MALFORMED\_OUTPUT \= "MALFORMED\_OUTPUT"

&nbsp;

class ProviderCapabilities(BaseModel):

&nbsp;&nbsp;&nbsp;&nbsp;supported\_durations: list\[float\]  \# e.g. \[5.0, 10.0\]

&nbsp;&nbsp;&nbsp;&nbsp;supported\_aspect\_ratios: list\[str\] \# \["9:16", "16:9", "1:1"\]

&nbsp;&nbsp;&nbsp;&nbsp;supports\_webhook: bool

&nbsp;&nbsp;&nbsp;&nbsp;max\_concurrent\_jobs: int

&nbsp;

class BaseImageProvider(ABC):

&nbsp;&nbsp;&nbsp;&nbsp;@abstractmethod

&nbsp;&nbsp;&nbsp;&nbsp;async def generate\_keyframe(

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;self,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;prompt: str,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;product\_image\_url: str,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;aspect\_ratio: str \= "9:16"

&nbsp;&nbsp;&nbsp;&nbsp;) \-\> str:

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"""返回生成的广告级关键帧图片可访问 URL"""

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pass

&nbsp;

class BaseVideoProvider(ABC):

&nbsp;&nbsp;&nbsp;&nbsp;capabilities: ProviderCapabilities

&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;@abstractmethod

&nbsp;&nbsp;&nbsp;&nbsp;async def submit\_i2v(

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;self,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;keyframe\_url: str,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;motion\_prompt: str,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;duration: float,&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;aspect\_ratio: str \= "9:16",

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;webhook\_url: Optional\[str\] \= None

&nbsp;&nbsp;&nbsp;&nbsp;) \-\> str:

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"""提交图生视频异步任务，返回外部 job\_id"""

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pass

&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;@abstractmethod

&nbsp;&nbsp;&nbsp;&nbsp;async def get\_job\_status(self, job\_id: str) \-\> Dict\[str, Any\]:

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"""轮询查询任务状态，返回 status ('RUNNING' | 'COMPLETED' | 'FAILED') 及 video\_url"""

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pass

### 超时与退避控制

* **I2V 任务超时时间**：设置硬超时阈值为 **360 秒**。超过该时间标记为 `TIMEOUT` 并释放任务。  
* **轮询退避**：若无 Webhook，轮询初始间隔为 3.0s，每次乘以 1.5，最大封顶 12.0s。

---

## 6\. 商品保真验收与双轨降级机制

为防止 AI 视频模型将商品瓶身字体、商标线条破坏，制定以下保真策略：

### 6.1 保真度分类标准

* **第一类：刚性保护区（Rigid Zone）**：商品 Logo、标签文字、表盘刻度、核心包装形状。此区域不得出现任何形变、溶解、模糊或字母异构。  
* **第二类：柔性动态区（Dynamic Zone）**：背景光影、景深光斑、烟雾/水雾、相机运动造成的视角平移。

### 6.2 降级方案 (Fallback Protocol)

如果选定的 Video Provider 在生成包含复杂文字的商品特写时发生字符融化，触发自动/手动降级：

1. **Primary 链路 (纯 I2V)**：  
   - Prompt 强制增加权重约束：`"rigid product, sharp static label, do not deform, cinematic camera motion only"`。  
2. **Fallback 降级链路 (2.5D 静态前景分层贴片)**：  
   - 将抠出的纯净透明通道商品图作为独立图层（Foreground Overlay）。  
   - 让 Video Provider 仅以 Keyframe 背景为基底生成动态背景视频（Background Motion）。  
   - 在 FFmpeg 合成阶段，通过 `overlay` 滤镜将高分辨率未失真商品图层强制复合到视频前方，辅以微小的缓动平移/缩放（Ken Burns 效果）。  
   - **效果保证**：商标文字 100% 绝对清晰，背景具备动态光影商业感。

---

## 7\. 首选供应商与成本预算基准

MVP 首发锁定单套可用配置，杜绝多账号环境混淆：

* **图像抠图**：本地 `rembg`（快速验证）或 BiRefNet API。  
* **关键帧打光生成**：`fal.ai` 托管的 `flux/dev`（或 `flux-realism`）。  
* **视频 I2V 生成**：`fal.ai` 托管的 `kling-video/v1.5/pro/image-to-video`（或本地 Wan2.1）。  
* **配音 TTS**：OpenAI `tts-1`（声音选用 `onyx` 质感男声或 `nova` 活力女声）。  
* **成本上限基准**：  
  - 4 张 Flux 关键帧：$\\approx $0.10$  
  - 4 段 Kling 5s 视频：$\\approx $0.80 \\sim $1.00$  
  - TTS 与 LLM Director：$\\approx $0.03$  
  - **单条视频初始生成成本控制在 $1.20 内**；单镜头重抽成本控制在 $0.25 内。  
* **凭据隔离**：所有 API Key 仅保存在本地 `.env.local` 中，禁止写入代码库与任何文档。

---

## 8\. FFmpeg 混音与合成落地参数

必须在本地验证通过的精确 FFmpeg 执行模版：

\# 智能音频闪避 (Audio Ducking) 滤镜示例：

\# \[1:a\] 为配音人声，\[2:a\] 为背景音乐。当人声发声时，BGM 音量自动衰减到原音量的 20%

ffmpeg \-y \\

&nbsp;&nbsp;\-f concat \-safe 0 \-i video\_list.txt \\

&nbsp;&nbsp;\-i combined\_voiceover.mp3 \\

&nbsp;&nbsp;\-i background\_music.mp3 \\

&nbsp;&nbsp;\-filter\_complex \\

&nbsp;&nbsp;"\[2:a\]volume=0.4\[bgm\]; \\

&nbsp;&nbsp;&nbsp;\[bgm\]\[1:a\]sidechaincompress=threshold=0.12:ratio=4:attack=50:release=300\[ducked\_bgm\]; \\

&nbsp;&nbsp;&nbsp;\[1:a\]\[ducked\_bgm\]amix=inputs=2:duration=first:dropout\_transition=2\[audio\_out\]" \\

&nbsp;&nbsp;\-map 0:v \-map "\[audio\_out\]" \\

&nbsp;&nbsp;\-c:v libx264 \-pix\_fmt yuv420p \-c:a aac \-b:a 192k \\

&nbsp;&nbsp;\-t 15.0 final\_output.mp4

&nbsp;