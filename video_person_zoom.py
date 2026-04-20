#!/usr/bin/env python3
"""
- INPUT only: download URL or copy local file to cwd (or -o); no transcode or tracking.
  仅 INPUT：URL 下载到本地，本地路径复制到当前目录（或 -o），不做转码与跟拍。
- With -n jersey number: detect + OCR tracking; optional -w/-d clip first.
  提供 -n：检测人物 + OCR 跟拍，可选 -w/-d 先截取片段。
- Without -n but with -w/-d: time-window trim only (no detect/OCR; prefers ffmpeg).
  无 -n 但有 -w/-d：仅按时间窗口截取（不跑检测/OCR，优先 ffmpeg）。

Usage / 用法:
  video_person_zoom.py INPUT [-o out.mp4]
  video_person_zoom.py INPUT -n 10 [-w TIME -d SEC] [-o out.mp4]
  video_person_zoom.py INPUT -w TIME -d SEC [-o out.mp4]

Deps / 依赖: tracking needs pip install -r requirements-person-zoom.txt (easyocr, ultralytics).
外部: ffmpeg (often required for yt-dlp merge).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _b(cn: str, en: str) -> str:
    """User-facing bilingual text: Chinese / English."""

    return f"{cn} / {en}"


def _is_remote(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _download_video(url: str) -> tuple[str, bool]:
    """Return (local path, delete temp dir). / 返回 (本地路径, 是否临时目录需删)。"""
    try:
        import yt_dlp
    except ImportError as e:
        raise SystemExit(
            _b(
                "缺少 yt-dlp，请执行: pip install yt-dlp\n并确保系统已安装 ffmpeg（用于合并音视频）。",
                "Missing yt-dlp. Run: pip install yt-dlp\nEnsure ffmpeg is installed for merging audio/video.",
            )
        ) from e

    tmpdir = tempfile.mkdtemp(prefix="vpz_")
    outtmpl = os.path.join(tmpdir, "source.%(ext)s")
    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for name in os.listdir(tmpdir):
        if name.startswith("source.") and not name.endswith(".part"):
            return os.path.join(tmpdir, name), True

    shutil.rmtree(tmpdir, ignore_errors=True)
    raise SystemExit(
        _b(
            "下载完成但未找到输出文件，请检查 URL 或 yt-dlp / ffmpeg 是否可用。",
            "Download finished but output file not found. Check URL, yt-dlp, and ffmpeg.",
        )
    )


def _download_or_copy_only(input_raw: str, output_path: str | None) -> str:
    """
    Download URL or copy local file to destination.
    仅下载 URL 或复制本地文件到目标路径。
    If output_path is None: URL → download_<ts>.<ext>; local → <name>_copy<suffix> in cwd.
    """
    tmpdir_to_remove: str | None = None
    try:
        if _is_remote(input_raw):
            local_tmp, is_temp = _download_video(input_raw)
            if is_temp:
                tmpdir_to_remove = str(Path(local_tmp).parent)
            ext = Path(local_tmp).suffix or ".mp4"
            if output_path:
                dest = os.path.abspath(output_path)
            else:
                dest = str(Path.cwd() / f"download_{int(time.time())}{ext}")
            d = os.path.dirname(dest)
            if d:
                os.makedirs(d, exist_ok=True)
            shutil.copy2(local_tmp, dest)
            return dest

        src = os.path.abspath(input_raw)
        if not os.path.isfile(src):
            raise SystemExit(_b(f"本地文件不存在: {src}", f"Local file not found: {src}"))
        if output_path:
            dest = os.path.abspath(output_path)
        else:
            sp = Path(src)
            dest = str(Path.cwd() / f"{sp.stem}_copy{sp.suffix}")
        d = os.path.dirname(dest)
        if d:
            os.makedirs(d, exist_ok=True)
        shutil.copy2(src, dest)
        return dest
    finally:
        if tmpdir_to_remove and os.path.isdir(tmpdir_to_remove):
            shutil.rmtree(tmpdir_to_remove, ignore_errors=True)


def _iou_xyxy(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    bb = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    u = aa + bb - inter
    return float(inter / u) if u > 1e-9 else 0.0


def _list_person_boxes(result) -> list[tuple[float, float, float, float]]:
    """All person boxes (xyxy, COCO class person) this frame. / 本帧人物框 xyxy。"""
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    cls = boxes.cls.detach().cpu().numpy()
    out: list[tuple[float, float, float, float]] = []
    for i in range(len(cls)):
        if int(round(float(cls[i]))) != 0:
            continue
        row = xyxy[i]
        out.append((float(row[0]), float(row[1]), float(row[2]), float(row[3])))
    return out


def _sort_person_boxes(
    boxes: list[tuple[float, float, float, float]],
    order: str,
) -> list[tuple[float, float, float, float]]:
    """Return sorted copy of boxes. / 按规则排序后的新列表。"""
    if not boxes:
        return []

    def stats(b: tuple[float, float, float, float]) -> tuple[float, float, float]:
        x1, y1, x2, y2 = b
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        ar = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        return cx, cy, ar

    scored: list[tuple[tuple[float, float, float, float], tuple[float, float, float]]] = [
        (b, stats(b)) for b in boxes
    ]

    if order == "area-desc":
        scored.sort(key=lambda t: (-t[1][2], t[1][0], t[1][1]))
    elif order == "area-asc":
        scored.sort(key=lambda t: (t[1][2], t[1][0], t[1][1]))
    elif order == "left":
        scored.sort(key=lambda t: (t[1][0], t[1][1], -t[1][2]))
    elif order == "right":
        scored.sort(key=lambda t: (-t[1][0], t[1][1], -t[1][2]))
    elif order == "top":
        scored.sort(key=lambda t: (t[1][1], t[1][0], -t[1][2]))
    elif order == "bottom":
        scored.sort(key=lambda t: (-t[1][1], t[1][0], -t[1][2]))
    else:
        raise ValueError(_b(f"未知排序规则: {order}", f"Unknown sort order: {order}"))
    return [t[0] for t in scored]


def _normalize_jersey_target(s: str) -> str:
    t = "".join(c for c in s.strip() if c.isdigit())
    if not t:
        raise ValueError(_b("球衣号码须为数字", "Jersey number must be digits only"))
    return t


def _parse_time_to_seconds(s: str) -> float:
    """Parse seconds, MM:SS, or H:MM:SS. / 解析秒数或 MM:SS / H:MM:SS。"""
    t = s.strip()
    if not t:
        raise ValueError(_b("时间点不能为空", "Time must not be empty"))
    if ":" not in t:
        return float(t)
    parts = t.split(":")
    if len(parts) == 2:
        m, sec = parts
        return int(m, 10) * 60 + float(sec)
    if len(parts) == 3:
        h, m, sec = parts
        return int(h, 10) * 3600 + int(m, 10) * 60 + float(sec)
    raise ValueError(_b(f"无法解析时间点: {s!r}", f"Cannot parse time: {s!r}"))


def _clip_window_seconds(
    video_len_sec: float,
    center_sec: float,
    duration_sec: float,
) -> tuple[float, float]:
    """
    Clip window [start,end] centered at center_sec, length duration_sec, clamped to video.
    以 center 为中心、总长 duration 的窗口，夹在片长内。
    """
    if video_len_sec <= 0:
        return 0.0, max(0.0, duration_sec)
    if duration_sec <= 0:
        raise ValueError(_b("时长必须大于 0", "Duration must be greater than 0"))
    if duration_sec >= video_len_sec:
        return 0.0, video_len_sec
    half = duration_sec / 2.0
    start = center_sec - half
    end = center_sec + half
    if start < 0.0:
        start = 0.0
        end = min(video_len_sec, duration_sec)
    elif end > video_len_sec:
        end = video_len_sec
        start = max(0.0, video_len_sec - duration_sec)
    return start, end


def _ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def _ffmpeg_extract_segment(
    input_path: str,
    output_path: str,
    start_sec: float,
    duration_sec: float,
) -> None:
    """
    Trim with ffmpeg to H.264+AAC MP4 (avoids OpenCV AV1 issues).
    用 ffmpeg 截取为 H.264 MP4，减轻 OpenCV 解 AV1 失败。
    """
    ff = _ffmpeg_bin()
    if not ff:
        raise RuntimeError(_b("未找到 ffmpeg", "ffmpeg not found in PATH"))

    base = [
        ff,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-ss",
        str(start_sec),
        "-t",
        str(duration_sec),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]
    cmd_with_audio = [*base, "-c:a", "aac", "-b:a", "192k", output_path]
    r = subprocess.run(cmd_with_audio, capture_output=True, text=True)
    if r.returncode != 0:
        cmd_an = [*base, "-an", output_path]
        r2 = subprocess.run(cmd_an, capture_output=True, text=True)
        if r2.returncode != 0:
            raise SystemExit(
                _b(
                    "ffmpeg 截取失败（含无音轨重试）。stderr:\n"
                    f"{r.stderr or r.stdout}\n---\n{r2.stderr or r2.stdout}",
                    "ffmpeg trim failed (including no-audio retry). stderr:\n"
                    f"{r.stderr or r.stdout}\n---\n{r2.stderr or r2.stdout}",
                )
            )


def _clip_segment_start_and_duration(
    fps: float,
    nframes: int,
    center_sec: float,
    clip_duration_sec: float,
) -> tuple[float, float]:
    """(start_sec, length_sec) same window as _clip_seek_cap. / 起点与长度秒。"""
    d = float(clip_duration_sec)
    c = float(center_sec)
    if nframes > 0 and fps > 0:
        vlen = nframes / fps
        start_sec, end_sec = _clip_window_seconds(vlen, c, d)
        return start_sec, end_sec - start_sec
    half = d / 2.0
    start_sec = max(0.0, c - half)
    return start_sec, d


def _ensure_capture_readable(cap: object, input_path: str) -> None:
    """Read first frame or exit with transcode hint. / 读首帧，失败则提示转码。"""
    import cv2

    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        raise SystemExit(
            _b(
                "无法从视频解码出第一帧。若片源为 AV1 或本机无硬解，OpenCV 可能读不到画面。\n"
                "请先转码为 H.264 再处理，例如：\n"
                f"  ffmpeg -i \"{input_path}\" -c:v libx264 -crf 23 -c:a copy \"{input_path}.h264.mp4\"",
                "Cannot decode the first frame (AV1 or no HW decode may fail in OpenCV).\n"
                "Transcode to H.264 first, e.g.:\n"
                f"  ffmpeg -i \"{input_path}\" -c:v libx264 -crf 23 -c:a copy \"{input_path}.h264.mp4\"",
            )
        )
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0.0)


def _assert_output_not_empty(path: str, frames_written: int) -> None:
    try:
        sz = os.path.getsize(path)
    except OSError:
        sz = 0
    if frames_written == 0 or sz < 512:
        try:
            os.remove(path)
        except OSError:
            pass
        raise SystemExit(
            _b(
                "输出视频几乎为空或无法写入有效帧（常见原因：输入为 AV1 且 OpenCV 未读到任何帧，"
                "或编码器不可用）。请先转 H.264 再运行，或安装 ffmpeg 后使用仅截取模式（将优先走 ffmpeg）。",
                "Output is nearly empty or no valid frames (e.g. AV1 not decoded by OpenCV, or encoder issue). "
                "Transcode to H.264 first, or install ffmpeg and use trim-only mode (prefers ffmpeg).",
            )
        )


def _clip_seek_cap(
    cap: object,
    fps: float,
    nframes: int,
    center_sec: float,
    clip_duration_sec: float,
) -> tuple[int, float, float]:
    """
    Seek capture to clip start; return (frame_count, start_sec, end_sec).
    定位到片段起点；返回 (帧数, 起点秒, 终点秒)。
    """
    import cv2

    d = float(clip_duration_sec)
    c = float(center_sec)
    if nframes > 0 and fps > 0:
        vlen = nframes / fps
        start_sec, end_sec = _clip_window_seconds(vlen, c, d)
        start_f = int(round(start_sec * fps))
        end_f = int(round(end_sec * fps))
        start_f = max(0, min(start_f, max(0, nframes - 1)))
        end_f = max(start_f + 1, min(nframes, end_f))
        clip_n = end_f - start_f
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_f))
        return clip_n, start_sec, end_sec
    half = d / 2.0
    start_sec = max(0.0, c - half)
    end_sec = start_sec + d
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
    clip_n = max(1, int(round(d * fps)))
    return clip_n, start_sec, end_sec


def process_clip_only(
    input_path: str,
    output_path: str,
    *,
    center_sec: float,
    duration_sec: float,
) -> None:
    """Trim [-w,-d] window; prefers ffmpeg. / 仅截取时间窗，优先 ffmpeg。"""
    import cv2

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise SystemExit(_b(f"无法打开视频: {input_path}", f"Cannot open video: {input_path}"))

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    start_sec, seg_dur = _clip_segment_start_and_duration(
        fps, nframes, center_sec, duration_sec
    )
    end_sec_print = start_sec + seg_dur
    print(
        _b(
            f"仅截取片段: 约 {start_sec:.3f}s – {end_sec_print:.3f}s，长 {seg_dur:.3f}s。",
            f"Trim clip: ~{start_sec:.3f}s – {end_sec_print:.3f}s, length {seg_dur:.3f}s.",
        ),
        file=sys.stderr,
    )

    if _ffmpeg_bin():
        print(
            _b(
                "使用 ffmpeg 截取（推荐，可避免 AV1 等在 OpenCV 下无法解码的问题）。",
                "Using ffmpeg to trim (recommended; avoids AV1 decode issues in OpenCV).",
            ),
            file=sys.stderr,
        )
        cap.release()
        try:
            _ffmpeg_extract_segment(input_path, output_path, start_sec, seg_dur)
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(_b(f"ffmpeg 截取失败: {e}", f"ffmpeg trim failed: {e}")) from e
        try:
            sz = os.path.getsize(output_path)
        except OSError:
            sz = 0
        if sz < 512:
            try:
                os.remove(output_path)
            except OSError:
                pass
            raise SystemExit(
                _b(
                    "ffmpeg 输出过小，可能时间段超出片长或输入损坏。请检查 -w/-d 与片源。",
                    "ffmpeg output too small; clip may exceed duration or input is bad. Check -w/-d and source.",
                )
            )
        print(
            _b(
                f"已写入: {output_path}（{sz} 字节）",
                f"Written: {output_path} ({sz} bytes)",
            ),
            file=sys.stderr,
        )
        return

    cap.release()
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise SystemExit(_b(f"无法重新打开视频: {input_path}", f"Cannot reopen video: {input_path}"))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    clip_frames_total, start_sec_print, end_sec_print = _clip_seek_cap(
        cap, fps, nframes, center_sec, duration_sec
    )
    print(
        _b(
            f"回退 OpenCV 逐帧写入: 约 {start_sec_print:.3f}s – {end_sec_print:.3f}s，"
            f"共 {clip_frames_total} 帧（未安装 ffmpeg 时可用性较差）。",
            f"Fallback OpenCV frame write: ~{start_sec_print:.3f}s – {end_sec_print:.3f}s, "
            f"{clip_frames_total} frames (less reliable without ffmpeg).",
        ),
        file=sys.stderr,
    )

    out_w, out_h = w - (w % 2), h - (h % 2)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))
    if not writer.isOpened():
        cap.release()
        raise SystemExit(_b(f"无法创建输出文件: {output_path}", f"Cannot create output: {output_path}"))

    frames_out = 0
    try:
        while frames_out < clip_frames_total:
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h))
            out = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
            writer.write(out)
            frames_out += 1
            if clip_frames_total and frames_out % max(1, clip_frames_total // 20) == 0:
                pct = 100.0 * frames_out / clip_frames_total
                print(
                    f"\r{_b('进度', 'Progress')}: {frames_out}/{clip_frames_total} ({pct:.0f}%)",
                    end="",
                    file=sys.stderr,
                )
    finally:
        print(file=sys.stderr)
        cap.release()
        writer.release()

    _assert_output_not_empty(output_path, frames_out)


def _jersey_roi_xyxy(
    frame_shape: tuple[int, ...],
    xyxy: tuple[float, float, float, float],
) -> tuple[int, int, int, int] | None:
    """Upper-torso ROI for jersey OCR; integer xyxy. / 胸口附近 ROI。"""
    fh, fw = int(frame_shape[0]), int(frame_shape[1])
    x1, y1, x2, y2 = xyxy
    pw = max(1.0, x2 - x1)
    ph = max(1.0, y2 - y1)
    nx1 = max(0, int(x1 + 0.12 * pw))
    nx2 = min(fw, int(x1 + 0.88 * pw))
    ny1 = max(0, int(y1 + 0.06 * ph))
    ny2 = min(fh, int(y1 + 0.52 * ph))
    if nx2 <= nx1 + 8 or ny2 <= ny1 + 8:
        return None
    return nx1, ny1, nx2, ny2


def _ocr_text_matches_target(texts: list[str], target: str) -> bool:
    """Whether OCR digit runs match target exactly. / 数字串是否与目标一致。"""
    segs: list[str] = []
    for raw in texts:
        segs.append("".join(c for c in raw if c.isdigit()))
    combined = "".join(segs)
    if combined == target:
        return True
    return any(s == target for s in segs if s)


def _ocr_jersey_match(
    reader,
    frame_bgr,
    xyxy: tuple[float, float, float, float],
    target: str,
    min_conf: float,
) -> bool:
    import cv2

    roi = _jersey_roi_xyxy(frame_bgr.shape, xyxy)
    if roi is None:
        return False
    x1, y1, x2, y2 = roi
    crop = frame_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    if crop.ndim == 3 and crop.shape[2] == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    h, w = crop.shape[0], crop.shape[1]
    scale = max(1.0, 200.0 / float(min(w, h)))
    if scale > 1.02:
        crop = cv2.resize(
            crop,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_CUBIC,
        )
    try:
        det = reader.readtext(crop, allowlist="0123456789", detail=1)
    except Exception:
        try:
            det = reader.readtext(crop, detail=1)
        except Exception:
            return False
    texts: list[str] = []
    for item in det:
        if len(item) >= 3:
            _bb, tx, cf = item[0], item[1], float(item[2])
        else:
            _bb, tx = item[0], item[1]
            cf = 1.0
        if cf < min_conf:
            continue
        texts.append(tx)
    return _ocr_text_matches_target(texts, target)


def _find_box_by_jersey_scan(
    reader,
    frame_bgr,
    persons: list[tuple[float, float, float, float]],
    target: str,
    min_conf: float,
) -> tuple[float, float, float, float] | None:
    """OCR largest persons first; first matching box. / 从大到小 OCR，首匹配框。"""
    ranked = _sort_person_boxes(persons, "area-desc")
    for b in ranked:
        if _ocr_jersey_match(reader, frame_bgr, b, target, min_conf):
            return b
    return None


def _relock_by_jersey(
    reader,
    frame_bgr,
    persons: list[tuple[float, float, float, float]],
    prev_xyxy: tuple[float, float, float, float],
    target: str,
    min_conf: float,
) -> tuple[float, float, float, float] | None:
    """On drift, prefer high-IoU persons for OCR. / 跟丢时优先高 IoU 人体 OCR。"""
    order = sorted(
        range(len(persons)),
        key=lambda j: _iou(prev_xyxy, persons[j]),
        reverse=True,
    )
    for j in order:
        b = persons[j]
        if _ocr_jersey_match(reader, frame_bgr, b, target, min_conf):
            return b
    return None


def _expand_and_clip_box(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    w: int,
    h: int,
    pad: float,
) -> tuple[int, int, int, int]:
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    bw = (x2 - x1) * (1.0 + pad)
    bh = (y2 - y1) * (1.0 + pad)
    # Match frame aspect ratio / 与画面同宽高比，避免拉伸人物
    ar_frame = w / max(h, 1)
    ar_box = bw / max(bh, 1e-6)
    if ar_box > ar_frame:
        bh = bw / ar_frame
    else:
        bw = bh * ar_frame

    nx1 = int(round(cx - bw / 2.0))
    ny1 = int(round(cy - bh / 2.0))
    nx2 = int(round(cx + bw / 2.0))
    ny2 = int(round(cy + bh / 2.0))

    if nx1 < 0:
        nx2 -= nx1
        nx1 = 0
    if ny1 < 0:
        ny2 -= ny1
        ny1 = 0
    if nx2 > w:
        shift = nx2 - w
        nx1 = max(0, nx1 - shift)
        nx2 = w
    if ny2 > h:
        shift = ny2 - h
        ny1 = max(0, ny1 - shift)
        ny2 = h

    nx1 = max(0, min(nx1, w - 1))
    ny1 = max(0, min(ny1, h - 1))
    nx2 = max(nx1 + 1, min(nx2, w))
    ny2 = max(ny1 + 1, min(ny2, h))
    return nx1, ny1, nx2, ny2


def _smooth_box(
    prev: tuple[float, float, float, float] | None,
    cur: tuple[float, float, float, float],
    alpha: float,
) -> tuple[float, float, float, float]:
    if prev is None:
        return cur
    return tuple(alpha * c + (1.0 - alpha) * p for p, c in zip(prev, cur))


def process_video(
    input_path: str,
    output_path: str,
    *,
    model_name: str,
    padding: float,
    smooth: float,
    device: str | None,
    target_order: str,
    target_index: int,
    min_iou: float,
    jersey: str,
    ocr_min_conf: float,
    max_jersey_search_frames: int,
    clip_center_sec: float | None,
    clip_duration_sec: float | None,
) -> None:
    try:
        import cv2
        import easyocr
        from ultralytics import YOLO
    except ImportError as e:
        raise SystemExit(
            _b(
                "缺少依赖，请执行: pip install -r requirements-person-zoom.txt",
                "Missing dependencies. Run: pip install -r requirements-person-zoom.txt",
            )
        ) from e

    use_cuda = bool(device and device.startswith("cuda"))
    if not use_cuda:
        try:
            import torch

            use_cuda = torch.cuda.is_available()
        except Exception:
            use_cuda = False

    ocr_reader = easyocr.Reader(["en"], gpu=use_cuda)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise SystemExit(_b(f"无法打开视频: {input_path}", f"Cannot open video: {input_path}"))

    _ensure_capture_readable(cap, input_path)

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    clip_frames_total: int | None = None
    if clip_center_sec is not None and clip_duration_sec is not None:
        clip_frames_total, start_sec_print, end_sec_print = _clip_seek_cap(
            cap, fps, nframes, float(clip_center_sec), float(clip_duration_sec)
        )
        print(
            _b(
                f"输出片段: 约 {start_sec_print:.3f}s – {end_sec_print:.3f}s，"
                f"共 {clip_frames_total} 帧（-w 中心 -d 总长）。",
                f"Output clip: ~{start_sec_print:.3f}s – {end_sec_print:.3f}s, "
                f"{clip_frames_total} frames (-w center, -d duration).",
            ),
            file=sys.stderr,
        )
    elif clip_center_sec is not None or clip_duration_sec is not None:
        raise SystemExit(
            _b(
                "请同时提供 -w 与 -d，或两者都不提供以处理整段视频。",
                "Provide both -w and -d together, or neither for full video.",
            )
        )

    out_w, out_h = w - (w % 2), h - (h % 2)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))
    if not writer.isOpened():
        cap.release()
        raise SystemExit(_b(f"无法创建输出文件: {output_path}", f"Cannot create output: {output_path}"))

    model = YOLO(model_name)
    if device:
        model.to(device)

    prev_smooth: tuple[float, float, float, float] | None = None
    last_box: tuple[float, float, float, float] | None = None
    locked_ref_xyxy: tuple[float, float, float, float] | None = None
    warned_relock = False
    warned_jersey_relock = False
    lock_announced = False
    frame_i = 0
    frames_out = 0
    total_written = 0
    infer_device = device or "cpu"
    progress_total = clip_frames_total if clip_frames_total is not None else nframes

    def _write_full_and_maybe_abort() -> None:
        """Full frame until lock or search limit. / 锁定前全画面或超帧退出。"""
        nonlocal frames_out, total_written
        out = cv2.resize(frame, (out_w, out_h))
        writer.write(out)
        total_written += 1
        if clip_frames_total is not None:
            frames_out += 1
        if frame_i == 1:
            print(
                _b(
                    "正在扫描球衣号码：输出暂为全画面，直至首次识别成功。",
                    "Scanning jersey number: full frame until first successful read.",
                ),
                file=sys.stderr,
            )
        if (
            max_jersey_search_frames > 0
            and locked_ref_xyxy is None
            and frame_i >= max_jersey_search_frames
        ):
            raise SystemExit(
                _b(
                    f"前 {max_jersey_search_frames} 帧内未识别到球衣 {jersey}。"
                    "可提高 --max-search-frames、换更清晰片段，或略调 --ocr-min-conf。",
                    f"No jersey {jersey} found in the first {max_jersey_search_frames} frames. "
                    "Try --max-search-frames, a clearer clip, or --ocr-min-conf.",
                )
            )

    try:
        while True:
            if clip_frames_total is not None and frames_out >= clip_frames_total:
                break
            ok, frame = cap.read()
            if not ok:
                break
            frame_i += 1
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h))

            results = model.predict(
                frame,
                classes=[0],
                verbose=False,
                device=infer_device,
            )
            persons = _list_person_boxes(results[0])
            box: tuple[float, float, float, float] | None = None

            if persons:
                if locked_ref_xyxy is not None:
                    best_j = max(
                        range(len(persons)),
                        key=lambda j: _iou(locked_ref_xyxy, persons[j]),
                    )
                    best_iou = _iou(locked_ref_xyxy, persons[best_j])
                    if best_iou >= min_iou:
                        box = persons[best_j]
                    else:
                        ocr_hit = _relock_by_jersey(
                            ocr_reader,
                            frame,
                            persons,
                            locked_ref_xyxy,
                            jersey,
                            ocr_min_conf,
                        )
                        if ocr_hit is not None:
                            box = ocr_hit
                            if not warned_jersey_relock:
                                print(
                                    _b(
                                        f"注意: IoU 过低({best_iou:.2f})，已用球衣号码 {jersey} 重新锁定。",
                                        f"Note: low IoU ({best_iou:.2f}); re-locked by jersey {jersey} via OCR.",
                                    ),
                                    file=sys.stderr,
                                )
                                warned_jersey_relock = True
                        elif last_box is not None:
                            box = last_box
                            if not warned_relock:
                                print(
                                    _b(
                                        f"注意: IoU 低且未 OCR 到 {jersey}，暂沿用上一帧位置。",
                                        f"Note: low IoU and OCR missed {jersey}; holding last frame position.",
                                    ),
                                    file=sys.stderr,
                                )
                                warned_relock = True
                        else:
                            sorted_b = _sort_person_boxes(persons, target_order)
                            bi = min(max(0, target_index), len(sorted_b) - 1)
                            box = sorted_b[bi]
                else:
                    jb = _find_box_by_jersey_scan(
                        ocr_reader, frame, persons, jersey, ocr_min_conf
                    )
                    if jb is None:
                        _write_full_and_maybe_abort()
                        continue
                    box = jb
                    if not lock_announced:
                        print(
                            _b(
                                f"已锁定球衣号码 {jersey}（第 {frame_i} 帧）。",
                                f"Locked jersey {jersey} (frame {frame_i}).",
                            ),
                            file=sys.stderr,
                        )
                        lock_announced = True

                locked_ref_xyxy = box
                last_box = box
            elif last_box is not None:
                box = last_box
            else:
                _write_full_and_maybe_abort()
                continue

            x1, y1, x2, y2 = box
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            cur = (cx, cy, x2 - x1, y2 - y1)
            sx, sy, sw, sh = _smooth_box(prev_smooth, cur, smooth)
            prev_smooth = (sx, sy, sw, sh)

            hx1 = sx - sw / 2.0
            hy1 = sy - sh / 2.0
            hx2 = sx + sw / 2.0
            hy2 = sy + sh / 2.0
            ix1, iy1, ix2, iy2 = _expand_and_clip_box(hx1, hy1, hx2, hy2, w, h, padding)

            crop = frame[iy1:iy2, ix1:ix2]
            out = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            writer.write(out)
            frames_out += 1
            total_written += 1

            if clip_frames_total is not None:
                if clip_frames_total and frames_out % max(1, clip_frames_total // 20) == 0:
                    pct = 100.0 * frames_out / clip_frames_total
                    print(
                        f"\r{_b('进度', 'Progress')}: {frames_out}/{clip_frames_total} ({pct:.0f}%)",
                        end="",
                        file=sys.stderr,
                    )
            elif progress_total and frame_i % max(1, progress_total // 20) == 0:
                pct = 100.0 * frame_i / progress_total
                print(
                    f"\r{_b('进度', 'Progress')}: {frame_i}/{progress_total} ({pct:.0f}%)",
                    end="",
                    file=sys.stderr,
                )
    finally:
        print(file=sys.stderr)
        cap.release()
        writer.release()

    _assert_output_not_empty(output_path, total_written)

    if last_box is None:
        raise SystemExit(
            _b(
                f"整段视频未成功锁定球衣号码 {jersey}（需在某一帧同时检出人物并 OCR 到该号码）。",
                f"Could not lock jersey {jersey}: need at least one frame with a person and readable number.",
            )
        )


def main() -> None:
    p = argparse.ArgumentParser(
        description=_b(
            "仅 INPUT：下载或复制；或 -n 跟拍；或无 -n 时用 -w/-d 截取片段。",
            "INPUT only: download/copy; or -n tracking; or -w/-d trim without -n.",
        )
    )
    p.add_argument(
        "input",
        help=_b(
            "本地视频路径，或 http(s) URL（yt-dlp 下载，如 YouTube）",
            "Local video path or http(s) URL (downloaded via yt-dlp, e.g. YouTube)",
        ),
    )
    p.add_argument(
        "-n",
        "--number",
        dest="jersey_number",
        default=None,
        metavar="NUM",
        help=_b(
            "要跟拍的球衣号码（仅数字）。无 -n 且无 -w/-d：仅下载或复制",
            "Jersey number (digits). Without -n and without -w/-d: download or copy only",
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default="",
        help=_b(
            "输出 MP4 路径；默认当前目录自动命名",
            "Output MP4 path; default auto name in current directory",
        ),
    )
    p.add_argument(
        "--model",
        default="yolov8n.pt",
        help=_b(
            "Ultralytics 模型名或权重路径，默认 yolov8n.pt（首次可自动下载）",
            "Ultralytics model name or weights path; default yolov8n.pt (may auto-download)",
        ),
    )
    p.add_argument(
        "--padding",
        type=float,
        default=0.25,
        help=_b(
            "人物框外留白比例（相对宽高），默认 0.25",
            "Extra margin around person box; default 0.25",
        ),
    )
    p.add_argument(
        "--smooth",
        type=float,
        default=0.35,
        help=_b(
            "框平滑系数 0~1，越大越贴近当前检测、可能更抖，默认 0.35",
            "Box smoothing 0–1; higher follows detection more closely; default 0.35",
        ),
    )
    p.add_argument(
        "--device",
        default="",
        help=_b(
            "推理设备，如 cpu、cuda:0；留空由 Ultralytics 选择",
            "Inference device, e.g. cpu, cuda:0; empty lets Ultralytics choose",
        ),
    )
    p.add_argument(
        "--target-order",
        default="area-desc",
        choices=(
            "area-desc",
            "area-asc",
            "left",
            "right",
            "top",
            "bottom",
        ),
        help=_b(
            "多人时排序再取 --target-index：面积或左/右/上/下",
            "When multiple people: sort order before --target-index",
        ),
    )
    p.add_argument(
        "--target-index",
        type=int,
        default=0,
        help=_b(
            "--target-order 下的 0 起始下标（如 left 且 1 为左起第二人）",
            "0-based index after --target-order (e.g. left + 1 = second from left)",
        ),
    )
    p.add_argument(
        "--min-iou",
        type=float,
        default=0.2,
        help=_b(
            "帧间 IoU 低于该值时尝试 OCR 重锁，默认 0.2",
            "If IoU vs previous box is below this, try OCR re-lock; default 0.2",
        ),
    )
    p.add_argument(
        "--ocr-min-conf",
        type=float,
        default=0.15,
        help=_b(
            "EasyOCR 置信度下限，困难时可降到 0.08~0.12，默认 0.15",
            "EasyOCR min confidence; try 0.08–0.12 if hard; default 0.15",
        ),
    )
    p.add_argument(
        "--max-search-frames",
        type=int,
        default=2400,
        help=_b(
            "从处理起点起最多多少帧内须首次识别号码；0 不限制；默认 2400",
            "Max frames from start to first successful number read; 0 = unlimited; default 2400",
        ),
    )
    p.add_argument(
        "-w",
        "--window",
        type=str,
        default=None,
        metavar="TIME",
        help=_b(
            "片段中心时间（秒或 MM:SS / H:MM:SS）；须与 -d 同用",
            "Clip center time; use with -d",
        ),
    )
    p.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        help=_b(
            "片段总时长（秒），以 -w 为中心对称截取；须与 -w 同用",
            "Clip length in seconds, symmetric around -w; use with -w",
        ),
    )
    args = p.parse_args()

    if (args.window is None) != (args.duration is None):
        p.error(
            _b(
                "请同时提供 -w 与 -d，或两者都不提供。",
                "Provide both -w and -d, or neither.",
            )
        )

    raw = args.input.strip()
    if not raw:
        p.error(_b("请提供输入路径或 URL", "Provide input path or URL"))

    has_jersey = bool(args.jersey_number and str(args.jersey_number).strip())
    has_clip = args.window is not None

    if has_jersey:
        try:
            jersey_norm = _normalize_jersey_target(str(args.jersey_number))
        except ValueError as e:
            p.error(str(e))
        clip_center_sec: float | None = None
        clip_duration_sec: float | None = None
        if has_clip:
            try:
                clip_center_sec = _parse_time_to_seconds(args.window)
            except ValueError as e:
                p.error(str(e))
            clip_duration_sec = float(args.duration)
            if clip_duration_sec <= 0:
                p.error(_b("-d 时长必须大于 0", "-d duration must be positive"))
    elif has_clip:
        try:
            clip_only_center = _parse_time_to_seconds(args.window)
        except ValueError as e:
            p.error(str(e))
        clip_only_duration = float(args.duration)
        if clip_only_duration <= 0:
            p.error(_b("-d 时长必须大于 0", "-d duration must be positive"))
    else:
        out_opt = args.output.strip() if args.output else None
        final_path = _download_or_copy_only(raw, out_opt)
        print(final_path)
        return

    clip_trim = not has_jersey and has_clip

    tmpdir_to_remove: str | None = None
    local_path = raw

    if _is_remote(raw):
        local_path, is_temp = _download_video(raw)
        if is_temp:
            tmpdir_to_remove = str(Path(local_path).parent)
        if args.output:
            out_path = args.output
        elif clip_trim:
            out_path = str(Path.cwd() / f"clip_{int(time.time())}.mp4")
        else:
            out_path = str(
                Path.cwd() / f"jersey{jersey_norm}_zoom_{int(time.time())}.mp4"
            )
    else:
        local_path = os.path.abspath(raw)
        if not os.path.isfile(local_path):
            p.error(_b(f"本地文件不存在: {local_path}", f"Local file not found: {local_path}"))
        if args.output:
            out_path = os.path.abspath(args.output)
        elif clip_trim:
            src = Path(local_path)
            out_path = str(src.with_name(f"{src.stem}_clip.mp4"))
        else:
            src = Path(local_path)
            out_path = str(
                src.with_name(f"{src.stem}_jersey{jersey_norm}_zoom.mp4")
            )

    out_path = os.path.abspath(out_path)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    device = args.device.strip() or None
    try:
        if clip_trim:
            process_clip_only(
                local_path,
                out_path,
                center_sec=clip_only_center,
                duration_sec=clip_only_duration,
            )
        else:
            msearch = args.max_search_frames
            if msearch < 0:
                p.error(_b("--max-search-frames 不能为负数", "--max-search-frames must be non-negative"))
            process_video(
                local_path,
                out_path,
                model_name=args.model,
                padding=max(0.0, args.padding),
                smooth=min(1.0, max(0.01, args.smooth)),
                device=device,
                target_order=args.target_order,
                target_index=max(0, args.target_index),
                min_iou=min(1.0, max(0.0, args.min_iou)),
                jersey=jersey_norm,
                ocr_min_conf=min(1.0, max(0.0, float(args.ocr_min_conf))),
                max_jersey_search_frames=msearch,
                clip_center_sec=clip_center_sec,
                clip_duration_sec=clip_duration_sec,
            )
    finally:
        if tmpdir_to_remove and os.path.isdir(tmpdir_to_remove):
            shutil.rmtree(tmpdir_to_remove, ignore_errors=True)

    print(out_path)


if __name__ == "__main__":
    main()
