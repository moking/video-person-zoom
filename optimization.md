# Optimization & Feature Log (Today)

This document lists all new features and optimizations implemented today, focused on accuracy improvements (false-positive reduction) and performance improvements (parallel speed-up).

**Maintenance / 文档维护**

- When you add or change tracking, sock-color, ball-gating, or parallel behavior in `video_person_zoom.py`, **update this file in the same change**: extend the English and Chinese sections, adjust the CLI tables if new flags appear, and add TOC links.  
- 在 `video_person_zoom.py` 中新增或修改跟拍、球袜色、近球门控、并行等行为时，**请在同一提交中同步更新本文件**：补充中英文条目、若有新参数则更新 CLI 表，并维护目录链接。

## Table of Contents

- [CLI quick reference (English)](#cli-quick-ref-en)
- [Feature log (feature.md)](#feature-log-featuremd)
- [English](#english)
  - [EN-1. Sock-color ROI redesign (reduce shoe-color confusion)](#en-1-sock-color-roi-redesign-reduce-shoe-color-confusion)
  - [EN-2. Strict sock-color standard: knee upper/lower dual-band matching](#en-2-strict-sock-color-standard-knee-upperlower-dual-band-matching)
  - [EN-3. Stricter HSV color definitions for sock detection](#en-3-stricter-hsv-color-definitions-for-sock-detection)
  - [EN-4. Runtime switch for strict vs relaxed sock detection](#en-4-runtime-switch-for-strict-vs-relaxed-sock-detection)
  - [EN-5. Print active sock detection standard at runtime](#en-5-print-active-sock-detection-standard-at-runtime)
  - [EN-6. Ball-proximity gated clip output (target must be near ball)](#en-6-ball-proximity-gated-clip-output-target-must-be-near-ball)
  - [EN-7. Configurable near-ball distance threshold](#en-7-configurable-near-ball-distance-threshold)
  - [EN-8. Anti-drift protections to avoid wrong-player clips](#en-8-anti-drift-protections-to-avoid-wrong-player-clips)
  - [EN-9. Consecutive-frame confirmation before triggering clips](#en-9-consecutive-frame-confirmation-before-triggering-clips)
  - [EN-10. Optional per-frame sock-color recheck switch](#en-10-optional-per-frame-sock-color-recheck-switch)
  - [EN-11. Time-chunk parallel processing with overlap](#en-11-time-chunk-parallel-processing-with-overlap)
  - [EN-12. New parallel execution policy (auto/off/force)](#en-12-new-parallel-execution-policy-autoffforce)
  - [EN-13. Runtime print of actual parallel decision](#en-13-runtime-print-of-actual-parallel-decision)
  - [EN-14. Boundary overlap deduplication by absolute timestamps](#en-14-boundary-overlap-deduplication-by-absolute-timestamps)
  - [EN-15. Orange pitch-line rejection for sock color](#en-15-orange-pitch-line-rejection-for-sock-color)
  - [EN-16. Skin-tone exclusion for sock color ratio](#en-16-skin-tone-exclusion-for-sock-color-ratio)
  - [Cross Reference to Chinese Section](#cross-reference-to-chinese-section)
- [CLI 快速参考（中文）](#cli-quick-ref-zh)
- [中文](#中文)
  - [ZH-1. 球袜 ROI 重构（降低球鞋颜色误判）](#zh-1-球袜-roi-重构降低球鞋颜色误判)
  - [ZH-2. 严格球袜标准：膝上/膝下双带同时命中](#zh-2-严格球袜标准膝上膝下双带同时命中)
  - [ZH-3. 球袜 HSV 颜色定义收紧](#zh-3-球袜-hsv-颜色定义收紧)
  - [ZH-4. 严格/宽松球袜识别开关](#zh-4-严格宽松球袜识别开关)
  - [ZH-5. 运行时打印当前球袜检测标准](#zh-5-运行时打印当前球袜检测标准)
  - [ZH-6. 片段输出增加“近球/持球”门控](#zh-6-片段输出增加近球持球门控)
  - [ZH-7. 可配置近球距离阈值](#zh-7-可配置近球距离阈值)
  - [ZH-8. 防漂移机制（减少错人片段）](#zh-8-防漂移机制减少错人片段)
  - [ZH-9. 连续帧确认后再触发片段](#zh-9-连续帧确认后再触发片段)
  - [ZH-10. 可选逐帧球袜复核开关](#zh-10-可选逐帧球袜复核开关)
  - [ZH-11. 时间分片并行处理 + overlap](#zh-11-时间分片并行处理--overlap)
  - [ZH-12. 并行策略开关（auto/off/force）](#zh-12-并行策略开关autooffforce)
  - [ZH-13. 运行时打印并行实际决策](#zh-13-运行时打印并行实际决策)
  - [ZH-14. overlap 边界结果去重](#zh-14-overlap-边界结果去重)
  - [ZH-15. 橙色目标：球场标线误判抑制](#zh-15-橙色目标球场标线误判抑制)
  - [ZH-16. 肤色排除：降低小腿颜色误判球袜](#zh-16-肤色排除降低小腿颜色误判球袜)
  - [交叉引用到英文部分](#交叉引用到英文部分)

---

## Feature log (feature.md)

- Feature-level change log: [`feature.md`](./feature.md)
- For user-visible capability additions, append to `feature.md` and link back here when optimization details exist.

---

<a id="cli-quick-ref-en"></a>

## CLI quick reference (English)

| Parameter | Default | Mode | Purpose / when to tune |
|-----------|---------|------|------------------------|
| `--sock-color` | *(required for sock tracking)* | `-n` **or** `--sock-color` | Target sock color token (`red`, `orange`, …). |
| `--sock-min-ratio` | `0.22` | `--sock-color` | Minimum color hit ratio in sock ROI; raise if too many false positives. |
| `--sock-strict-mode` | `on` | `--sock-color` | `on`: knee upper **and** lower 5cm bands must match ([EN-2](#en-2-strict-sock-color-standard-knee-upperlower-dual-band-matching)). `off`: single band ([EN-4](#en-4-runtime-switch-for-strict-vs-relaxed-sock-detection)). |
| `--sock-skin-exclude` | `strong` | `--sock-color` | Skin exclusion mode: `off`/`on`/`strong`; `strong` uses wider skin mask to further suppress lower-leg skin false positives ([EN-16](#en-16-skin-tone-exclusion-for-sock-color-ratio)). |
| `--sock-recheck-every-frame` | `on` | `--sock-color` | Per-frame sock recheck to limit tracker drift ([EN-10](#en-10-optional-per-frame-sock-color-recheck-switch)). |
| `--ball-near-meter` | `1.0` | `-n` or `--sock-color` | Near-ball distance in meters (approx. from bbox scale) ([EN-7](#en-7-configurable-near-ball-distance-threshold)). |
| `--near-ball-streak-frames` | `2` | `-n` or `--sock-color` | Consecutive frames required before starting a clip ([EN-9](#en-9-consecutive-frame-confirmation-before-triggering-clips)). |
| `--parallel-mode` | `auto` | Tracking | `auto` / `off` / `force` parallel chunk policy ([EN-12](#en-12-new-parallel-execution-policy-autoffforce)). |
| `--parallel-chunks` | `0` | Tracking | `0` = derive chunk count from mode + host; `1` = no time-chunk parallelism ([EN-11](#en-11-time-chunk-parallel-processing-with-overlap)). |
| `--chunk-overlap-sec` | `-1` (auto) | Parallel chunks | `-1` uses one recognition window (~`-d` / segment length) as overlap ([EN-11](#en-11-time-chunk-parallel-processing-with-overlap)). |
| `-d` / `--duration` | `10` (tracking default if omitted) | `-n` or `--sock-color` | Per-segment output length; also used as default overlap when `--chunk-overlap-sec=-1`. |
| *(built-in, no flag)* | always on for `orange` | `--sock-color orange` | After HSV ratio passes, geometry rejects masks that look like horizontal pitch paint ([EN-15](#en-15-orange-pitch-line-rejection-for-sock-color)). |

**Runtime notes**

- Active sock policy and parallel decision are printed to stderr when applicable ([EN-5](#en-5-print-active-sock-detection-standard-at-runtime), [EN-13](#en-13-runtime-print-of-actual-parallel-decision)).
- If both `-w` and `-d` are set (pre-trim window), time-chunk parallelism is disabled to avoid double windowing ([EN-11](#en-11-time-chunk-parallel-processing-with-overlap)).

**Cross-links**

- Narrative detail (English): [English](#english)
- Same tables in Chinese: [CLI 快速参考（中文）](#cli-quick-ref-zh)

---

## English

Parameter cheat sheet: [CLI quick reference (English)](#cli-quick-ref-en)

### EN-1. Sock-color ROI redesign (reduce shoe-color confusion)
- Replaced lower-leg sampling with knee-centered sampling to avoid shoe-dominant areas.
- Current sock ROI is centered around knee geometry estimated from person bbox proportions.

### EN-2. Strict sock-color standard: knee upper/lower dual-band matching
- Added strict dual-band logic:
  - upper band: approximately knee - 5cm to knee
  - lower band: approximately knee to knee + 5cm
- A detection is valid only when **both** bands match target color (AND rule).

### EN-3. Stricter HSV color definitions for sock detection
- Tightened HSV ranges for all supported sock colors (`red/blue/green/yellow/orange/purple/pink/white/black`).
- Goal: reduce false positives caused by shoes, grass reflections, and lighting artifacts.

### EN-4. Runtime switch for strict vs relaxed sock detection
- Added `--sock-strict-mode on|off`.
- `on` (default): dual-band strict matching.
- `off`: single knee-centered band matching.

### EN-5. Print active sock detection standard at runtime
- Program now prints active sock detection policy in runtime logs:
  - strict/relaxed mode
  - target sock color
  - active min ratio rule.

### EN-6. Ball-proximity gated clip output (target must be near ball)
- Clip generation is no longer triggered by target lock alone.
- Clips are produced only when the target is valid **and** either:
  - in possession-like zone, or
  - within configured near-ball distance.

### EN-7. Configurable near-ball distance threshold
- Added `--ball-near-meter` (default `1.0`).
- Distance threshold is converted to pixels using player bbox height as scale reference.

### EN-8. Anti-drift protections to avoid wrong-player clips
- Introduced per-frame `target_valid_this_frame` guard.
- In sock mode, invalid color recheck can invalidate current target frame.
- Reference box updates (`locked_ref_xyxy` / `last_box`) now happen only for valid target frames.

### EN-9. Consecutive-frame confirmation before triggering clips
- Added near-ball streak logic to avoid one-frame trigger noise.
- Segment starts only after consecutive qualified frames threshold is met.

### EN-10. Optional per-frame sock-color recheck switch
- Added `--sock-recheck-every-frame on|off` (default `on`).
- `on`: continuously verifies target sock color on each valid frame.
- `off`: looser behavior for higher recall.

### EN-11. Time-chunk parallel processing with overlap
- Added tracking-time chunk parallelism via process-level execution.
- Video is split into multiple time chunks and processed concurrently.
- Neighbor chunks support overlap to reduce boundary misses.
- Added:
  - `--parallel-chunks`
  - `--chunk-overlap-sec`

### EN-12. New parallel execution policy (auto/off/force)
- Added `--parallel-mode auto|off|force` (default `auto`).
- `auto`: chooses chunk count based on host CPU and CUDA availability.
- `off`: disables parallel chunk processing.
- `force`: enables parallel chunk processing even when CUDA is available.

### EN-13. Runtime print of actual parallel decision
- Program now prints effective parallel decision:
  - selected mode
  - final chunk count
  - overlap seconds.

### EN-14. Boundary overlap deduplication by absolute timestamps
- Chunk-generated segment names now include absolute timeline timestamps.
- Added dedup logic by `[start, end]` time signature to avoid duplicate clips from overlap area.

### EN-15. Orange pitch-line rejection for sock color
- **Problem:** With `--sock-color orange`, bright orange **field markings** can pass the same HSV band as socks, especially when a player **steps across** a line and the knee ROI intersects the paint.
- **Mitigation (code, automatic for `orange` only):** After each knee band meets the orange HSV ratio, the binary mask is analyzed. Matches are rejected when the mask looks like a **wide, thin horizontal stripe**, or when **one or a few rows** hold most orange pixels (typical line geometry vs. sock fabric blob).
- Applies in both **strict** (dual band) and **relaxed** (single band) sock modes. No CLI switch yet; extend this doc if a toggle is added later.

### EN-16. Skin-tone exclusion for sock color ratio
- **Problem:** Exposed lower-leg skin can occasionally satisfy target sock HSV ranges, especially under warm lighting and compression artifacts.
- **Mitigation:** Added `--sock-skin-exclude off|on|strong` (default `strong`). In sock ROI/bands, likely skin-tone pixels are masked out first, then sock-color ratio is computed on remaining valid pixels.
- **Strong mode:** `strong` expands the skin HSV exclusion envelope and is more aggressive for hard scenes.
- **Impact:** Reduces false positives where bare skin is mistaken for sock color (notably orange/yellow/red-like ranges).
- Works in both strict and relaxed sock modes.

### Cross Reference to Chinese Section
- Chinese mirror for this section: [Jump to 中文](#中文)
- CLI quick reference (Chinese): [CLI 快速参考（中文）](#cli-quick-ref-zh)
- Orange pitch-line guard (Chinese): [ZH-15](#zh-15-橙色目标球场标线误判抑制)

---

<a id="cli-quick-ref-zh"></a>

## CLI 快速参考（中文）

| 参数 | 默认值 | 适用模式 | 用途 / 调参建议 |
|------|--------|----------|-----------------|
| `--sock-color` | *跟拍需指定* | `-n` **或** `--sock-color` | 目标球袜颜色（如 `red`、`orange`）。 |
| `--sock-min-ratio` | `0.22` | `--sock-color` | ROI 内目标色最小占比；误检多可适当调高。 |
| `--sock-strict-mode` | `on` | `--sock-color` | `on`：膝上+膝下 5cm 双带都命中（[ZH-2](#zh-2-严格球袜标准膝上膝下双带同时命中)）；`off`：单带（[ZH-4](#zh-4-严格宽松球袜识别开关)）。 |
| `--sock-skin-exclude` | `strong` | `--sock-color` | 肤色排除模式：`off`/`on`/`strong`；`strong` 使用更宽肤色范围，进一步降低小腿肤色误判（[ZH-16](#zh-16-肤色排除降低小腿颜色误判球袜)）。 |
| `--sock-recheck-every-frame` | `on` | `--sock-color` | 逐帧复核袜色，抑制跟丢漂移（[ZH-10](#zh-10-可选逐帧球袜复核开关)）。 |
| `--ball-near-meter` | `1.0` | `-n` 或 `--sock-color` | 近球距离阈值（米，由框高近似换算）（[ZH-7](#zh-7-可配置近球距离阈值)）。 |
| `--near-ball-streak-frames` | `2` | `-n` 或 `--sock-color` | 连续满足近球条件后才触发片段（[ZH-9](#zh-9-连续帧确认后再触发片段)）。 |
| `--parallel-mode` | `auto` | 跟拍 | `auto` / `off` / `force` 并行策略（[ZH-12](#zh-12-并行策略开关autooffforce)）。 |
| `--parallel-chunks` | `0` | 跟拍 | `0` 按策略与主机自动分片；`1` 不分片（[ZH-11](#zh-11-时间分片并行处理--overlap)）。 |
| `--chunk-overlap-sec` | `-1`（自动） | 分片并行 | `-1` 时 overlap 约等于识别窗口长度（与 `-d`/片段时长一致）（[ZH-11](#zh-11-时间分片并行处理--overlap)）。 |
| `-d` / `--duration` | 跟拍未写时默认 `10` | `-n` 或 `--sock-color` | 每段输出时长；`--chunk-overlap-sec=-1` 时亦作默认 overlap 基准。 |
| *内置，无参数* | 仅 `orange` 时启用 | `--sock-color orange` | HSV 占比通过后，用掩码几何排除横向球场标线（[ZH-15](#zh-15-橙色目标球场标线误判抑制)）。 |

**运行时说明**

- 球袜检测标准与并行决策会在 stderr 打印（[ZH-5](#zh-5-运行时打印当前球袜检测标准)、[ZH-13](#zh-13-运行时打印并行实际决策)）。
- 若同时使用 `-w` 与 `-d` 做时间窗预处理，会关闭时间分片并行，避免二次切窗（[ZH-11](#zh-11-时间分片并行处理--overlap)）。

**交叉引用**

- 英文版同表：[CLI quick reference (English)](#cli-quick-ref-en)
- 正文条目：[中文](#中文)

---

## 中文

参数速查表：[CLI 快速参考（中文）](#cli-quick-ref-zh)

### ZH-1. 球袜 ROI 重构（降低球鞋颜色误判）
- 将球袜采样区域从小腿下段改为膝盖附近，尽量避开球鞋主导区域。
- 当前球袜 ROI 基于人体框比例估计膝盖位置后取样。

### ZH-2. 严格球袜标准：膝上/膝下双带同时命中
- 新增严格双带判定：
  - 上带：约膝盖上 5cm 到膝盖
  - 下带：约膝盖到膝盖下 5cm
- 只有两条带都命中目标颜色（AND）才算识别成功。

### ZH-3. 球袜 HSV 颜色定义收紧
- 对 `red/blue/green/yellow/orange/purple/pink/white/black` 的 HSV 区间进行收紧。
- 目标：降低鞋面颜色、草地反光、光照变化造成的误识别。

### ZH-4. 严格/宽松球袜识别开关
- 新增 `--sock-strict-mode on|off`。
- `on`（默认）：膝上/膝下双带严格命中。
- `off`：膝盖单带命中。

### ZH-5. 运行时打印当前球袜检测标准
- 程序运行日志会打印当前球袜识别标准：
  - 严格/宽松模式
  - 目标颜色
  - 实际使用阈值规则。

### ZH-6. 片段输出增加“近球/持球”门控
- 不再只要锁定目标就输出片段。
- 仅在“目标有效 + 持球或近球”时才触发片段输出。

### ZH-7. 可配置近球距离阈值
- 新增 `--ball-near-meter`（默认 `1.0`）。
- 通过球员框高度换算像素尺度来近似 1 米阈值。

### ZH-8. 防漂移机制（减少错人片段）
- 新增逐帧 `target_valid_this_frame` 校验。
- 在 sock 模式下可按当前帧复核袜色，不满足则本帧目标无效。
- 仅在目标有效帧才更新 `locked_ref_xyxy/last_box`，降低漂移积累。

### ZH-9. 连续帧确认后再触发片段
- 加入 near-ball 连续帧计数，避免单帧噪声误触发。
- 达到连续帧阈值后才开始输出片段。

### ZH-10. 可选逐帧球袜复核开关
- 新增 `--sock-recheck-every-frame on|off`（默认 `on`）。
- `on`：逐帧复核球袜颜色（更稳健）。
- `off`：更宽松，可能提高召回但增加误检风险。

### ZH-11. 时间分片并行处理 + overlap
- 新增按时间分片并行处理（进程级并行）。
- 将视频切为多段并发处理，并支持相邻分片 overlap 防止边界漏检。
- 新增参数：
  - `--parallel-chunks`
  - `--chunk-overlap-sec`

### ZH-12. 并行策略开关（auto/off/force）
- 新增 `--parallel-mode auto|off|force`（默认 `auto`）。
- `auto`：根据主机 CPU 与 CUDA 状态自动决定并行度。
- `off`：关闭并行分片。
- `force`：即使可用 CUDA 也强制并行分片。

### ZH-13. 运行时打印并行实际决策
- 程序会输出并行实际配置：
  - mode
  - chunks
  - overlap 秒数。

### ZH-14. overlap 边界结果去重
- 分片输出片段命名改为包含绝对时间戳。
- 基于片段 `[start,end]` 时间签名做去重，避免 overlap 区重复片段。

### ZH-15. 橙色目标：球场标线误判抑制
- **问题：** `--sock-color orange` 时，球场 **橙色油漆标线** 与球袜在 HSV 上易混淆；球员 **跨过橙线** 时，膝部 ROI 常与标线相交，误检更明显。
- **处理（代码内置，仅 `orange`）：** 在每个膝带满足橙色占比后，对二值掩码做形状判断；若呈 **横向宽、纵向薄** 的条带，或 **少数几行集中了绝大部分橙色像素**（典型标线而非袜筒布面），则判定为误检并拒绝。
- **严格 / 宽松** 两种球袜模式均生效。当前无独立 CLI 开关；若后续增加开关，请同步更新本表与 [CLI quick reference (English)](#cli-quick-ref-en)。

### ZH-16. 肤色排除：降低小腿颜色误判球袜
- **问题：** 裸露小腿在暖色光照或压缩失真下，可能落入目标球袜 HSV 区间，导致把肤色当作袜色。
- **处理：** 新增 `--sock-skin-exclude off|on|strong`（默认 `strong`）。在球袜 ROI/双带内先剔除疑似皮肤像素，再用剩余像素计算球袜命中率。
- **强排除档位：** `strong` 会扩大肤色剔除 HSV 范围，适合暖光、压缩重、误检顽固场景。
- **效果：** 可降低小腿肤色被识别成球袜颜色的误检（对 orange/yellow/red 等更敏感颜色尤为有用）。
- 严格与宽松球袜模式均生效。

### 交叉引用到英文部分
- 英文镜像内容： [Jump to English](#english)
- 英文 CLI 快速表：[CLI quick reference (English)](#cli-quick-ref-en)
- 橙色标线抑制（英文）：[EN-15](#en-15-orange-pitch-line-rejection-for-sock-color)
- 肤色排除（英文）：[EN-16](#en-16-skin-tone-exclusion-for-sock-color-ratio)

