# video_person_zoom.py — 使用说明 / User Guide

---

## 中文

### 概述

`video_person_zoom.py` 支持三种工作方式：

1. **仅下载 / 复制（只提供 `INPUT`，不提供 `-n`、`-w`、`-d`）**  
   - **URL**：用 `yt-dlp` 下载到本地（默认文件名形如 `download_<时间戳>.<扩展名>`，或用 `-o` 指定路径）。  
   - **本地路径**：将文件**复制**到当前目录（默认 `<原名>_copy<后缀>`），或用 `-o` 指定目标路径。  
   不做转码、不跟拍、不截取。

2. **跟拍模式（提供 `-n` 球衣号码）**  
   使用 YOLO 检测人物，在球衣区域用 EasyOCR 识别号码，匹配后按 IoU 跟踪并输出裁切放大后的跟拍视频。可选 `-w` / `-d` 先截取时间片段再处理。

3. **仅截取模式（不提供 `-n`，但提供 `-w` 与 `-d`）**  
   只按时间窗口从原片截取片段输出，**不进行**人物检测与 OCR。若系统已安装 **`ffmpeg`**，脚本会**优先用 ffmpeg 截取**（更稳，尤其可避免 AV1 在 OpenCV 下读帧失败）；否则回退为 OpenCV 逐帧写入。

### 依赖与安装

**跟拍模式**需要安装：

```bash
pip install -r requirements-person-zoom.txt
```

依赖包括：`opencv-python-headless`、`ultralytics`、`yt-dlp`、`numpy`、`easyocr` 等。

**从 URL（如 YouTube）下载并合并音视频**时，系统需安装 **`ffmpeg`**（命令行工具，不是 Python 包）。例如 Debian/Ubuntu：

```bash
sudo apt update && sudo apt install -y ffmpeg
```

**仅截取模式**：**强烈建议**安装系统 **`ffmpeg`**（脚本优先用它截取）；否则仅用 OpenCV 写 MP4，对部分编码（如 AV1）兼容性较差。若输入为 URL，仍需要 `yt-dlp` 与 `ffmpeg`。

### 基本用法

```text
video_person_zoom.py INPUT [选项]
```

- **`INPUT`**：本地视频路径，或 `http(s)` 地址（由 `yt-dlp` 下载，常见于 YouTube）。

### 三种模式对照

| 模式           | 条件 | 行为说明 |
|----------------|------|----------|
| 仅下载/复制    | **无** `-n`，**且无** `-w`/`-d` | URL → 下载；本地文件 → 复制到当前目录或 `-o`。 |
| 跟拍           | 提供 **`-n`** | 检测 + OCR 跟号码；`-w`/`-d` 可选（须成对使用）。 |
| 仅截取         | **无** `-n`，但有 **`-w`** 与 **`-d`** | 按时间窗口导出片段（优先 ffmpeg）。 |

**`-w` 与 `-d` 规则（通用）**：

- 必须**同时提供**或**同时省略**（跟拍模式下省略表示处理整段）。
- **`-w TIME`**：片段中心时间，支持秒数（如 `90`、`90.5`）、`MM:SS`、`H:MM:SS`。
- **`-d SECONDS`**：片段总时长（秒），以 `-w` 为中心向两侧对称截取；靠近片头/片尾时窗口会在 `[0, 片长]` 内平移，总长仍为 `d`（片长不足 `d` 时导出整段）。

### 常用参数说明（中文）

| 参数 | 说明 |
|------|------|
| `-n`, `--number NUM` | 要跟拍的球衣号码（仅数字）。不提供且无 `-w`/`-d` 时：仅下载或复制。 |
| `-o`, `--output PATH` | 输出 MP4 路径；默认见下表。 |
| `-w TIME`, `--window` | 与 `-d` 成对：片段中心时间。 |
| `-d SEC`, `--duration` | 与 `-w` 成对：片段总时长（秒）。 |
| `--model` | YOLO 权重，默认 `yolov8n.pt`。 |
| `--padding` | 人物框外留白比例，默认 `0.25`。 |
| `--smooth` | 框平滑系数 0~1，默认 `0.35`。 |
| `--device` | 推理设备，如 `cpu`、`cuda:0`。 |
| `--target-order` | 多人时排序：`area-desc`、`area-asc`、`left`、`right`、`top`、`bottom`。 |
| `--target-index` | 在上述排序下的 0 起始下标（跟丢且 OCR 失败时的几何回退）。 |
| `--min-iou` | 帧间 IoU 低于该值时尝试用号码 OCR 重锁，默认 `0.2`。 |
| `--ocr-min-conf` | EasyOCR 置信度下限，默认 `0.15`。 |
| `--max-search-frames` | 从处理起点起最多多少帧内必须首次识别到号码；`0` 表示不限制；默认 `2400`。 |

