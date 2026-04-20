#!/usr/bin/env python3
"""
- 仅 INPUT：URL 则下载到本地，本地路径则复制到当前目录（或 -o），不做转码与跟拍。
- 提供 -n 球衣号码：检测人物 + OCR 跟拍，可选 -w/-d 截取片段再处理。
- 不提供 -n 但提供 -w/-d：仅按时间窗口截取片段（不跑检测/OCR，优先 ffmpeg）。

用法:
  video_person_zoom.py INPUT [-o out.mp4]
  video_person_zoom.py INPUT -n 10 [-w TIME -d SEC] [-o out.mp4]
  video_person_zoom.py INPUT -w TIME -d SEC [-o out.mp4]

依赖：跟拍模式需 pip install -r requirements-person-zoom.txt（含 easyocr、ultralytics）
外部：ffmpeg（yt-dlp 合并音视频时通常需要）。
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


def _is_remote(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _download_video(url: str) -> tuple[str, bool]:
    """返回 (本地媒体路径, 是否为临时文件需删除)。"""
    try:
        import yt_dlp
    except ImportError as e:
        raise SystemExit(
            "缺少 yt-dlp，请执行: pip install yt-dlp\n"
            "并确保系统已安装 ffmpeg（用于合并音视频）。"
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
    raise SystemExit("下载完成但未找到输出文件，请检查 URL 或 yt-dlp / ffmpeg 是否可用。")


def _download_or_copy_only(input_raw: str, output_path: str | None) -> str:
    """
    仅下载（URL）或复制（本地文件）到目标路径。
    output_path 为 None 时：URL → 当前目录 download_<时间戳>.<扩展名>；本地 → 当前目录 <原名>_copy<后缀>
    返回最终绝对路径。
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
            raise SystemExit(f"本地文件不存在: {src}")
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
    """当前帧所有人物框 (xyxy)，仅 COCO 类别 person。"""
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
    """按规则排序后返回新列表（不修改入参）。"""
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
        raise ValueError(f"未知排序规则: {order}")
    return [t[0] for t in scored]


def _normalize_jersey_target(s: str) -> str:
    t = "".join(c for c in s.strip() if c.isdigit())
    if not t:
        raise ValueError("球衣号码须为数字")
    return t


def _parse_time_to_seconds(s: str) -> float:
    """支持纯秒数、MM:SS、H:MM:SS（小时可为多位）。"""
    t = s.strip()
    if not t:
        raise ValueError("时间点不能为空")
    if ":" not in t:
        return float(t)
    parts = t.split(":")
    if len(parts) == 2:
        m, sec = parts
        return int(m, 10) * 60 + float(sec)
    if len(parts) == 3:
        h, m, sec = parts
        return int(h, 10) * 3600 + int(m, 10) * 60 + float(sec)
    raise ValueError(f"无法解析时间点: {s!r}")


