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

Profiling / 性能分析: 见同目录 profile.md；快速 CPU 采样可设环境变量 VPZ_CPROFILE=文件路径（cProfile）。
ffmpeg 临时 H.264 加速: VPZ_FFMPEG_NVENC=0 禁用 NVENC；VPZ_FFMPEG_X264_PRESET=veryfast；VPZ_FFMPEG_X264_CRF=24。
"""

from __future__ import annotations

import argparse
import contextlib
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path


def _configure_quiet_videoio() -> None:
    """Lower FFmpeg/libav log noise (e.g. AV1 HW decode unavailable). / 降低 OpenCV FFmpeg 后端的 stderr 提示。"""
    # Matches libavutil AV_LOG_*; -8 = quiet. Parsed when OpenCV loads libav.
    os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")


_configure_quiet_videoio()


@contextlib.contextmanager
def _suppress_stderr_fd() -> Iterator[None]:
    """Redirect OS stderr to /dev/null (C libraries bypass sys.stderr). / 屏蔽 fd 2，避免 libav 直接写终端。"""
    stderr_fd = 2
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(stderr_fd)
    try:
        os.dup2(devnull, stderr_fd)
        yield
    finally:
        os.dup2(saved, stderr_fd)
        os.close(saved)
        os.close(devnull)


def _b(cn: str, en: str) -> str:
    """User-facing bilingual text: Chinese / English."""

    return f"{cn} / {en}"


def _print_dl_device_banner(yolo_device: str, *, ocr_on_gpu: bool) -> None:
    """Print whether YOLO / EasyOCR run on CPU or GPU. / 标明人物检测与 OCR 在 CPU 还是 GPU 上执行。"""
    y_on_gpu = yolo_device.strip().lower() != "cpu"
    y_cn, y_en = ("GPU", "GPU") if y_on_gpu else ("CPU", "CPU")
    o_cn, o_en = ("GPU", "GPU") if ocr_on_gpu else ("CPU", "CPU")
    suffix_cn = ""
    suffix_en = ""
    if y_on_gpu:
        try:
            import torch

            if torch.cuda.is_available():
                idx = 0
                ds = yolo_device.strip()
                dsl = ds.lower()
                if dsl.startswith("cuda:"):
                    part = ds.split(":", 1)[1]
                    idx = int(part, 10) if part.isdigit() else torch.cuda.current_device()
                elif ds.isdigit():
                    idx = int(ds, 10)
                suffix_cn = f"，GPU: {torch.cuda.get_device_name(idx)}"
                suffix_en = f", GPU: {torch.cuda.get_device_name(idx)}"
        except Exception:
            pass
    print(
        _b(
            f"执行设备 — YOLO（人物检测）: {y_cn}（device={yolo_device}{suffix_cn}）；"
            f"EasyOCR（球衣号码）: {o_cn}",
            f"Execution — YOLO (person detect): {y_en} (device={yolo_device}{suffix_en}); "
            f"EasyOCR (jersey digits): {o_en}",
        ),
        file=sys.stderr,
    )


def _normalize_yolo_device(user_spec: str | None, *, cuda_ok: bool) -> str:
    """
    Map --device / default to strings Ultralytics + PyTorch accept.
    Some versions reject bare '0'; use 'cuda:0'.
    """
    if not user_spec or not str(user_spec).strip():
        return "cuda:0" if cuda_ok else "cpu"
    s = str(user_spec).strip()
    sl = s.lower()
    if sl == "cpu":
        return "cpu"
    if sl.startswith("cuda"):
        return s if ":" in s else "cuda:0"
    if s.isdigit() and cuda_ok:
        return f"cuda:{int(s, 10)}"
    if s.isdigit() and not cuda_ok:
        return "cpu"
    return s


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


_iou = _iou_xyxy


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


def _ffmpeg_h264_encoder_variants() -> list[tuple[str, list[str]]]:
    """
    Ordered (label, ffmpeg video encode args) for temp H.264 proxies.
    临时 H.264：优先 NVENC（快），否则 libx264（preset 默认 veryfast）。
    Env: VPZ_FFMPEG_NVENC=0 禁用 NVENC；VPZ_FFMPEG_X264_PRESET / VPZ_FFMPEG_X264_CRF 可调 libx264。
    """
    out: list[tuple[str, list[str]]] = []
    nv = (os.environ.get("VPZ_FFMPEG_NVENC") or "1").strip().lower()
    if nv not in ("0", "false", "no", ""):
        out.append(
            (
                "h264_nvenc",
                [
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p4",
                    "-rc",
                    "vbr",
                    "-cq",
                    "26",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                ],
            )
        )
    x264_preset = (os.environ.get("VPZ_FFMPEG_X264_PRESET") or "veryfast").strip() or "veryfast"
    x264_crf = (os.environ.get("VPZ_FFMPEG_X264_CRF") or "24").strip() or "24"
    out.append(
        (
            f"libx264(preset={x264_preset},crf={x264_crf})",
            [
                "-c:v",
                "libx264",
                "-preset",
                x264_preset,
                "-crf",
                x264_crf,
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ],
        )
    )
    return out


def _ffmpeg_run_h264_proxy(
    input_path: str,
    output_path: str,
    *,
    seek_before_input: str | None,
    duration_after_input: str | None,
    fail_cn: str,
    fail_en: str,
) -> None:
    """
    Encode to H.264 MP4 for OpenCV; tries NVENC then libx264.
    seek_before_input: put -ss before -i for faster keyframe seeks on long files.
    """
    ff = _ffmpeg_bin()
    if not ff:
        raise RuntimeError(_b("未找到 ffmpeg", "ffmpeg not found in PATH"))

    last_err = ("", "")
    for label, venc in _ffmpeg_h264_encoder_variants():
        head: list[str] = [
            ff,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
        ]
        if seek_before_input is not None:
            head.extend(["-ss", seek_before_input])
        head.extend(["-i", input_path])
        if duration_after_input is not None:
            head.extend(["-t", duration_after_input])
        base = [*head, *venc]
        cmd_with_audio = [*base, "-c:a", "aac", "-b:a", "128k", output_path]
        r = subprocess.run(cmd_with_audio, capture_output=True, text=True)
        if r.returncode == 0:
            print(
                _b(f"ffmpeg 视频编码: {label}", f"ffmpeg video encoder: {label}"),
                file=sys.stderr,
            )
            return
        cmd_an = [*base, "-an", output_path]
        r2 = subprocess.run(cmd_an, capture_output=True, text=True)
        if r2.returncode == 0:
            print(
                _b(
                    f"ffmpeg 视频编码: {label}（无音轨）",
                    f"ffmpeg video encoder: {label} (no audio)",
                ),
                file=sys.stderr,
            )
            return
        last_err = (r.stderr or r.stdout or "", r2.stderr or r2.stdout or "")

    raise SystemExit(
        _b(
            f"{fail_cn}\n{last_err[0]}\n---\n{last_err[1]}",
            f"{fail_en}\n{last_err[0]}\n---\n{last_err[1]}",
        )
    )


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
    _ffmpeg_run_h264_proxy(
        input_path,
        output_path,
        seek_before_input=str(start_sec),
        duration_after_input=str(duration_sec),
        fail_cn="ffmpeg 截取失败（已尝试 NVENC / libx264，含无音轨重试）。stderr:",
        fail_en="ffmpeg trim failed (tried NVENC / libx264, including no-audio). stderr:",
    )


def _ffmpeg_transcode_full_to_h264(input_path: str, output_path: str) -> None:
    """
    Full remux/transcode to H.264 MP4 for OpenCV-friendly decode.
    整片转 H.264 MP4，便于 OpenCV 读帧。
    """
    _ffmpeg_run_h264_proxy(
        input_path,
        output_path,
        seek_before_input=None,
        duration_after_input=None,
        fail_cn="ffmpeg 整片转码失败（已尝试 NVENC / libx264，含无音轨重试）。stderr:",
        fail_en="ffmpeg full transcode failed (tried NVENC / libx264, including no-audio). stderr:",
    )


def _try_reset_capture_first_frame(cap: object) -> bool:
    """Read one frame and seek back to 0; False if decode failed. / 读首帧并回绕到 0，失败返回 False。"""
    import cv2

    ok, frame = cap.read()
    if not ok or frame is None:
        return False
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0.0)
    return True


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

    print(
        _b(
            "执行设备 — 仅截取模式：解码/重编码在 CPU 上（ffmpeg 或 OpenCV），未使用 GPU 神经网络。",
            "Execution — trim-only: decode/re-encode on CPU (ffmpeg or OpenCV); no GPU neural nets.",
        ),
        file=sys.stderr,
    )

    with _suppress_stderr_fd():
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
    with _suppress_stderr_fd():
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
    first_read = True
    try:
        while frames_out < clip_frames_total:
            if first_read:
                with _suppress_stderr_fd():
                    ok, frame = cap.read()
                first_read = False
            else:
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
    """Strict full-number OCR match. / 严格整号匹配，避免 9 误匹配 90。"""
    segs: list[str] = []
    for raw in texts:
        segs.append("".join(c for c in raw if c.isdigit()))
    combined = "".join(segs)
    # Strict mode: only accept full concatenated digits == target.
    # Example: OCR ["9", "0"] => "90", will NOT match target "9".
    return combined == target


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


def _center_crop_with_zoom_limit(
    cx: float,
    cy: float,
    person_w: float,
    person_h: float,
    frame_w: int,
    frame_h: int,
    padding: float,
    max_zoom: float,
) -> tuple[int, int, int, int]:
    """
    Center crop around target while capping zoom-in.
    以目标为中心裁剪，并限制最大放大倍数（避免超过 max_zoom）。
    """
    max_zoom = max(1.0, float(max_zoom))
    bw = max(1.0, person_w * (1.0 + max(0.0, padding)))
    bh = max(1.0, person_h * (1.0 + max(0.0, padding)))
    # Keep crop at least this large so output zoom never exceeds max_zoom.
    bw = max(bw, frame_w / max_zoom)
    bh = max(bh, frame_h / max_zoom)
    return _expand_and_clip_box(
        cx - bw / 2.0,
        cy - bh / 2.0,
        cx + bw / 2.0,
        cy + bh / 2.0,
        frame_w,
        frame_h,
        0.0,
    )


class _AsyncSegmentWriter:
    """Background MP4 writer so detection loop can continue."""

    def __init__(self, path: str, fourcc: int, fps: float, out_size: tuple[int, int]) -> None:
        self.path = path
        self._fourcc = fourcc
        self._fps = fps
        self._out_size = out_size
        self._q: queue.Queue[object] = queue.Queue(maxsize=64)
        self._ready = threading.Event()
        self._ok = False
        self._t = threading.Thread(target=self._worker, daemon=True)
        self._t.start()
        self._ready.wait(timeout=5.0)

    def _worker(self) -> None:
        import cv2

        writer = cv2.VideoWriter(self.path, self._fourcc, self._fps, self._out_size)
        self._ok = bool(writer.isOpened())
        self._ready.set()
        if not self._ok:
            return
        try:
            while True:
                item = self._q.get()
                if item is None:
                    break
                writer.write(item)  # item is ndarray frame
        finally:
            writer.release()

    @property
    def ok(self) -> bool:
        return self._ok

    def write(self, frame) -> bool:
        if not self._ok:
            return False
        # copy() prevents aliasing with later frame buffer reuse
        self._q.put(frame.copy())
        return True

    def close(self) -> None:
        if not self._ok:
            return
        self._q.put(None)
        self._t.join(timeout=10.0)


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
    segment_duration_sec: float,
    max_segments: int,
    max_parallel_writers: int,
    pre_roll_sec: float,
) -> list[str]:
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

    try:
        import torch

        cuda_ok = torch.cuda.is_available()
    except Exception:
        cuda_ok = False

    # EasyOCR: GPU when CUDA is available unless user forces --device cpu.
    if device and device.strip().lower() == "cpu":
        use_cuda = False
    else:
        use_cuda = cuda_ok

    if not device:
        print(
            _b(
                "未指定 --device："
                + ("已检测到 CUDA，YOLO 与 EasyOCR 将使用 GPU。" if cuda_ok else "未检测到可用 CUDA，YOLO 与 EasyOCR 使用 CPU。"),
                "No --device: "
                + ("CUDA detected; YOLO and EasyOCR use GPU." if cuda_ok else "CUDA not available; YOLO and EasyOCR use CPU."),
            ),
            file=sys.stderr,
        )

    ocr_reader = easyocr.Reader(["en"], gpu=use_cuda)

    decode_tmp: str | None = None
    clip_via_ffmpeg_prefetch = False
    clip_print_start = 0.0
    clip_print_end = 0.0

    with _suppress_stderr_fd():
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise SystemExit(_b(f"无法打开视频: {input_path}", f"Cannot open video: {input_path}"))

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    with _suppress_stderr_fd():
        first_ok = _try_reset_capture_first_frame(cap)

    if not first_ok:
        cap.release()
        ff = _ffmpeg_bin()
        if not ff:
            raise SystemExit(
                _b(
                    "无法从视频解码出第一帧（常见于 AV1 与 OpenCV）。未找到 ffmpeg，无法自动转码。\n"
                    "请安装 ffmpeg 后重试，或手动转 H.264，例如：\n"
                    f"  ffmpeg -i \"{input_path}\" -c:v libx264 -crf 23 -c:a copy \"{input_path}.h264.mp4\"",
                    "Cannot decode the first frame (often AV1 + OpenCV). ffmpeg not found for auto-transcode.\n"
                    "Install ffmpeg and retry, or transcode manually, e.g.:\n"
                    f"  ffmpeg -i \"{input_path}\" -c:v libx264 -crf 23 -c:a copy \"{input_path}.h264.mp4\"",
                )
            )
        fd, decode_tmp = tempfile.mkstemp(suffix=".mp4", prefix="vpz_ocvproxy_")
        os.close(fd)
        try:
            want_clip_prefetch = clip_center_sec is not None and clip_duration_sec is not None
            if want_clip_prefetch:
                ss, dur = _clip_segment_start_and_duration(
                    fps, nframes, float(clip_center_sec), float(clip_duration_sec)
                )
                clip_print_start, clip_print_end = ss, ss + dur
                print(
                    _b(
                        "OpenCV 无法解码首帧，已用 ffmpeg 截取目标片段为临时 H.264 再处理。",
                        "OpenCV could not decode the first frame; using ffmpeg clip → temp H.264.",
                    ),
                    file=sys.stderr,
                )
                _ffmpeg_extract_segment(input_path, decode_tmp, ss, dur)
                clip_via_ffmpeg_prefetch = True
            else:
                print(
                    _b(
                        "OpenCV 无法解码首帧，已用 ffmpeg 将整片转码为临时 H.264 再处理（可能较慢）。",
                        "OpenCV could not decode the first frame; full ffmpeg transcode to temp H.264 (may be slow).",
                    ),
                    file=sys.stderr,
                )
                _ffmpeg_transcode_full_to_h264(input_path, decode_tmp)

            with _suppress_stderr_fd():
                cap = cv2.VideoCapture(decode_tmp)
            if not cap.isOpened():
                raise SystemExit(
                    _b(
                        "ffmpeg 输出后仍无法用 OpenCV 打开临时文件。",
                        "ffmpeg produced output OpenCV still cannot open.",
                    )
                )
            fps = float(cap.get(cv2.CAP_PROP_FPS) or fps)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            with _suppress_stderr_fd():
                second_ok = _try_reset_capture_first_frame(cap)
            if not second_ok:
                cap.release()
                raise SystemExit(
                    _b(
                        "ffmpeg 转码/截取后 OpenCV 仍读不到首帧，请检查片源或 ffmpeg 日志。",
                        "Still cannot read the first frame after ffmpeg; check source or ffmpeg logs.",
                    )
                )
        except SystemExit:
            if decode_tmp:
                try:
                    os.remove(decode_tmp)
                except OSError:
                    pass
            raise
        except Exception as e:
            if decode_tmp:
                try:
                    os.remove(decode_tmp)
                except OSError:
                    pass
            raise SystemExit(_b(f"ffmpeg 预处理失败: {e}", f"ffmpeg preprocess failed: {e}")) from e

    clip_frames_total: int | None = None
    if clip_center_sec is not None and clip_duration_sec is not None:
        if clip_via_ffmpeg_prefetch:
            clip_frames_total = (
                nframes if nframes > 0 else max(1, int(float(clip_duration_sec) * max(fps, 1e-3)))
            )
            start_sec_print, end_sec_print = clip_print_start, clip_print_end
            print(
                _b(
                    f"输出片段: 约 {start_sec_print:.3f}s – {end_sec_print:.3f}s，"
                    f"约 {clip_frames_total} 帧（ffmpeg 预截取）。",
                    f"Output clip: ~{start_sec_print:.3f}s – {end_sec_print:.3f}s, "
                    f"~{clip_frames_total} frames (ffmpeg pre-cut).",
                ),
                file=sys.stderr,
            )
        else:
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
        if decode_tmp:
            try:
                os.remove(decode_tmp)
            except OSError:
                pass
        raise SystemExit(
            _b(
                "请同时提供 -w 与 -d，或两者都不提供以处理整段视频。",
                "Provide both -w and -d together, or neither for full video.",
            )
        )

    out_w, out_h = w - (w % 2), h - (h % 2)
    segment_dir = os.path.dirname(output_path) or os.getcwd()
    seg_fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    seg_duration = max(0.1, float(segment_duration_sec))
    seg_frames_total = max(1, int(round(seg_duration * fps)))
    pre_roll_frames = max(0, int(round(max(0.0, float(pre_roll_sec)) * fps)))
    active_segments: list[dict[str, object]] = []
    saved_segments: list[str] = []
    warned_parallel_limit = False
    next_segment_detect_sec = 0.0
    recent_out_frames: deque = deque(maxlen=max(1, pre_roll_frames + 1))

    model = YOLO(model_name)
    infer_device = _normalize_yolo_device(device, cuda_ok=cuda_ok)
    if infer_device.lower() != "cpu":
        model.to(infer_device)
    _print_dl_device_banner(infer_device, ocr_on_gpu=use_cuda)
    print(
        _b(
            "执行设备 — 裁切/缩放在 CPU 上（每帧 BGR 处理）；仅输出识别片段。",
            "Execution — crop/resize on CPU (per-frame BGR processing); only detected segments are written.",
        ),
        file=sys.stderr,
    )

    prev_smooth: tuple[float, float, float, float] | None = None
    last_box: tuple[float, float, float, float] | None = None
    locked_ref_xyxy: tuple[float, float, float, float] | None = None
    warned_relock = False
    warned_jersey_relock = False
    lock_announced = False
    frame_i = 0
    progress_total = clip_frames_total if clip_frames_total is not None else nframes

    def _write_full_and_maybe_abort() -> None:
        """Before first lock: keep scanning only; no output. / 首次锁定前只扫描，不写输出。"""
        if frame_i == 1:
            print(
                _b(
                    "正在扫描球衣号码：仅在识别到目标后开始写片段。",
                    "Scanning jersey number: segment output starts after a successful match.",
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
            if clip_frames_total is not None and frame_i >= clip_frames_total:
                break
            ok, frame = cap.read()
            if not ok:
                break
            frame_i += 1
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h))

            box: tuple[float, float, float, float] | None = None
            detected_this_frame = False
            results = model.predict(
                frame,
                classes=[0],
                verbose=False,
                device=infer_device,
            )
            persons = _list_person_boxes(results[0])

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
                            detected_this_frame = True
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
                    detected_this_frame = True
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
            ix1, iy1, ix2, iy2 = _center_crop_with_zoom_limit(
                sx,
                sy,
                hx2 - hx1,
                hy2 - hy1,
                w,
                h,
                padding,
                1.1,
            )

            crop = frame[iy1:iy2, ix1:ix2]
            out = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            recent_out_frames.append(out)
            still_active: list[dict[str, object]] = []
            for seg in active_segments:
                sw = seg["writer"]
                rem = int(seg["remaining"])
                pth = str(seg["path"])
                if isinstance(sw, _AsyncSegmentWriter):
                    if bool(seg.get("skip_once", False)):
                        seg["skip_once"] = False
                    else:
                        sw.write(out)
                        rem -= 1
                    if rem <= 0:
                        sw.close()
                        saved_segments.append(pth)
                        print(
                            _b(
                                f"片段已保存: {pth}",
                                f"Segment saved: {pth}",
                            ),
                            file=sys.stderr,
                        )
                    else:
                        seg["remaining"] = rem
                        still_active.append(seg)
            active_segments = still_active
            if detected_this_frame:
                detect_t = max(0.0, (frame_i - 1) / max(fps, 1e-6))
                can_start = True
                if detect_t < next_segment_detect_sec:
                    # New segment can only be triggered at/after previous window end.
                    # 允许的最大重叠仅来自 pre-roll。
                    can_start = False
                if max_segments > 0 and len(saved_segments) + len(active_segments) >= max_segments:
                    can_start = False
                if not can_start:
                    pass
                elif len(active_segments) >= max_parallel_writers:
                    if not warned_parallel_limit:
                        print(
                            _b(
                                f"并行写入已达上限({max_parallel_writers})，暂不启动新片段。",
                                f"Parallel writers at limit ({max_parallel_writers}); skipping new segment start.",
                            ),
                            file=sys.stderr,
                        )
                        warned_parallel_limit = True
                else:
                    warned_parallel_limit = False
                    start_sec = max(0.0, detect_t - max(0.0, float(pre_roll_sec)))
                    end_sec = start_sec + seg_duration
                    segment_name = f"{jersey}-{start_sec:.3f}-{end_sec:.3f}.mp4"
                    segment_path = os.path.join(segment_dir, segment_name)
                    sw = _AsyncSegmentWriter(segment_path, seg_fourcc, fps, (out_w, out_h))
                    if sw.ok:
                        prefill = list(recent_out_frames)
                        for f in prefill:
                            sw.write(f)
                        rem = max(0, int(seg_frames_total) - len(prefill))
                        if rem <= 0:
                            sw.close()
                            saved_segments.append(segment_path)
                            print(
                                _b(
                                    f"片段已保存: {segment_path}",
                                    f"Segment saved: {segment_path}",
                                ),
                                file=sys.stderr,
                            )
                            next_segment_detect_sec = end_sec
                        else:
                            active_segments.append(
                                {
                                    "writer": sw,
                                    "remaining": rem,
                                    "path": segment_path,
                                    "skip_once": True,
                                }
                            )
                            print(
                                _b(
                                    f"新片段: {segment_name}",
                                    f"New segment: {segment_name}",
                                ),
                                file=sys.stderr,
                            )
                            next_segment_detect_sec = end_sec
                    else:
                        print(
                            _b(
                                f"警告: 无法创建片段文件 {segment_name}",
                                f"Warning: cannot create segment file {segment_name}",
                            ),
                            file=sys.stderr,
                        )
            if max_segments > 0 and len(saved_segments) >= max_segments:
                break

            if clip_frames_total is not None:
                if clip_frames_total and frame_i % max(1, clip_frames_total // 20) == 0:
                    pct = 100.0 * frame_i / clip_frames_total
                    print(
                        f"\r{_b('进度', 'Progress')}: {frame_i}/{clip_frames_total} ({pct:.0f}%)",
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
        for seg in active_segments:
            sw = seg["writer"]
            pth = str(seg["path"])
            if isinstance(sw, _AsyncSegmentWriter):
                sw.close()
                saved_segments.append(pth)
                print(
                    _b(
                        f"片段已保存: {pth}",
                        f"Segment saved: {pth}",
                    ),
                    file=sys.stderr,
                )
        if decode_tmp:
            try:
                os.remove(decode_tmp)
            except OSError:
                pass

    if last_box is None:
        raise SystemExit(
            _b(
                f"整段视频未成功锁定球衣号码 {jersey}（需在某一帧同时检出人物并 OCR 到该号码）。",
                f"Could not lock jersey {jersey}: need at least one frame with a person and readable number.",
            )
        )
    if not saved_segments:
        raise SystemExit(
            _b(
                "已识别到目标球衣，但未成功写出片段文件。",
                "Target jersey was detected, but no segment file was written.",
            )
        )
    return saved_segments


def _audio_rms_windows(input_path: str, *, sample_rate: int = 16000, win_sec: float = 0.5) -> list[float]:
    """Extract RMS energy windows from audio via ffmpeg pipe."""
    ff = _ffmpeg_bin()
    if not ff:
        raise RuntimeError(_b("未找到 ffmpeg", "ffmpeg not found in PATH"))
    cmd = [
        ff,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.stdout is not None
    import numpy as np

    win_samples = max(1, int(round(sample_rate * max(0.05, float(win_sec)))))
    chunk_bytes = win_samples * 2
    vals: list[float] = []
    while True:
        buf = p.stdout.read(chunk_bytes)
        if not buf:
            break
        arr = np.frombuffer(buf, dtype=np.int16).astype(np.float32)
        if arr.size == 0:
            continue
        rms = float(np.sqrt(np.mean(arr * arr)))
        vals.append(rms)
    p.wait(timeout=30)
    return vals


def _detect_audio_peaks(rms: list[float], *, win_sec: float, min_gap_sec: float) -> list[float]:
    """Simple robust peak picking on RMS envelope."""
    if not rms:
        return []
    import numpy as np

    x = np.asarray(rms, dtype=np.float32)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) + 1e-6
    thr = med + 6.0 * mad
    min_gap_n = max(1, int(round(min_gap_sec / max(win_sec, 1e-6))))
    peaks: list[int] = []
    i = 0
    n = int(x.shape[0])
    while i < n:
        if x[i] >= thr:
            j = min(n, i + min_gap_n)
            k = i + int(np.argmax(x[i:j]))
            peaks.append(k)
            i = j
        else:
            i += 1
    return [float(k) * win_sec for k in peaks]


def process_goal_events(
    input_path: str,
    output_dir: str,
    *,
    duration_sec: float,
    pre_roll_sec: float,
    max_clips: int,
) -> list[str]:
    """
    Lightweight goal spotting by audio excitement peaks.
    轻量进球捕获：基于音频能量峰值生成候选片段。
    """
    os.makedirs(output_dir, exist_ok=True)
    win_sec = 0.5
    rms = _audio_rms_windows(input_path, win_sec=win_sec)
    peaks = _detect_audio_peaks(
        rms,
        win_sec=win_sec,
        min_gap_sec=max(4.0, float(duration_sec) - max(0.0, float(pre_roll_sec))),
    )
    if not peaks:
        return []
    out_paths: list[str] = []
    for t in peaks:
        start_sec = max(0.0, t - max(0.0, float(pre_roll_sec)))
        end_sec = start_sec + float(duration_sec)
        name = f"goal-{start_sec:.3f}-{end_sec:.3f}.mp4"
        out_path = os.path.join(output_dir, name)
        _ffmpeg_extract_segment(input_path, out_path, start_sec, float(duration_sec))
        out_paths.append(out_path)
        if max_clips > 0 and len(out_paths) >= max_clips:
            break
    return out_paths


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
        "--goal-detect",
        action="store_true",
        help=_b(
            "进球捕获模式：按音频峰值自动切疑似进球片段",
            "Goal spotting mode: auto-cut likely goal clips by audio peaks",
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
            "YOLO / EasyOCR：cpu、cuda:0、1（=cuda:1）等；留空则自动检测 CUDA，有则用 GPU",
            "YOLO / EasyOCR: cpu, cuda:0, digit maps to cuda:N; empty auto-detects CUDA and uses GPU if present",
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
            "无 -n 时：与 -w 同用做截取时长；有 -n 时：每个识别片段时长（默认 10 秒）",
            "Without -n: use with -w as trim length; with -n: per-detected segment length (default 10s)",
        ),
    )
    p.add_argument(
        "-c",
        "--max-clips",
        type=int,
        default=0,
        help=_b(
            "仅 -n 模式：最多生成多少个片段后退出；0 表示处理到文件末尾",
            "Only with -n: stop after this many clips; 0 means run to end of input",
        ),
    )
    p.add_argument(
        "--max-parallel-writers",
        type=int,
        default=3,
        help=_b(
            "仅 -n 模式：最多并行片段写入数，默认 3",
            "Only with -n: maximum concurrent segment writers, default 3",
        ),
    )
    p.add_argument(
        "--pre-roll",
        type=float,
        default=2.0,
        help=_b(
            "仅 -n 模式：每个片段在检测时刻前保留多少秒，默认 2 秒",
            "Only with -n: seconds kept before detection time in each segment, default 2s",
        ),
    )
    args = p.parse_args()

    raw = args.input.strip()
    if not raw:
        p.error(_b("请提供输入路径或 URL", "Provide input path or URL"))

    has_jersey = bool(args.jersey_number and str(args.jersey_number).strip())
    has_goal_detect = bool(args.goal_detect)
    has_clip = args.window is not None

    if has_goal_detect and has_jersey:
        p.error(_b("--goal-detect 与 -n 不能同时使用", "--goal-detect cannot be used with -n"))

    if has_jersey:
        if args.window is not None and args.duration is None:
            p.error(
                _b(
                    "-n 模式下，提供 -w 时必须同时提供 -d。",
                    "With -n, -w requires -d.",
                )
            )
        try:
            jersey_norm = _normalize_jersey_target(str(args.jersey_number))
        except ValueError as e:
            p.error(str(e))
        segment_duration_sec = 10.0
        if args.duration is not None:
            segment_duration_sec = float(args.duration)
            if segment_duration_sec <= 0:
                p.error(_b("-d 时长必须大于 0", "-d duration must be positive"))
        if args.max_clips < 0:
            p.error(_b("-c 不能为负数", "-c must be non-negative"))
        if args.max_parallel_writers <= 0:
            p.error(_b("--max-parallel-writers 必须大于 0", "--max-parallel-writers must be > 0"))
        if args.pre_roll < 0:
            p.error(_b("--pre-roll 不能为负数", "--pre-roll must be non-negative"))
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
    elif has_goal_detect:
        segment_duration_sec = 10.0
        if args.duration is not None:
            segment_duration_sec = float(args.duration)
            if segment_duration_sec <= 0:
                p.error(_b("-d 时长必须大于 0", "-d duration must be positive"))
        if args.max_clips < 0:
            p.error(_b("-c 不能为负数", "-c must be non-negative"))
        if args.pre_roll < 0:
            p.error(_b("--pre-roll 不能为负数", "--pre-roll must be non-negative"))
        if has_clip:
            p.error(_b("--goal-detect 不使用 -w", "--goal-detect does not use -w"))
    elif has_clip:
        try:
            clip_only_center = _parse_time_to_seconds(args.window)
        except ValueError as e:
            p.error(str(e))
        clip_only_duration = float(args.duration)
        if clip_only_duration <= 0:
            p.error(_b("-d 时长必须大于 0", "-d duration must be positive"))
    elif args.duration is not None:
        p.error(
            _b(
                "无 -n 时，-d 需与 -w 同时使用。",
                "Without -n, -d must be used with -w.",
            )
        )
    else:
        out_opt = args.output.strip() if args.output else None
        final_path = _download_or_copy_only(raw, out_opt)
        print(final_path)
        return

    clip_trim = (not has_jersey) and (not has_goal_detect) and has_clip

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
        elif has_goal_detect:
            out_path = str(Path.cwd() / f"goals_{int(time.time())}.mp4")
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
        elif has_goal_detect:
            src = Path(local_path)
            out_path = str(src.with_name(f"{src.stem}_goals.mp4"))
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
        elif has_goal_detect:
            segment_paths = process_goal_events(
                local_path,
                os.path.dirname(out_path) or os.getcwd(),
                duration_sec=segment_duration_sec,
                pre_roll_sec=args.pre_roll,
                max_clips=args.max_clips,
            )
        else:
            msearch = args.max_search_frames
            if msearch < 0:
                p.error(_b("--max-search-frames 不能为负数", "--max-search-frames must be non-negative"))
            segment_paths = process_video(
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
                segment_duration_sec=segment_duration_sec,
                max_segments=args.max_clips,
                max_parallel_writers=args.max_parallel_writers,
                pre_roll_sec=args.pre_roll,
            )
    finally:
        if tmpdir_to_remove and os.path.isdir(tmpdir_to_remove):
            shutil.rmtree(tmpdir_to_remove, ignore_errors=True)

    if has_jersey or has_goal_detect:
        for pth in segment_paths:
            print(pth)
    else:
        print(out_path)


if __name__ == "__main__":
    _vpz_cprof = os.environ.get("VPZ_CPROFILE", "").strip()
    if _vpz_cprof:
        import cProfile

        pr = cProfile.Profile()
        pr.enable()
        try:
            main()
        finally:
            pr.disable()
            pr.dump_stats(_vpz_cprof)
            print(
                _b(
                    f"cProfile 统计已写入: {_vpz_cprof}（可用 pstats 或 snakeviz 查看）",
                    f"cProfile stats written: {_vpz_cprof} (inspect with pstats or snakeviz)",
                ),
                file=sys.stderr,
            )
    else:
        main()