### 默认输出文件名（中文）

| 输入 | 模式 | 默认输出 |
|------|------|----------|
| 本地文件 | 仅复制 | 当前目录 `<原名>_copy<后缀>` |
| URL | 仅下载 | 当前目录 `download_<时间戳>.<扩展名>` |
| 本地文件 | 跟拍 `-n` | `原名_jersey{号码}_zoom.mp4` |
| 本地文件 | 仅截取 | `原名_clip.mp4` |
| URL | 跟拍 | `jersey{号码}_zoom_<时间戳>.mp4` |
| URL | 仅截取 | `clip_<时间戳>.mp4` |

### 示例（中文）

```bash
# 跟拍 10 号，整段处理
python video_person_zoom.py match.mp4 -n 10

# 跟拍 10 号，只处理以 5:00 为中心、总长 20 秒的片段
python video_person_zoom.py match.mp4 -n 10 -w 5:00 -d 20 -o out.mp4

# 仅复制本地文件到当前目录（默认 match_copy.mp4）或指定 -o
python video_person_zoom.py /path/to/match.mp4 -o ./copy.mp4

# 仅下载 URL 到当前目录（默认 download_<时间戳>.<扩展名>）
python video_person_zoom.py "https://www.youtube.com/watch?v=VIDEO_ID" -o ./video.mp4

# 不提供号码：只截取片段（原画）
python video_person_zoom.py match.mp4 -w 5:00 -d 20 -o clip.mp4

# YouTube（需 yt-dlp + ffmpeg）
python video_person_zoom.py "https://www.youtube.com/watch?v=VIDEO_ID" -n 7 -w 1:30 -d 15 -o ./out.mp4
```

### 故障排除：AV1 提示、输出 MP4 极小且无法播放

#### 原因说明

1. **`Your platform doesn't support hardware accelerated AV1 decoding`**  
   多半来自 **FFmpeg / OpenCV 在解码 AV1** 时的提示，含义是：**当前没有可用的硬件 AV1 解码**，往往仍会走 **CPU 软解**。这条提示**本身不一定是错误**。

2. **生成的文件（例如 `/tmp/abc.mp4`）体积极小、播放器打不开**  
   常见原因是：**几乎没有成功解码并写出有效帧**。旧逻辑主要依赖 OpenCV `VideoCapture` 逐帧读取；对 **AV1** 等格式，在不少环境下 `read()` 会**很快失败或几乎读不到帧**，`VideoWriter` 只会留下一个**近乎空的、损坏的 MP4**（常见只有几 KB～几十 KB）。

#### 脚本中的相关行为（便于对照现象）

- **仅截取模式（无 `-n`）**：若检测到系统 **`ffmpeg`**，会**优先用 ffmpeg** 按 `-w`/`-d` 截取并输出 **H.264**（必要时无音轨重试），**不依赖 OpenCV 解码片源**，一般可避免 AV1 导致的空文件。  
- **跟拍模式（有 `-n`）**：打开视频后会**先试读第一帧**；读不到会提示先把片源转成 **H.264** 再处理。  
- **两种模式**：写入结束后会检查 **写入帧数** 与 **输出文件大小**；明显异常时会报错并尝试删除无效输出，避免误以为已成功生成。

#### 你可以怎么做

**若主要是截取片段（不提供 `-n`）：**  
安装好 **`ffmpeg`** 后再运行；脚本会自动走 **ffmpeg 截取**，通常即可得到可正常播放的 MP4。

**若必须使用跟拍（提供 `-n`）：**  
请先把素材转成 **H.264**（OpenCV 读帧更稳），例如：

