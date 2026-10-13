# Local Helper / 本地工具

scripts/media_probe.py uses Pillow for images and PyAV (FFmpeg bindings) for videos. It is local-only, does not upload media, rejects existing output directories, and blocks secondary media resources. Install scripts/requirements.txt in an isolated environment only if needed and permitted. No separate system FFmpeg installation is needed for supported PyAV wheels.
工具使用 Pillow 处理图片，PyAV（FFmpeg 绑定）处理视频。只读本地输入，不上传媒体，拒绝已有输出目录并阻止次级媒体资源。仅在需要且获准时在独立环境安装 requirements.txt；受支持的 PyAV wheel 不需要另装系统 FFmpeg。

Python 3.11+ is required for the supported PyAV 19 environment. Example isolated setup:
支持的 PyAV 19 环境需要 Python 3.11+，独立安装示例：

    python -m venv work/media-env
    # Windows:
    work/media-env/Scripts/python.exe -m pip install -r scripts/requirements.txt
    # Linux/macOS:
    work/media-env/bin/python -m pip install -r scripts/requirements.txt

Use that environment's Python for helper commands. Test without bytecode artifacts:
使用该环境的 Python 执行工具。测试时可避免产生字节码文件：

    python -B -m unittest discover -s tests -v

## Examples / 示例

Replace paths with the actual local source and a new task-owned output directory. Crop coordinates are left,top,right,bottom, in pixels after EXIF orientation; right and bottom are exclusive.
替换为实际本地源文件与新的任务输出目录。裁剪参数是方向校正后的像素坐标 left,top,right,bottom，右下边界不包含。

    python scripts/media_probe.py image --input screenshot.png --output work/image-check --crop 120,80,900,500
    python scripts/media_probe.py probe --input clip.mp4
    python scripts/media_probe.py video --input clip.mp4 --output work/video-overview --frames 12
    python scripts/media_probe.py video --input clip.mp4 --output work/video-detail --times 3.0,3.1,3.2,3.3,3.4
    python scripts/media_probe.py video --input clip.mp4 --output work/video-range --start 30 --end 45 --frames 16

Outputs: manifest.json, PNG images, and contact-sheet.jpg for videos. Open the images with the host viewer; filenames and JSON are not a substitute for viewing. The contact sheet is for navigation; use individual frames or crops for small text. Image mode keeps an original-resolution oriented crop when requested and a bounded overview.
输出 manifest.json、PNG 图片，视频另有 contact-sheet.jpg。需要用宿主看图工具实际打开，不能仅读文件名和 JSON 代替。缩略图用于导航，小字查看单帧或裁剪。图片模式在请求裁剪时保留原分辨率、方向校正后的裁剪，并生成有限尺寸概览。

Transparent image crops retain alpha; their overview uses a white background recorded in the manifest. Animated images select frame 0 only and report the source frame count. Use a temporal reader if later animation states matter.
透明图片的裁剪保留 alpha，概览采用清单记录的白色背景。动画图片只选第 0 帧并报告源帧数；需要后续动画状态时另用时序读取工具。

## Limits / 限制

- Default 12 samples, maximum 96. Decode budget: 100,000 frames and 90 seconds, checked between decoded frames. Read timeout is 15 seconds, not a hard process-kill guarantee; hostile or stuck decoders may need a host-level timeout.
  默认 12 个样本，最多 96 个；解码上限 100,000 帧、90 秒，在帧间检查。读取超时 15 秒，不是强制终止保证；异常解码器仍可能需要宿主进程超时。
- Selects the first decoded frame at or after each requested time, using presentation timestamps normalized to the selected stream start (or first timestamp if unknown). Several targets can map to one frame. The manifest records actual PTS, requested times, unresolved targets and coverage.
  每个目标取不早于目标时间的首个解码帧，采用呈现时间戳并归一到所选流起点（未知则首个时间戳）。多个目标可能对应同一帧；清单记录实际 PTS、目标、未满足目标及覆盖。
- Uniform overview uses the start of equally spaced bins, not every frame or necessarily the last frame. No automatic scene detector. Times are seconds on the normalized selected video timeline, not wall-clock time or an audio alignment guarantee.
  均匀概览抽取等分区间起点，不是每帧，也不保证末帧。无自动场景检测；时间是所选视频流归一秒数，不是现实时间，也不保证音频对齐。
- Frames default to max-side 1280, configurable up to 4096. Enlargement cannot create detail. Inputs exceeding 50 million pixels per image or frame are rejected.
  帧默认最长边 1280，可设至 4096；放大不能产生细节。单图或单帧超过 5000 万像素拒绝处理。
- Basic display rotation is applied and recorded. Reflection/shear, non-square pixels, HDR and color-managed interpretation need separate checking. Audio is inventoried but not played, extracted or transcribed.
  基础显示旋转会应用并记录；反射或切变、非方形像素、HDR 和色彩管理需另行核验。仅列音轨信息，不播放、提取或转录声音。
- Unknown duration needs explicit times or end. Missing timestamps are skipped and reported. Decoder errors may leave partial artifacts without a completion manifest. Sources are never modified.
  时长未知需显式 times 或 end。缺时间戳的帧跳过并报告；解码异常可能留下部分文件但无完成清单。源文件不改动。
