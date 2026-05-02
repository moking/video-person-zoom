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
  - [EN-17. Default unlimited first-lock search window](#en-17-default-unlimited-first-lock-search-window)
  - [EN-18. Sock-color recall hardening for strict mode](#en-18-sock-color-recall-hardening-for-strict-mode)
  - [EN-19. Near-ball gating made more tolerant](#en-19-near-ball-gating-made-more-tolerant)
  - [EN-20. Zoom-in secondary verification for sock-color hits](#en-20-zoom-in-secondary-verification-for-sock-color-hits)
  - [EN-21. Single-frame trigger in sock-color mode](#en-21-single-frame-trigger-in-sock-color-mode)
  - [EN-22. Two-pass verification for jersey-number matching](#en-22-two-pass-verification-for-jersey-number-matching)
  - [EN-23. Shin-band confirmation to suppress arm-as-leg false hits](#en-23-shin-band-confirmation-to-suppress-arm-as-leg-false-hits)
  - [EN-24. Miss-based temporal skipping for faster scanning](#en-24-miss-based-temporal-skipping-for-faster-scanning)
  - [EN-25. Target-focused zoom verification and softer miss-skip default](#en-25-target-focused-zoom-verification-and-softer-miss-skip-default)
  - [EN-26. Height-based near-ball rule and box-only overlays](#en-26-height-based-near-ball-rule-and-box-only-overlays)
  - [EN-27. Shot-priority recall window and segment continuation](#en-27-shot-priority-recall-window-and-segment-continuation)
  - [EN-28. `--ball-near-meter` honored for near-ball gate (matches stderr cm line)](#en-28-ball-near-meter-honored-for-near-ball-gate-matches-stderr-cm-line)
  - [EN-29. Sock recall loosened + shoe false-positive guard (≥12cm / other-palette above)](#en-29-sock-recall-loosened--shoe-false-positive-guard-12cm--other-palette-above)
  - [EN-30. Orange sock vs yellow kit discrimination](#en-30-orange-sock-vs-yellow-kit-discrimination)
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
  - [ZH-17. 首次锁定搜索窗口默认不限制](#zh-17-首次锁定搜索窗口默认不限制)
  - [ZH-18. 严格模式球袜召回增强（降低漏检）](#zh-18-严格模式球袜召回增强降低漏检)
  - [ZH-19. 近球门控判定放宽（降低漏触发）](#zh-19-近球门控判定放宽降低漏触发)
  - [ZH-20. 球袜命中增加放大二次校验（降低误检）](#zh-20-球袜命中增加放大二次校验降低误检)
  - [ZH-21. 袜色模式改为单帧触发（降低漏触发）](#zh-21-袜色模式改为单帧触发降低漏触发)
  - [ZH-22. 号码识别改为两阶段校验（降低误检）](#zh-22-号码识别改为两阶段校验降低误检)
  - [ZH-23. 增加小腿确认带，抑制“手臂当腿”误检](#zh-23-增加小腿确认带抑制手臂当腿误检)
  - [ZH-24. 未命中时按秒跳帧，加速扫描](#zh-24-未命中时按秒跳帧加速扫描)
  - [ZH-25. 聚焦目标区域放大复核，并下调默认跳帧](#zh-25-聚焦目标区域放大复核并下调默认跳帧)
  - [ZH-26. 近球改为“球距不超过身高”并统一框标注](#zh-26-近球改为球距不超过身高并统一框标注)
  - [ZH-27. 射门优先召回窗口与片段连续扩展](#zh-27-射门优先召回窗口与片段连续扩展)
  - [ZH-28. `--ball-near-meter` 参与近球门控并与 stderr 厘米距离一致](#zh-28-ball-near-meter-参与近球门控并与-stderr-厘米距离一致)
  - [ZH-29. 球袜放宽召回 + 球鞋误检双条件（上沿 12cm / 非目标袜色带）](#zh-29-球袜放宽召回--球鞋误检双条件上沿-12cm--非目标袜色带)
  - [ZH-30. 橙袜与黄色球衣/裁判服区分](#zh-30-橙袜与黄色球衣裁判服区分)
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
| `--ball-near-meter` | `1.0` | `-n` or `--sock-color` | Near-ball max distance in **meters**; gate uses `distance_cm <= value × 100`, same scale as stderr sock-save logs ([EN-7](#en-7-configurable-near-ball-distance-threshold), [EN-28](#en-28-ball-near-meter-honored-for-near-ball-gate-matches-stderr-cm-line)). Ignored when `--segment-on-target-only` is set. |
| `--segment-on-target-only` | off | `-n` or `--sock-color` | If set, segments trigger on valid target only; ball proximity/possession checks are skipped (streak/max-clips still apply). See [`feature.md`](./feature.md) FEAT-20260501-16. |
| `--near-ball-streak-frames` | `2` | `-n` or `--sock-color` | Consecutive frames required before starting a clip ([EN-9](#en-9-consecutive-frame-confirmation-before-triggering-clips)). |
| `--max-search-frames` | `0` | `-n` or `--sock-color` | Max frames from start to first successful lock; `0` = unlimited (default) ([EN-17](#en-17-default-unlimited-first-lock-search-window)). |
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

### EN-17. Default unlimited first-lock search window
- Changed `--max-search-frames` default from `2400` to `0` (unlimited).
- **Why:** Long clips or late appearances of the target should not abort by default; users can still set a positive cap for faster fail-fast behavior.

### EN-18. Sock-color recall hardening for strict mode
- **Problem:** In strict dual-band mode, some target sock colors (especially white/black under compression or exposure shifts) can be under-counted in one band and cause false negatives.
- **Mitigation:**
  - Added color-aware strict per-band floor: white/black now use a lower floor (`0.24`), while other colors keep `0.30` (still bounded by `--sock-min-ratio`).
  - Added conservative partial-band fallback: if one knee band passes and the other is close, accept only when the merged knee ROI also passes a guarded ratio check.
- **Impact:** Improves recall for hard sock-color scenes while keeping anti-false-positive guards (orange line rejection and ratio gating) active.

### EN-19. Near-ball gating made more tolerant
- **Problem:** Near-ball gating could be too strict in practice, making segment triggers hard when ball boxes jitter, are tiny, or player scale is far-field.
- **Mitigation:**
  - Relaxed meter-to-pixel mapping using a wider body scale (`max(height, 1.25*width)`) and a larger tolerance factor.
  - Expanded possession zone around lower body/feet.
  - Switched from center-only distance to nearest-point distance from ball box to player box, with extra margin from ball radius and player width.
- **Impact:** Easier near-ball satisfaction and better trigger recall while still requiring target validity plus streak confirmation.

### EN-20. Zoom-in secondary verification for sock-color hits
- **Problem:** Some false positives can still pass at original scale when target socks are small/noisy in frame.
- **Mitigation:** Added a two-pass sock-color decision:
  - Pass 1: normal-scale match (existing logic).
  - Pass 2: zoom-in local patch around the candidate player and re-check sock-color with a slightly stricter ratio.
- **Impact:** Candidate frames must pass both checks, which suppresses non-target players that accidentally pass coarse-scale color checks.

### EN-21. Single-frame trigger in sock-color mode
- **Change:** In `--sock-color` mode, near-ball trigger now defaults to single-frame confirmation once the frame passes sock-color verification and near-ball check.
- **Why:** With two-pass sock-color verification enabled, requiring two consecutive frames became unnecessarily strict and caused missed triggers.
- **Impact:** Sock-color workflow starts clips faster on valid hits while still guarded by color verification and ball proximity.

### EN-22. Two-pass verification for jersey-number matching
- **Change:** Jersey-number matching now uses the same two-pass confirmation pattern as sock-color matching.
- **Mitigation:** Candidate player must pass:
  - Pass 1: normal-scale OCR number match.
  - Pass 2: zoom-in local OCR re-check around the same player box with slightly stricter confidence.
- **Impact:** Reduces false locks where coarse-scale OCR accidentally reads a wrong player as target number.

### EN-23. Shin-band confirmation to suppress arm-as-leg false hits
- **Problem:** In some frames, arm/sleeve colors near knee-height could be mistaken as sock-color hits.
- **Mitigation:** Added a lower-leg (mid-shin) confirmation band; a candidate now needs color support in shin area as well, not only knee-centered bands/ROI.
- **Impact:** Reduces false positives where upper-limb colors are misclassified as leg/sock evidence.

### EN-24. Miss-based temporal skipping for faster scanning
- **Change:** Added `--skip-seconds-on-miss` (default `0.05`) in tracking modes.
- **Behavior:** When current frame misses target lock, the pipeline skips approximately the configured seconds worth of subsequent frames before running next full detection pass.
- **Impact:** Reduces detector invocations and speeds up long-footage scanning; set `0` to disable skipping.

### EN-25. Target-focused zoom verification and softer miss-skip default
- **Problem:** Global player-centered zoom verification could still include distracting regions; aggressive miss-skip could reduce recall.
- **Mitigation:**
  - Second-pass zoom now focuses by task: jersey mode centers on torso/number region; sock mode centers on lower-leg/sock region, while still containing full player box for stable geometry.
  - Sock second-pass ratio bump reduced from `+0.03` to `+0.01` to avoid over-pruning true positives.
  - Shin confirmation band shifted upward to reduce shoe-color contamination.
  - Miss-skip default lowered to `0.2s` (from `1.0s`) for better recall/throughput balance.
  - Miss-skip default further lowered to `0.05s` to reduce missed short shooting moments.
- **Impact:** Better precision on true target regions with improved recall stability and fewer shoe-as-sock artifacts.

### EN-26. Height-based near-ball rule and box-only overlays
- **Change:** Near-ball decision now accepts candidate when ball-player distance is less than or equal to player height (in pixels).
- **Refinement:** Distance is measured from ball center to nearest point on player's foot line (bottom edge of player box), and threshold uses head-to-foot pixel distance.
- **Visual update:** Removed head-circle marker; exported verification frames and output segments now use target bounding box overlay consistently.
- **Impact:** Aligns near-ball semantics with requested rule-of-thumb and improves visual verification consistency during playback.

### EN-27. Shot-priority recall window and segment continuation
- **Change:** Added shot-priority recall controls:
  - `--ball-missing-grace-frames` to tolerate 1-2 brief frames without ball detection while preserving near-ball state.
  - `--shot-relax-window-sec` with `--shot-relax-sock-delta` / `--shot-relax-ocr-delta` to slightly relax second-pass verification thresholds in a short shot-candidate window.
  - `--segment-extend-sec` to allow active segments to continue briefly while near-ball persists after trigger.
- **Impact:** Improves capture of short shooting actions under ball-detection flicker and avoids clip fragmentation around trigger boundaries.

### EN-28. `--ball-near-meter` honored for near-ball gate (matches stderr cm line)
- **Problem:** Near-ball gating compared raw pixels to one body-height in px (`min_d <= near_px`) and **ignored** `--ball-near-meter`, so large values like `100` did nothing. stderr could print ~287cm while exported `--sock-save-frames` JPGs (which require near-ball) never appeared.
- **Fix:** Near-ball now uses the same approximate cm distance as `[sock-save-frames]` logging (`_player_ball_distance_cm`, 175cm reference height per bbox). Pass when `distance_cm <= ball_near_meter * 100`.
- **Default:** `--ball-near-meter 1.0` → **100cm** threshold (documented “meters”). To approximate the old one-body-height pixel cap (~175cm), use `--ball-near-meter 1.75`.

### EN-29. Sock recall loosened + shoe false-positive guard (≥12cm / other-palette above)
- **Primary gate (updated):** Knee upper/lower **dual bands are no longer required**. Both strict and relaxed modes use a **wider below-knee leg band** (小腿) for target-color ratio; strict mode only applies a **stricter scaled floor** via `_sock_strict_min_ratio`. This restores recall when knee ROIs miss.
- **Recall tuning:** Lower shin ratio multipliers, slightly wider shin ROI horizontally/vertically, easier zoom second pass (`max(min_ratio-0.015, …)` vs a bump-up).
- **Shoe guard (no new CLI):** After shin-band evidence passes, reject if:
  1. In a below-knee strip, the **target-color** mask top is within **~15cm** of the foot line (box bottom, 1.75m scale)—shoe-only stripe; or
  2. In a ~5cm band **above** that top edge, **non-target** sock-palette colors exceed **~11%** of valid (skin-masked) pixels (sock stripe above shoe).
- Zoom-in verification uses **full-frame geometry** for shoe guard (`shoe_frame_bgr` / `shoe_xyxy`).

### EN-30. Orange sock vs yellow kit discrimination
- **Problem:** After shin-primary sock matching, yellow referee shirts / kits could satisfy orange HSV bleed or wrong ROI placement and lock as `--sock-color orange`.
- **Mitigation:**
  - Tightened built-in **orange** HSV wedge (`H∈[11,19]`, higher min S/V) to separate from **yellow** (`H≥22`).
  - For orange targets only: if **yellow** ratio in the **same shin ROI** clearly exceeds **orange** (`yellow > orange + 0.007` and yellow ≥ ~8.8%), reject.
  - For orange targets only: if **upper torso** strip (~top 10–42% of player box) shows **strong yellow** (ratio ≥ ~15%), reject (yellow shirt / bib).

### Cross Reference to Chinese Section
- Chinese mirror for this section: [Jump to 中文](#中文)
- CLI quick reference (Chinese): [CLI 快速参考（中文）](#cli-quick-ref-zh)
- Orange pitch-line guard (Chinese): [ZH-15](#zh-15-橙色目标球场标线误判抑制)
- First-lock search default unlimited (Chinese): [ZH-17](#zh-17-首次锁定搜索窗口默认不限制)
- Strict-mode sock recall hardening (Chinese): [ZH-18](#zh-18-严格模式球袜召回增强降低漏检)
- Near-ball gating tolerance increase (Chinese): [ZH-19](#zh-19-近球门控判定放宽降低漏触发)
- Zoom-in secondary sock verification (Chinese): [ZH-20](#zh-20-球袜命中增加放大二次校验降低误检)
- Single-frame sock trigger (Chinese): [ZH-21](#zh-21-袜色模式改为单帧触发降低漏触发)
- Two-pass jersey verification (Chinese): [ZH-22](#zh-22-号码识别改为两阶段校验降低误检)
- Shin-band anti arm confusion (Chinese): [ZH-23](#zh-23-增加小腿确认带抑制手臂当腿误检)
- Miss-based skip acceleration (Chinese): [ZH-24](#zh-24-未命中时按秒跳帧加速扫描)
- Target-focused zoom and softer skip default (Chinese): [ZH-25](#zh-25-聚焦目标区域放大复核并下调默认跳帧)
- Height-based near-ball and box overlay (Chinese): [ZH-26](#zh-26-近球改为球距不超过身高并统一框标注)
- Shot-priority recall window (Chinese): [ZH-27](#zh-27-射门优先召回窗口与片段连续扩展)
- `--ball-near-meter` gate vs cm logging (Chinese): [ZH-28](#zh-28-ball-near-meter-参与近球门控并与-stderr-厘米距离一致)
- Sock shoe guard & recall loosening (Chinese): [ZH-29](#zh-29-球袜放宽召回--球鞋误检双条件上沿-12cm--非目标袜色带)
- Orange vs yellow sock discrimination (Chinese): [ZH-30](#zh-30-橙袜与黄色球衣裁判服区分)
- Orange vs yellow sock discrimination (English): [EN-30](#en-30-orange-sock-vs-yellow-kit-discrimination)

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
| `--ball-near-meter` | `1.0` | `-n` 或 `--sock-color` | 近球最大距离（**米**）；门控条件为 `距离_cm ≤ 参数×100`，与 stderr 袜色日志厘米一致（[ZH-7](#zh-7-可配置近球距离阈值)、[ZH-28](#zh-28-ball-near-meter-参与近球门控并与-stderr-厘米距离一致)）。与 `--segment-on-target-only` 二选一有效时，以仅目标模式为准。 |
| `--segment-on-target-only` | 关闭 | `-n` 或 `--sock-color` | 若指定，则只要目标有效即触发片段，不判近球/持球；仍受连续帧、片段上限等约束。见 [`feature.md`](./feature.md) FEAT-20260501-16。 |
| `--near-ball-streak-frames` | `2` | `-n` 或 `--sock-color` | 连续满足近球条件后才触发片段（[ZH-9](#zh-9-连续帧确认后再触发片段)）。 |
| `--max-search-frames` | `0` | `-n` 或 `--sock-color` | 从起点起多少帧内须首次锁定目标；`0` 不限制（默认）（[ZH-17](#zh-17-首次锁定搜索窗口默认不限制)）。 |
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

### ZH-17. 首次锁定搜索窗口默认不限制
- `--max-search-frames` 默认值由 `2400` 改为 `0`（不限制帧数）。
- **原因：** 长片或目标较晚才出现时，默认不应因搜索窗口过短而直接退出；需要时可显式设为正整数做快速失败。

### ZH-18. 严格模式球袜召回增强（降低漏检）
- **问题：** 严格双带模式下，部分目标袜色（尤其白/黑袜在压缩或曝光波动下）可能出现单带占比偏低，导致漏检。
- **处理：**
  - 新增颜色感知的严格阈值下限：白/黑袜下限降至 `0.24`，其余颜色保持 `0.30`（同时仍受 `--sock-min-ratio` 约束）。
  - 新增严格模式保守补偿判定：当一条膝带达标、另一条接近阈值时，仅在合并膝区占比也达标的情况下放行。
- **效果：** 在困难颜色场景提升召回率，同时保留橙色标线抑制与占比门限，尽量避免误检回升。

### ZH-19. 近球门控判定放宽（降低漏触发）
- **问题：** 近球门控在实战中偏严，球框抖动、球框过小或远景尺度偏差会导致触发困难。
- **处理：**
  - 放宽“米到像素”换算：改用更宽松的人体尺度（`max(身高像素, 1.25*宽度像素)`）并增加容差系数。
  - 扩大下肢/脚下持球区域判定范围。
  - 距离判定从“仅球心到人框”改为“球框最近点到人框”，并叠加球半径与宽度边距补偿。
- **效果：** 更容易满足近球条件，提升片段触发召回；同时仍保留目标有效性与连续帧门槛约束。

### ZH-20. 球袜命中增加放大二次校验（降低误检）
- **问题：** 原始分辨率下仍可能出现粗粒度颜色误命中，导致非目标球员被判为袜色命中。
- **处理：** 将球袜判定改为两阶段：
  - 第一阶段：按原尺度执行现有球袜匹配。
  - 第二阶段：围绕候选球员构建局部放大区域，再执行一次袜色匹配，并使用略严格的阈值复核。
- **效果：** 仅当两次都通过才判定命中，可有效抑制“远景/噪声导致的误检测”。

### ZH-21. 袜色模式改为单帧触发（降低漏触发）
- **变更：** 在 `--sock-color` 模式下，只要当前帧通过袜色校验并满足近球条件，即可触发，不再默认要求连续两帧。
- **原因：** 引入放大二次校验后，命中可信度已提升，继续要求连续两帧会增加不必要的漏触发。
- **效果：** 有效命中时触发更及时，同时仍受袜色校验与近球门控约束。

### ZH-22. 号码识别改为两阶段校验（降低误检）
- **变更：** 号码识别路径与袜色路径一致，改为“两次都通过才命中”。
- **处理：**
  - 第一阶段：原尺度 OCR 号码匹配。
  - 第二阶段：围绕同一候选球员框做局部放大，再做一次 OCR 复核（置信度略收紧）。
- **效果：** 可减少粗尺度 OCR 将非目标球员误读为目标号码而造成的误锁定。

### ZH-23. 增加小腿确认带，抑制“手臂当腿”误检
- **问题：** 个别帧中手臂/袖子颜色在膝部高度附近会干扰袜色判断，出现“把手臂当腿”的误检。
- **处理：** 在原有膝部带/膝部 ROI 命中基础上，新增小腿中段确认带；只有小腿区域也有足够颜色证据才放行。
- **效果：** 降低上肢颜色误入袜色证据链的概率，提升命中可信度。

### ZH-24. 未命中时按秒跳帧，加速扫描
- **变更：** 跟拍模式新增 `--skip-seconds-on-miss`（默认 `0.05`）。
- **行为：** 当当前帧未识别到目标时，按配置秒数跳过后续帧，再进行下一次完整检测。
- **效果：** 减少检测调用频次，加快长视频扫描；设置为 `0` 可关闭跳帧。

### ZH-25. 聚焦目标区域放大复核，并下调默认跳帧
- **问题：** 以整个人体为中心的放大复核可能引入无关区域；未命中默认跳 1 秒会增加漏检。
- **处理：**
  - 放大复核改为按任务聚焦：号码模式聚焦躯干号码区，袜色模式聚焦下肢袜色区，同时保证完整人框仍在 patch 内。
  - 袜色二次复核阈值增量由 `+0.03` 下调为 `+0.01`，减少过严筛除。
  - 小腿确认带上移，降低鞋面颜色污染。
  - 未命中跳帧默认值下调为 `0.2s`，兼顾速度与召回。
  - 未命中跳帧默认值进一步下调为 `0.05s`，减少短时关键动作漏检。
- **效果：** 目标区域复核更精准，误把鞋色当袜色的风险下降，且召回更稳定。

### ZH-26. 近球改为“球距不超过身高”并统一框标注
- **变更：** 近球判定改为“球到人距离 <= 球员身高像素”即合格。
- **细化：** 距离改为“球心到脚面线段（人框底边）”最短距离；阈值用“头到脚”的像素距离计算，去除较宽松捷径。
- **可视化：** 取消头顶圆圈；导出命中帧和输出片段统一使用目标框标注。
- **效果：** 近球规则更符合业务约定，且播放核验时标注样式一致、目标更易追踪。

### ZH-27. 射门优先召回窗口与片段连续扩展
- **变更：** 新增射门优先召回参数：
  - `--ball-missing-grace-frames`：允许短时 1-2 帧无球检测仍维持近球状态。
  - `--shot-relax-window-sec` + `--shot-relax-sock-delta` / `--shot-relax-ocr-delta`：在射门候选窗口里下调二次复核阈值。
  - `--segment-extend-sec`：触发后在近球持续时允许片段短窗口连续扩展。
- **效果：** 降低射门瞬间因丢球检测/阈值过严造成的漏检，并减少片段被割裂。

### ZH-28. `--ball-near-meter` 参与近球门控并与 stderr 厘米距离一致
- **问题：** 近球判定曾用像素与「一身高等价」比较（`min_d <= near_px`），**未使用** `--ball-near-meter`，故设为 `100` 等也不生效；stderr 可打印约 287cm，但依赖近球的 `--sock-save-frames` 导出仍不会出现。
- **修复：** 与 `[sock-save-frames]` 日志共用 `_player_ball_distance_cm`（框高→175cm 标尺）；当 `距离_cm ≤ ball_near_meter × 100` 时判定近球。
- **默认：** `--ball-near-meter 1.0` 对应 **100cm** 阈值（文档单位：米）。若要接近旧版「不超过一身长」像素上限（约 175cm），可使用 `--ball-near-meter 1.75`。

### ZH-29. 球袜放宽召回 + 球鞋误检双条件（上沿 12cm / 非目标袜色带）
- **主判定（已更新）：** 不再要求膝上/膝下**双带**同时命中；严格/宽松均以**膝下小腿带**目标色占比为主，严格模式仅通过 `_sock_strict_min_ratio` 提高缩放基准；减轻膝部 ROI 漏检导致的整体失败。
- **召回：** 降低小腿占比门槛、加宽小腿采样带、放大复核略放宽（相对 `--sock-min-ratio` 下浮而非上抬）。
- **球鞋抑制（无新 CLI）：** 小腿通过后 `_sock_reject_likely_shoe`：
  1. **距地高度：** 目标色上沿距脚底 **&lt;~15cm**（过低条带，偏鞋区）则拒绝；
  2. **上方异色袜：** 上沿之上约 **5cm** 窄带内，非目标内置袜色在肤色有效像素中占比 **≥~11%** 则拒绝。
- 放大复核仍用全画面坐标做球鞋几何判定。

### ZH-30. 橙袜与黄色球衣/裁判服区分
- **问题：** 小腿主判定 + 偏宽 ROI 后，黄衣裁判等易被橙色 HSV 串色或框偏移误判为 `--sock-color orange`。
- **处理：** 内置橙色 HSV 收紧并与黄色分区（H 分界）；橙袜专用——小腿 ROI 内黄色占比明显高于橙色则拒绝；上躯干（约框高 10%–42%）黄色过强则拒绝（黄衣/背心）。

### 交叉引用到英文部分
- 英文镜像内容： [Jump to English](#english)
- 英文 CLI 快速表：[CLI quick reference (English)](#cli-quick-ref-en)
- 橙色标线抑制（英文）：[EN-15](#en-15-orange-pitch-line-rejection-for-sock-color)
- 肤色排除（英文）：[EN-16](#en-16-skin-tone-exclusion-for-sock-color-ratio)
- 首次锁定搜索默认不限制（英文）：[EN-17](#en-17-default-unlimited-first-lock-search-window)
- 严格模式球袜召回增强（英文）：[EN-18](#en-18-sock-color-recall-hardening-for-strict-mode)
- 近球门控判定放宽（英文）：[EN-19](#en-19-near-ball-gating-made-more-tolerant)
- 放大二次校验（英文）：[EN-20](#en-20-zoom-in-secondary-verification-for-sock-color-hits)
- 袜色单帧触发（英文）：[EN-21](#en-21-single-frame-trigger-in-sock-color-mode)
- 号码两阶段校验（英文）：[EN-22](#en-22-two-pass-verification-for-jersey-number-matching)
- 小腿确认带（英文）：[EN-23](#en-23-shin-band-confirmation-to-suppress-arm-as-leg-false-hits)
- 未命中跳帧加速（英文）：[EN-24](#en-24-miss-based-temporal-skipping-for-faster-scanning)
- 目标聚焦放大复核（英文）：[EN-25](#en-25-target-focused-zoom-verification-and-softer-miss-skip-default)
- 身高距离规则与统一框标注（英文）：[EN-26](#en-26-height-based-near-ball-rule-and-box-only-overlays)
- 射门优先召回窗口（英文）：[EN-27](#en-27-shot-priority-recall-window-and-segment-continuation)
- `--ball-near-meter` 门控与厘米一致（英文）：[EN-28](#en-28-ball-near-meter-honored-for-near-ball-gate-matches-stderr-cm-line)
- 球袜球鞋抑制与召回（英文）：[EN-29](#en-29-sock-recall-loosened--shoe-false-positive-guard-12cm--other-palette-above)
- 橙/黄球袜区分（英文）：[EN-30](#en-30-orange-sock-vs-yellow-kit-discrimination)