```bash
ffmpeg -i 原片.mp4 -c:v libx264 -crf 23 -c:a copy 原片_h264.mp4
python video_person_zoom.py 原片_h264.mp4 -n 10 -o /tmp/out.mp4
```

**其它检查：**  
若仍异常，请确认 **`-w` / `-d` 未超出片长**，片源文件未损坏；并查看终端完整报错信息。

### 已知限制（中文）

- OCR 依赖画面清晰度；远景、模糊、遮挡可能导致无法锁定或跟错。  
- 跟拍模式首次锁定前会输出全画面占位帧（若在片段模式下，仍计入 `-d` 限定帧数）。  
- 同一号码多人等极端情况需人工校验结果。

---

## English

### Overview

`video_person_zoom.py` supports three modes:

1. **Download / copy only (`INPUT` only — no `-n`, no `-w`/`-d`)**  
   - **URL**: download via `yt-dlp` (default name like `download_<timestamp>.<ext>`, or use `-o`).  
   - **Local path**: **copy** the file into the current directory (default `<name>_copy<suffix>`), or set `-o`.  
   No transcoding, tracking, or trimming.

2. **Tracking mode (`-n` is set)**  
   YOLO + EasyOCR + IoU tracking for a cropped follow shot. Optional `-w` / `-d` to process a time window first.

3. **Trim-only mode (`-n` omitted, but `-w` and `-d` are set)**  
   Exports only that segment **without** detection or OCR. If **`ffmpeg`** is installed, the script **prefers ffmpeg** for trimming; otherwise OpenCV frame-by-frame writing.

### Dependencies

**Tracking mode:**

```bash
pip install -r requirements-person-zoom.txt
```

Includes `opencv-python-headless`, `ultralytics`, `yt-dlp`, `numpy`, `easyocr`, etc.

For **HTTP(S) sources** (e.g. YouTube), **`ffmpeg`** must be installed on the system (the actual `ffmpeg` binary, not a Python-only wrapper), because `yt-dlp` merges separate video/audio streams with it.

**Trim-only mode**: **`ffmpeg` is strongly recommended** (the script prefers it for trimming). Without it, OpenCV-only MP4 writing can be unreliable for some codecs (e.g. AV1). URLs still need `yt-dlp` and `ffmpeg`.

### Basic invocation

```text
video_person_zoom.py INPUT [options]
```

- **`INPUT`**: path to a local video file, or an `http(s)` URL (downloaded via `yt-dlp`).

### Mode summary

| Mode | Condition | Behavior |
|------|-----------|----------|
| Download / copy | **No** `-n` and **no** `-w`/`-d` | URL → download; local file → copy to cwd or `-o`. |
| Tracking | **`-n`** is provided | Detect + OCR + follow; `-w`/`-d` optional (together if used). |
| Trim-only | **No** `-n`, but **`-w`** and **`-d`** are set | Export that time range only (prefers ffmpeg). |

**`-w` / `-d` rules:**

- Use **both** or **neither** (in tracking mode, omitting both means process the full file).
- **`-w TIME`**: center time of the clip; supports seconds (`90`, `90.5`), `MM:SS`, or `H:MM:SS`.
- **`-d SECONDS`**: total clip length in seconds, symmetric around `-w`; the window is clamped/shifted to stay inside `[0, duration]` while keeping length `d` when possible (if the file is shorter than `d`, the whole file is exported).

### Common options (English)

| Option | Description |
|--------|-------------|
| `-n`, `--number NUM` | Jersey number (digits only). Omit with no `-w`/`-d` → download/copy only. |
| `-o`, `--output PATH` | Output MP4 path; defaults see table below. |
| `-w`, `--window` | Must pair with `-d`: center time. |
| `-d`, `--duration` | Must pair with `-w`: clip length in seconds. |
| `--model` | YOLO weights, default `yolov8n.pt`. |
| `--padding` | Extra margin around the person box, default `0.25`. |
| `--smooth` | Box smoothing 0–1, default `0.35`. |
| `--device` | Inference device, e.g. `cpu`, `cuda:0`. |
| `--target-order` | When multiple people: `area-desc`, `area-asc`, `left`, `right`, `top`, `bottom`. |
| `--target-index` | 0-based index after that ordering (geometry fallback if track+OCR fail). |
| `--min-iou` | If IoU vs previous box is below this, try OCR re-lock; default `0.2`. |
| `--ocr-min-conf` | EasyOCR confidence threshold; default `0.15`. |
| `--max-search-frames` | Max frames from the processing start to obtain the first successful number read; `0` = unlimited; default `2400`. |

