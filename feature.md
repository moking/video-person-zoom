# Feature Log

This document tracks user-visible feature additions and behavior changes.

**Maintenance / 文档维护**

- When adding or changing user-visible capabilities in `video_person_zoom.py`, update this file in the same change.
- 对 `video_person_zoom.py` 的用户可见功能新增/变更，请在同一改动中同步更新本文件。
- Optimization-only tuning (accuracy/performance hardening without new capability) should go to [`optimization.md`](./optimization.md).
- 仅优化类改动（非新能力）请写入 [`optimization.md`](./optimization.md)。

## Table of Contents

- [Entry Template (English)](#entry-template-english)
- [Entry Template (中文)](#entry-template-中文)
- [English Entries](#english-entries)
- [中文条目](#中文条目)
- [Cross Reference](#cross-reference)

---

## Entry Template (English)

Use this format for each new feature entry (append-only):

```markdown
### FEAT-YYYYMMDD-N. Short title
- **Date**: YYYY-MM-DD
- **Scope**: CLI / Tracking / Output / Detection / UX
- **What changed**: ...
- **Why**: ...
- **CLI / API impact**: Added/changed flags, defaults, behavior notes.
- **Related optimization**: [optimization.md#...](./optimization.md#...)
```

## Entry Template (中文)

每次新增功能按以下格式追加（append-only）：

```markdown
### FEAT-YYYYMMDD-N. 标题
- **日期**: YYYY-MM-DD
- **范围**: CLI / 跟拍 / 输出 / 检测 / 交互
- **变更内容**: ...
- **变更原因**: ...
- **CLI / API 影响**: 新增/变更参数、默认值、行为说明。
- **关联优化**: [optimization.md#...](./optimization.md#...)
```

---

## English Entries

### FEAT-20260426-1. Sock-color target tracking mode
- **Date**: 2026-04-26
- **Scope**: Detection, Tracking, CLI
- **What changed**: Added `--sock-color` tracking mode as an alternative to jersey-number OCR tracking.
- **Why**: Support cases where jersey numbers are unclear but sock colors are identifiable.
- **CLI / API impact**: Added sock-color target flow and related thresholds/switches.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260426-2. Ball-proximity gated clip generation
- **Date**: 2026-04-26
- **Scope**: Tracking, Output
- **What changed**: Clip output now requires target validity plus near-ball/possession gating.
- **Why**: Prevent clips from being generated when target is not engaged around the ball.
- **CLI / API impact**: Added `--ball-near-meter` and `--near-ball-streak-frames`.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260426-3. Parallel time-chunk processing controls
- **Date**: 2026-04-26
- **Scope**: Performance, CLI
- **What changed**: Added time-chunk parallel processing with overlap and policy control.
- **Why**: Speed up long-video processing on CPU-heavy hosts while avoiding boundary misses.
- **CLI / API impact**: Added `--parallel-mode`, `--parallel-chunks`, `--chunk-overlap-sec`.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260427-4. Unlimited first-lock search by default (`--max-search-frames`)
- **Date**: 2026-04-27
- **Scope**: CLI, Tracking
- **What changed**: `--max-search-frames` default is now `0` (no frame cap until first successful lock); previously `2400`.
- **Why**: Long videos or late target appearance should not exit early unless the user opts in with a positive limit.
- **CLI / API impact**: Same flag; default only. Set a positive integer to restore bounded search.
- **Related optimization**: [EN-17 / ZH-17](./optimization.md#en-17-default-unlimited-first-lock-search-window)

### FEAT-20260429-5. `-w` anchors to clip start offset (default +10s)
- **Date**: 2026-04-29
- **Scope**: CLI, Output
- **What changed**: Changed `-w/--window` semantics from clip-center time to an anchor timestamp that is interpreted as 10 seconds after clip start by default.
- **Why**: Match expected manual clipping workflow where users provide a known event timestamp that should land near clip start, not in the middle.
- **CLI / API impact**: `-w` still requires `-d`, but now computes clip start as `start ~= w - min(10, d)` (with boundary clamping).
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-6. Target-head marker circle in output video
- **Date**: 2026-04-29
- **Scope**: Output, UX
- **What changed**: Added a small circle marker above the detected target player's head in rendered output frames.
- **Why**: Make the tracked target easier to distinguish quickly in crowded scenes.
- **CLI / API impact**: No new flags; marker is enabled by default for tracked target output.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-7. Export sock-match frames with cap
- **Date**: 2026-04-29
- **Scope**: CLI, Debugging, Output
- **What changed**: Added `--sock-save-frames` to save frames that satisfy sock-color matching as JPG images.
- **Why**: Help inspect and verify sock-color matching quality frame-by-frame.
- **CLI / API impact**: New `--sock-save-frames N` (default `0` off). Saves up to `N` images and then stops automatically.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-8. Visual marker on exported match frames
- **Date**: 2026-04-29
- **Scope**: Debugging, Output
- **What changed**: Exported match JPGs now draw a circle above the matched player and a bounding box around the player.
- **Why**: Make verification easier by showing exactly which player was judged as a match in each saved frame.
- **CLI / API impact**: No new flags; applies to frames exported via `--sock-save-frames`.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-9. Miss-based frame skipping control
- **Date**: 2026-04-29
- **Scope**: CLI, Tracking
- **What changed**: Added `--skip-seconds-on-miss` to skip a time span of frames after a miss (no target detected in current frame).
- **Why**: Improve throughput for football footage where scene changes are often limited over short intervals.
- **CLI / API impact**: New `--skip-seconds-on-miss` (default `0.2`, `0` disables).
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-10. Target-box overlay and distance-rule update
- **Date**: 2026-04-29
- **Scope**: Output, Tracking
- **What changed**: Replaced head-circle marker with target bounding box overlay in exported match frames and output video segments.
- **Why**: Box overlay is clearer for continuous target verification frame-by-frame.
- **CLI / API impact**: No new flags; visual marker now uses box only.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-11. Exported verify frames require target + near-ball
- **Date**: 2026-04-29
- **Scope**: Output, Debugging
- **What changed**: Tightened exported verification frame condition to require both target match (jersey or sock-color) and near-ball in the same frame.
- **Why**: Keep exported verification images aligned with actual clip-trigger criteria and reduce irrelevant debug frames.
- **CLI / API impact**: Reuses existing export flag; saved image names now use `target-match-nearball-*`.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-12. Output overlay box aligned with smoothed tracker
- **Date**: 2026-04-29
- **Scope**: Output, UX
- **What changed**: Output segment overlay now draws target box using the smoothed tracking box (same basis as crop follow), not raw per-frame detection box.
- **Why**: Keep on-screen box visually synchronized with camera follow and reduce perceived lag/misalignment.
- **CLI / API impact**: No new flags; behavior improvement in output overlay.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-13. Lower default miss-skip for higher recall
- **Date**: 2026-04-29
- **Scope**: CLI, Tracking
- **What changed**: Reduced default `--skip-seconds-on-miss` from `0.2` to `0.05`.
- **Why**: Decrease chance of missing short shooting moments while keeping light acceleration.
- **CLI / API impact**: Same flag; default is now `0.05`.
- **Related optimization**: See [`optimization.md`](./optimization.md).

### FEAT-20260429-14. Shot-priority recall controls
- **Date**: 2026-04-29
- **Scope**: CLI, Tracking
- **What changed**: Added shot-priority controls: `--ball-missing-grace-frames`, `--shot-relax-window-sec`, `--shot-relax-sock-delta`, `--shot-relax-ocr-delta`, and `--segment-extend-sec`.
- **Why**: Keep shot clips from being missed when ball detection flickers briefly and to extend clips smoothly during continuous shot actions.
- **CLI / API impact**: New optional tuning flags for near-ball grace, verification relaxation window, and post-trigger segment extension.
- **Related optimization**: See [`optimization.md`](./optimization.md).

## 中文条目

### FEAT-20260426-1. 球袜颜色目标跟拍模式
- **日期**: 2026-04-26
- **范围**: 检测、跟拍、CLI
- **变更内容**: 新增 `--sock-color` 跟拍能力，作为球衣号码 OCR 跟拍的替代路径。
- **变更原因**: 适配球衣号码不清晰、但球袜颜色可辨识的素材。
- **CLI / API 影响**: 增加球袜目标识别流程及相关阈值/开关。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260426-2. 近球/持球门控的片段输出
- **日期**: 2026-04-26
- **范围**: 跟拍、输出
- **变更内容**: 片段触发改为“目标有效 + 近球/持球”。
- **变更原因**: 避免目标不在球附近时仍输出无效片段。
- **CLI / API 影响**: 新增 `--ball-near-meter`、`--near-ball-streak-frames`。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260426-3. 分片并行处理控制
- **日期**: 2026-04-26
- **范围**: 性能、CLI
- **变更内容**: 新增带 overlap 的时间分片并行处理，并提供策略开关。
- **变更原因**: 在 CPU 主机上加速长视频处理并减少边界漏检。
- **CLI / API 影响**: 新增 `--parallel-mode`、`--parallel-chunks`、`--chunk-overlap-sec`。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260427-4. 首次锁定搜索默认不限制（`--max-search-frames`）
- **日期**: 2026-04-27
- **范围**: CLI、跟拍
- **变更内容**: `--max-search-frames` 默认值由 `2400` 改为 `0`（首次锁定前不限制搜索帧数）。
- **变更原因**: 长素材或目标较晚出现时不应默认因窗口过短而退出；需要时可显式设正整数。
- **CLI / API 影响**: 参数不变，仅默认值变化。
- **关联优化**: [EN-17 / ZH-17](./optimization.md#zh-17-首次锁定搜索窗口默认不限制)

### FEAT-20260429-5. `-w` 改为片段起点偏移锚点（默认 +10s）
- **日期**: 2026-04-29
- **范围**: CLI、输出
- **变更内容**: 将 `-w/--window` 语义从“片段中心时间”改为“片段起点后的锚点时间”，默认按起点后 10 秒解释。
- **变更原因**: 贴合手动截取习惯：用户给出的事件时间应更靠近片段前部，而不是居中。
- **CLI / API 影响**: `-w` 仍需配合 `-d`；起点计算改为 `start ~= w - min(10, d)`（并做边界夹取）。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-6. 输出视频增加目标头顶圆圈标记
- **日期**: 2026-04-29
- **范围**: 输出、交互体验
- **变更内容**: 在渲染输出帧中，为已识别目标球员的头顶增加小圆圈标记。
- **变更原因**: 在多人场景中更快区分当前跟拍目标，降低人工回看成本。
- **CLI / API 影响**: 无新增参数；默认对目标输出启用。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-7. 支持按上限导出袜色命中帧
- **日期**: 2026-04-29
- **范围**: CLI、调试、输出
- **变更内容**: 新增 `--sock-save-frames`，将满足球袜颜色条件的帧额外导出为 JPG 图片。
- **变更原因**: 便于逐帧核对袜色命中效果与排查漏检/误检。
- **CLI / API 影响**: 新增 `--sock-save-frames N`（默认 `0` 关闭）；达到 `N` 张后自动停止保存。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-8. 导出命中帧增加可视化标注
- **日期**: 2026-04-29
- **范围**: 调试、输出
- **变更内容**: 对导出的命中 JPG，新增目标头顶圆圈和目标框可视化标注。
- **变更原因**: 方便快速核验每张保存帧中被判定命中的具体球员。
- **CLI / API 影响**: 无新增参数；对 `--sock-save-frames` 导出的图片默认生效。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-9. 未命中跳帧控制参数
- **日期**: 2026-04-29
- **范围**: CLI、跟拍
- **变更内容**: 新增 `--skip-seconds-on-miss`，当当前帧未识别到目标时按秒数跳过后续帧。
- **变更原因**: 足球素材短时间画面变化通常有限，跳帧可减少无效推理、加快处理。
- **CLI / API 影响**: 新增 `--skip-seconds-on-miss`（默认 `0.2`，设 `0` 关闭）。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-10. 目标框可视化与距离规则更新
- **日期**: 2026-04-29
- **范围**: 输出、跟拍
- **变更内容**: 导出命中帧与输出片段均改为使用目标框标注，不再使用头顶圆圈。
- **变更原因**: 连续回看时，目标框更直观稳定，便于核验目标是否正确。
- **CLI / API 影响**: 无新增参数；可视化标注默认改为框。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-11. 导出验证帧改为“目标命中且近球”双条件
- **日期**: 2026-04-29
- **范围**: 输出、调试
- **变更内容**: 导出验证帧的保存条件收紧为“目标判定通过（号码或袜色）且近球”同时满足。
- **变更原因**: 保证导出图片与实际触发片段的业务条件一致，减少无效验证帧。
- **CLI / API 影响**: 复用现有导出参数；保存文件名更新为 `target-match-nearball-*`。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-13. 下调未命中跳帧默认值以提升召回
- **日期**: 2026-04-29
- **范围**: CLI、跟拍
- **变更内容**: `--skip-seconds-on-miss` 默认值由 `0.2` 下调到 `0.05`。
- **变更原因**: 降低短时关键动作（如射门）被跳过的风险，同时保留轻量加速。
- **CLI / API 影响**: 参数不变，默认值更新为 `0.05`。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

### FEAT-20260429-14. 射门优先召回控制参数
- **日期**: 2026-04-29
- **范围**: CLI、跟拍
- **变更内容**: 新增 `--ball-missing-grace-frames`、`--shot-relax-window-sec`、`--shot-relax-sock-delta`、`--shot-relax-ocr-delta`、`--segment-extend-sec`。
- **变更原因**: 在短时丢球检测或快速射门动作下减少漏检，并让触发后片段可连续延展。
- **CLI / API 影响**: 提供近球容忍、候选窗口阈值放宽、片段延长预算等可调能力。
- **关联优化**: 参见 [`optimization.md`](./optimization.md)。

## Cross Reference

- Optimization details: [`optimization.md`](./optimization.md)
- 优化细节：[`optimization.md`](./optimization.md)
