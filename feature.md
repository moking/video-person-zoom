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

## Cross Reference

- Optimization details: [`optimization.md`](./optimization.md)
- 优化细节：[`optimization.md`](./optimization.md)