### Default output filenames (English)

| Input | Mode | Default output |
|-------|------|----------------|
| Local file | Download/copy only | `{basename}_copy{ext}` in cwd |
| URL | Download only | `download_<unix_timestamp>.<ext>` in cwd |
| Local file | Tracking with `-n` | `{basename}_jersey{NUM}_zoom.mp4` |
| Local file | Trim-only | `{basename}_clip.mp4` |
| URL | Tracking | `jersey{NUM}_zoom_<unix_timestamp>.mp4` |
| URL | Trim-only | `clip_<unix_timestamp>.mp4` |

### Examples (English)

```bash
# Track jersey #10, full video
python video_person_zoom.py match.mp4 -n 10

# Track #10 on a 20s clip centered at 5:00
python video_person_zoom.py match.mp4 -n 10 -w 5:00 -d 20 -o out.mp4

# Copy a local file (default ./match_copy.mp4) or set -o
python video_person_zoom.py /path/to/match.mp4 -o ./copy.mp4

# Download a URL only
python video_person_zoom.py "https://www.youtube.com/watch?v=VIDEO_ID" -o ./video.mp4

# No jersey number: trim only (original framing)
python video_person_zoom.py match.mp4 -w 5:00 -d 20 -o clip.mp4

# YouTube (requires yt-dlp + ffmpeg)
python video_person_zoom.py "https://www.youtube.com/watch?v=VIDEO_ID" -n 7 -w 1:30 -d 15 -o ./out.mp4
```

### Troubleshooting: AV1 message, tiny or unplayable MP4

#### What is going on

1. **`Your platform doesn't support hardware accelerated AV1 decoding`**  
   This usually comes from **FFmpeg / OpenCV** while decoding **AV1**. It means **no hardware AV1 decoder** is available; decoding may still proceed via **software**. The line is **not necessarily a fatal error**.

2. **Output file (e.g. `/tmp/abc.mp4`) is extremely small and won’t play**  
   Typical cause: **almost no frames were successfully decoded and written**. When the pipeline relied mainly on OpenCV `VideoCapture`, some **AV1** sources cause `read()` to **fail quickly or return almost no frames**, leaving a **near-empty, broken MP4** (often only a few KB to a few tens of KB).

#### Behavior in the script (what changed, in plain terms)

- **Trim-only mode (no `-n`)**: if **`ffmpeg`** is found, the script **prefers ffmpeg** to cut by `-w`/`-d` and writes **H.264** (retries without audio if needed). It **does not depend on OpenCV decoding the source**, which avoids many AV1 “empty file” cases.  
- **Tracking mode (`-n`)**: after opening the file, the script **tries to read the first frame**; if that fails, it tells you to **transcode to H.264** first.  
- **Both modes**: after writing, it checks **frame count written** and **output file size**; on obvious failure it errors and tries to remove bad output.

#### What you should do

**If you mainly need trimming (no `-n`):**  
Install **`ffmpeg`** and run again; the script will use **ffmpeg-based trimming** and you should get a playable MP4 in normal cases.

**If you must use tracking (`-n`):**  
Transcode the source to **H.264** first (OpenCV reads more reliably), for example:

```bash
ffmpeg -i source.mp4 -c:v libx264 -crf 23 -c:a copy source_h264.mp4
python video_person_zoom.py source_h264.mp4 -n 10 -o /tmp/out.mp4
```

**Also check:**  
Ensure **`-w` / `-d` are within the file duration** and the source is not corrupted; read the full terminal error if problems persist.

### Limitations (English)

- OCR quality depends on resolution, motion blur, and occlusions.  
- Before the first successful lock in tracking mode, full-frame placeholder frames may be written (still counted toward `-d` when clipping is enabled).  
- Ambiguous cases (e.g. duplicate numbers) may need manual verification.
