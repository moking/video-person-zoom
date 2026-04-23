# video-person-zoom 性能分析（Profiling）

本文说明如何采集 **CPU**、**GPU** 与 **内存** 相关数据，用于分析 `video_person_zoom.py` 运行时的瓶颈。  
This document describes how to collect **CPU**, **GPU**, and **memory** metrics when profiling `video_person_zoom.py`.

---

## 1. 内置：Python CPU 热点（cProfile）

脚本入口支持环境变量 **`VPZ_CPROFILE`**：若设置为输出文件路径，会在一次完整 `main()` 结束后写入 **cProfile** 二进制统计。

```bash
cd /path/to/video-person-zoom
VPZ_CPROFILE=/tmp/vpz.prof .venv/bin/python video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
```

查看热点（按累计时间排序，打印前 50 条）：

```bash
python -c "import pstats; p=pstats.Stats('/tmp/vpz.prof'); p.sort_stats('cumulative').print_stats(50)"
```

交互式：

```bash
python -m pstats /tmp/vpz.prof
# 在提示符下: sort cumulative | stats 40
```

可选 **火焰图 / 可视化**（需单独安装）：

```bash
pip install snakeviz
snakeviz /tmp/vpz.prof
```

等价方式（不经由 `VPZ_CPROFILE`）：

```bash
python -m cProfile -o /tmp/vpz.prof video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
```

---

## 2. GPU：利用率与显存（NVIDIA）

在脚本运行的同时，另开终端观察 GPU 占用与显存，确认 YOLO / EasyOCR / PyTorch 是否在使用 GPU。

```bash
watch -n0.5 nvidia-smi
```

或持续监控模式：

```bash
nvidia-smi dmon -s pucvmet
```

关注字段：**GPU-Util**、**显存占用**、功耗等。

---

## 3. GPU：CUDA 时间线与内核（Nsight Systems）

需要安装 **NVIDIA Nsight Systems**（`nsys`）。对整次 Python 运行做系统级 + CUDA 采样：

```bash
nsys profile -t cuda,nvtx,osrt -o report ./.venv/bin/python video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
```

生成 `.nsys-rep`，用 **Nsight Systems GUI** 打开，可查看各阶段在 CPU/GPU 上的时间分布、CUDA 内核等。

---

## 4. CPU：系统级采样（Linux perf）

```bash
perf record -g -- ./.venv/bin/python video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
perf report
```

适合看 **内核态 / 用户态**、C 扩展、系统调用等，与 Python `cProfile` 互补。

---

## 5. CPU：采样火焰图（py-spy，无需改代码）

```bash
pip install py-spy
py-spy record -o profile.svg -- ./.venv/bin/python video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
```

用浏览器打开 `profile.svg` 查看调用栈热点。

---

## 6. 内存：进程 RSS 峰值

使用 GNU `time` 的 `-v`（部分系统为 `/usr/bin/time`）：

```bash
/usr/bin/time -v ./.venv/bin/python video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
```

查看输出中的 **Maximum resident set size**（峰值常驻内存，单位 KB）。

---

## 7. 内存：Python 堆随时间（memory_profiler）

```bash
pip install memory_profiler
mprof run ./.venv/bin/python video_person_zoom.py INPUT.mp4 -n 10 -o /tmp/out.mp4
mprof plot
```

适合观察运行过程中 **Python 堆** 是否持续增长。

---

## 8. PyTorch / CUDA 显存摘要（调试时临时使用）

在 Python 交互或临时加几行（例如在若干帧推理后）：

```python
import torch
print(torch.cuda.memory_summary())
```

用于确认 **显存分配/缓存** 是否与预期一致。

---

## 9. PyTorch Profiler（算子级，需改代码）

若要对 **`model.predict`** 等热点做 **CPU + CUDA** 算子级分析，可在循环外包一层 `torch.profiler`，启用 `ProfilerActivity.CPU` 与 `ProfilerActivity.CUDA`，并导出 **Chrome trace**（JSON），在 Chrome 地址栏打开 `chrome://tracing` 加载该文件。  
仓库默认未开启；需要时可单独加「仅 profile 前 N 帧」的开关，避免整段视频生成过大 trace。

---

## 10. 与本项目相关的执行路径简述

| 阶段 | 典型资源 |
|------|-----------|
| 解码、缩放、`VideoWriter` | 多为 **CPU**（OpenCV） |
| YOLO 检测、`model.predict` | **GPU**（若 CUDA 可用且未 `--device cpu`） |
| EasyOCR | **GPU**（`gpu=True` 且 CUDA 可用时） |
| ffmpeg 截取/转码 | 默认先试 **NVENC**（NVIDIA），失败再用 **`libx264` + `veryfast`**；可用环境变量调节 |

结合 **nvidia-smi** 与 **`VPZ_CPROFILE`**，通常足以区分「GPU 未用上」与「Python 侧热点」。

---

## 11. ffmpeg 临时 H.264（OpenCV 代理）加速

当 OpenCV 读不了首帧时，脚本会用 ffmpeg 生成临时 H.264。为加快整片/截取转码，实现上会：

1. **优先 `h264_nvenc`**（需 NVIDIA 驱动与带 NVENC 的 ffmpeg）；成功时 stderr 会打印 `ffmpeg video encoder: h264_nvenc`。
2. 失败则回退 **`libx264`**，默认 **`-preset veryfast -crf 24`**（比原先的 `fast + crf 23` 更快，画质略降，对临时代理通常可接受）。

环境变量（可选）：

| 变量 | 含义 |
|------|------|
| `VPZ_FFMPEG_NVENC=0` | 禁用 NVENC，只用 libx264 |
| `VPZ_FFMPEG_X264_PRESET` | libx264 预设，默认 `veryfast`；可试 `ultrafast` 更快、文件更大 |
| `VPZ_FFMPEG_X264_CRF` | libx264 CRF，默认 `24`；数值越大越快、画质越差 |

截取路径还把 **`-ss` 放在 `-i` 之前**，有利于长文件上的快速定位（关键帧附近，边界可能略不精确，对临时代理一般够用）。