def _clip_window_seconds(
    video_len_sec: float,
    center_sec: float,
    duration_sec: float,
) -> tuple[float, float]:
    """
    以 center_sec 为中心、总长 duration_sec 的窗口，夹在 [0, video_len_sec] 内。
    若视频短于 duration，则返回整段 [0, video_len_sec]。
    """
    if video_len_sec <= 0:
        return 0.0, max(0.0, duration_sec)
    if duration_sec <= 0:
        raise ValueError("时长必须大于 0")
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
    用 ffmpeg 按时间截取并输出 H.264 + AAC 的 MP4，避免 OpenCV 解码 AV1 等格式失败导致空文件。
    """
    ff = _ffmpeg_bin()
    if not ff:
        raise RuntimeError("未找到 ffmpeg")

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
                "ffmpeg 截取失败（含无音轨重试）。stderr:\n"
                f"{r.stderr or r.stdout}\n---\n{r2.stderr or r2.stdout}"
            )


def _clip_segment_start_and_duration(
    fps: float,
    nframes: int,
    center_sec: float,
    clip_duration_sec: float,
) -> tuple[float, float]:
    """返回 (起点秒, 片段长度秒)，与 _clip_seek_cap 使用的窗口一致。"""
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
    """读取首帧；失败时提示 AV1 等格式需先转码。"""
    import cv2

    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        raise SystemExit(
            "无法从视频解码出第一帧。若片源为 AV1 或本机无硬解，OpenCV 可能读不到画面。\n"
            "请先转码为 H.264 再处理，例如：\n"
            f"  ffmpeg -i \"{input_path}\" -c:v libx264 -crf 23 -c:a copy \"{input_path}.h264.mp4\""
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
            "输出视频几乎为空或无法写入有效帧（常见原因：输入为 AV1 且 OpenCV 未读到任何帧，"
            "或编码器不可用）。请先转 H.264 再运行，或安装 ffmpeg 后使用仅截取模式（将优先走 ffmpeg）。"
        )


def _clip_seek_cap(
    cap: object,
    fps: float,
    nframes: int,
    center_sec: float,
    clip_duration_sec: float,
) -> tuple[int, float, float]:
    """
    将 VideoCapture 定位到以 center_sec 为中心、总长 clip_duration_sec 的窗口起点。
    返回 (输出帧数, 窗口起点秒, 窗口终点秒)。
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
    """仅截取 [-w,-d] 时间窗口。若系统有 ffmpeg，优先用其截取（兼容 AV1，避免 OpenCV 解码失败）。"""
    import cv2

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise SystemExit(f"无法打开视频: {input_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    start_sec, seg_dur = _clip_segment_start_and_duration(
        fps, nframes, center_sec, duration_sec
    )
    end_sec_print = start_sec + seg_dur
    print(
        f"仅截取片段: 约 {start_sec:.3f}s – {end_sec_print:.3f}s，"
        f"长 {seg_dur:.3f}s。",
        file=sys.stderr,
    )

    if _ffmpeg_bin():
        print("使用 ffmpeg 截取（推荐，可避免 AV1 等在 OpenCV 下无法解码的问题）。", file=sys.stderr)
        cap.release()
        try:
            _ffmpeg_extract_segment(input_path, output_path, start_sec, seg_dur)
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(f"ffmpeg 截取失败: {e}") from e
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
                "ffmpeg 输出过小，可能时间段超出片长或输入损坏。请检查 -w/-d 与片源。"
            )
        print(f"已写入: {output_path}（{sz} 字节）", file=sys.stderr)
        return

    cap.release()
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise SystemExit(f"无法重新打开视频: {input_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    clip_frames_total, start_sec_print, end_sec_print = _clip_seek_cap(
        cap, fps, nframes, center_sec, duration_sec
    )
    print(
        f"回退 OpenCV 逐帧写入: 约 {start_sec_print:.3f}s – {end_sec_print:.3f}s，"
        f"共 {clip_frames_total} 帧（未安装 ffmpeg 时可用性较差）。",
        file=sys.stderr,
    )

    out_w, out_h = w - (w % 2), h - (h % 2)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))
    if not writer.isOpened():
        cap.release()
        raise SystemExit(f"无法创建输出文件: {output_path}")

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
                    f"\r进度: {frames_out}/{clip_frames_total} ({pct:.0f}%)",
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
    """人体框内偏上区域（胸口号码常见位置），返回整数 xyxy。"""
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
    """合并各段数字后是否与目标完全一致（避免子串误匹配）。"""
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
    """按人体框从大到小依次 OCR，返回首个匹配号码的框。"""
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
    """跟丢时优先尝试与上一框 IoU 较大的人体上的 OCR。"""
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
    # 保持与画面相同宽高比，避免拉伸人物
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
            "缺少依赖，请执行: pip install -r requirements-person-zoom.txt"
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
        raise SystemExit(f"无法打开视频: {input_path}")

    _ensure_readable(cap, input_path)

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
            f"输出片段: 约 {start_sec_print:.3f}s – {end_sec_print:.3f}s，"
            f"共 {clip_frames_total} 帧（-w 中心 -d 总长）。",
            file=sys.stderr,
        )
    elif clip_center_sec is not None or clip_duration_sec is not None:
        raise SystemExit("请同时提供 -w 与 -d，或两者都不提供以处理整段视频。")

    out_w, out_h = w - (w % 2), h - (h % 2)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))
    if not writer.isOpened():
        cap.release()
        raise SystemExit(f"无法创建输出文件: {output_path}")

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
        """未锁定前输出全画面；超过搜索上限则退出。"""
        nonlocal frames_out, total_written
        out = cv2.resize(frame, (out_w, out_h))
        writer.write(out)
        total_written += 1
        if clip_frames_total is not None:
            frames_out += 1
        if frame_i == 1:
            print(
                "正在扫描球衣号码：输出暂为全画面，直至首次识别成功。",
                file=sys.stderr,
            )
        if (
            max_jersey_search_frames > 0
            and locked_ref_xyxy is None
            and frame_i >= max_jersey_search_frames
        ):
            raise SystemExit(
                f"前 {max_jersey_search_frames} 帧内未识别到球衣 {jersey}。"
                "可提高 --max-search-frames、换更清晰片段，或略调 --ocr-min-conf。"
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
                                    f"注意: IoU 过低({best_iou:.2f})，已用球衣号码 {jersey} 重新锁定。",
                                    file=sys.stderr,
                                )
                                warned_jersey_relock = True
                        elif last_box is not None:
                            box = last_box
                            if not warned_relock:
                                print(
                                    f"注意: IoU 低且未 OCR 到 {jersey}，暂沿用上一帧位置。",
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
                            f"已锁定球衣号码 {jersey}（第 {frame_i} 帧）。",
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
                        f"\r进度: {frames_out}/{clip_frames_total} ({pct:.0f}%)",
                        end="",
                        file=sys.stderr,
                    )
            elif progress_total and frame_i % max(1, progress_total // 20) == 0:
                pct = 100.0 * frame_i / progress_total
                print(
                    f"\r进度: {frame_i}/{progress_total} ({pct:.0f}%)",
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
            f"整段视频未成功锁定球衣号码 {jersey}（需在某一帧同时检出人物并 OCR 到该号码）。"
        )


def main() -> None:
    p = argparse.ArgumentParser(
        description="仅 INPUT：下载或复制；或 -n 跟拍；或无 -n 时用 -w/-d 截取片段。"
    )
    p.add_argument(
        "input",
        help="本地视频路径，或 http(s) 媒体地址（由 yt-dlp 下载，常见为 YouTube 链接）",
    )
    p.add_argument(
        "-n",
        "--number",
        dest="jersey_number",
        default=None,
        metavar="NUM",
        help="要跟拍的球衣号码（仅数字）。不提供且不提供 -w/-d 时：仅下载 URL 或复制本地文件",
    )
    p.add_argument(
        "-o",
        "--output",
        default="",
        help="输出 mp4 路径；默认写入当前目录下的自动命名文件",
    )
    p.add_argument(
        "--model",
        default="yolov8n.pt",
        help="Ultralytics 模型名或权重路径，默认 yolov8n.pt（首次会自动下载）",
    )
    p.add_argument(
        "--padding",
        type=float,
        default=0.25,
        help="在人物框外额外留白比例（相对宽高），默认 0.25",
    )
    p.add_argument(
        "--smooth",
        type=float,
        default=0.35,
        help="框位置平滑系数 0~1，越大越贴近当前检测、抖动越大，默认 0.35",
    )
    p.add_argument(
        "--device",
        default="",
        help="推理设备，例如 cpu、cuda:0；留空则由 Ultralytics 自行选择",
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
        help="多人时按何种顺序编号再取 --target-index：面积从大到小/从小到大，或按画面左/右/上/下位置",
    )
    p.add_argument(
        "--target-index",
        type=int,
        default=0,
        help="在 --target-order 排序下的 0 起始下标，例如 left 且 1 表示「从左数第二个人」",
    )
    p.add_argument(
        "--min-iou",
        type=float,
        default=0.2,
        help="帧间与上一帧检测框 IoU 低于该值时尝试 OCR 重锁，默认 0.2",
    )
    p.add_argument(
        "--ocr-min-conf",
        type=float,
        default=0.15,
        help="EasyOCR 单段文字置信度下限，识别困难时可降到 0.08~0.12，默认 0.15",
    )
    p.add_argument(
        "--max-search-frames",
        type=int,
        default=2400,
        help="从片头起最多扫描多少帧以寻找目标号码；0 表示不限制。默认 2400",
    )
    p.add_argument(
        "-w",
        "--window",
        type=str,
        default=None,
        metavar="TIME",
        help="输出片段的中心时间点（秒或 MM:SS / H:MM:SS）；必须与 -d 一起使用",
    )
    p.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        help="输出片段总时长（秒），以 -w 为中心向两侧对称截取；必须与 -w 一起使用",
    )
    args = p.parse_args()

    if (args.window is None) != (args.duration is None):
        p.error("请同时提供 -w 与 -d，或两者都不提供。")

    raw = args.input.strip()
    if not raw:
        p.error("请提供输入路径或 URL")

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
                p.error("-d 时长必须大于 0")
    elif has_clip:
        try:
            clip_only_center = _parse_time_to_seconds(args.window)
        except ValueError as e:
            p.error(str(e))
        clip_only_duration = float(args.duration)
        if clip_only_duration <= 0:
            p.error("-d 时长必须大于 0")
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
            p.error(f"本地文件不存在: {local_path}")
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
                p.error("--max-search-frames 不能为负数")
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
