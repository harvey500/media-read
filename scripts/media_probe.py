"""Local image crops and bounded, timestamped video samples."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw, ImageOps


MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def local_file(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Input must be a local regular file")
    return path


def source_info(path):
    stat = path.stat()
    return {"name": path.name, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def new_output(value):
    path = Path(value).expanduser().absolute()
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_manifest(output, data):
    with (output / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return data


def bounded_side(value):
    number = int(value)
    if not 128 <= number <= 4096:
        raise argparse.ArgumentTypeError("max-side must be 128..4096")
    return number


def crop_box(value, size):
    parts = tuple(int(item.strip()) for item in value.split(","))
    if len(parts) != 4:
        raise ValueError("Crop needs left,top,right,bottom")
    left, top, right, bottom = parts
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ValueError("Crop is outside the oriented image")
    return parts


def check_pixels(width, height):
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise ValueError("Invalid dimensions or pixel budget exceeded")


def image_extract(args):
    source = local_file(args.input)
    with Image.open(source) as original:
        check_pixels(*original.size)
        orientation = original.getexif().get(274, 1)
        frames = getattr(original, "n_frames", 1)
        profile_present = bool(original.info.get("icc_profile"))
        image = ImageOps.exif_transpose(original)
        transparent = "A" in image.getbands() or "transparency" in image.info
        image = image.convert("RGBA" if transparent else "RGB")
    box = crop_box(args.crop, image.size) if args.crop else None
    output = new_output(args.output)
    preview = image.copy()
    if transparent:
        backdrop = Image.new("RGBA", preview.size, "white")
        preview = Image.alpha_composite(backdrop, preview).convert("RGB")
    preview.thumbnail((args.max_side, args.max_side), Image.Resampling.LANCZOS)
    preview.save(output / "overview.png")
    artifacts = {"overview": "overview.png"}
    if box:
        image.crop(box).save(output / "crop.png")
        artifacts["crop"] = "crop.png"
    return write_manifest(output, {
        "kind": "image", "source": source_info(source),
        "oriented_size": list(image.size), "original_exif_orientation": orientation,
        "crop_box_oriented_pixels": list(box) if box else None,
        "source_frames": frames, "selected_frame": 0,
        "icc_profile_present": profile_present, "color_management_applied": False,
        "overview_alpha_background": "white" if transparent else None,
        "crop_preserves_alpha": transparent if box else None,
        "artifacts": artifacts,
    })


def deny_secondary_resource(url, flags, options):
    raise ValueError("Secondary media resources are not allowed")


def open_video(path):
    import av

    # A file handle avoids treating filenames as remote protocols.
    handle = path.open("rb")
    try:
        container = av.open(handle, mode="r", timeout=(10, 15),
                            io_open=deny_secondary_resource,
                            options={"protocol_whitelist": "file,pipe"})
    except BaseException:
        handle.close()
        raise
    return handle, container


def stream_seconds(stream, field):
    value = getattr(stream, field, None)
    if value is None or stream.time_base is None:
        return None
    return float(value * stream.time_base)


def metadata(container, video_index):
    import av

    videos = list(container.streams.video)
    if not 0 <= video_index < len(videos):
        raise ValueError("Requested video stream does not exist")
    stream = videos[video_index]
    duration = stream_seconds(stream, "duration")
    if duration is None and container.duration is not None:
        duration = float(container.duration / av.time_base)
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        duration = None
    return stream, {
        "duration_s": duration, "duration_source":
            "selected_stream" if stream.duration is not None else "container",
        "selected_video_ordinal": video_index, "selected_stream_index": stream.index,
        "start_time_s": stream_seconds(stream, "start_time"),
        "coded_width": stream.width, "coded_height": stream.height,
        "nominal_fps": float(stream.average_rate) if stream.average_rate else None,
        "sample_aspect_ratio": str(stream.sample_aspect_ratio),
        "audio_streams": [{"index": item.index, "codec": item.codec_context.name,
                           "sample_rate": item.codec_context.sample_rate}
                          for item in container.streams.audio],
        "audio_analyzed": False,
    }


def probe(args):
    source = local_file(args.input)
    handle, container = open_video(source)
    try:
        _, info = metadata(container, args.video_index)
        return {"kind": "video_probe", "source": source_info(source), **info}
    finally:
        container.close()
        handle.close()


def target_times(args, duration):
    if args.times is not None:
        if args.start != 0 or args.end is not None:
            raise ValueError("Use --times or a start/end range, not both")
        targets = sorted(set(float(item.strip()) for item in args.times.split(",")))
    else:
        if not 1 <= args.frames <= 96:
            raise ValueError("frames must be 1..96")
        end = args.end if args.end is not None else duration
        if end is None:
            raise ValueError("Unknown duration; provide --times or --end")
        if not math.isfinite(args.start) or not math.isfinite(end) or not 0 <= args.start < end:
            raise ValueError("Need a finite range with 0 <= start < end")
        if duration is not None and end > duration + 0.001:
            raise ValueError("Range end exceeds reported duration")
        targets = [args.start + (end - args.start) * index / args.frames
                   for index in range(args.frames)]
    if not 1 <= len(targets) <= 96 or any(not math.isfinite(t) or t < 0 for t in targets):
        raise ValueError("Need 1..96 finite, nonnegative times")
    if duration is not None and targets[-1] >= duration:
        raise ValueError("Requested time must precede reported duration")
    return targets


def time_label(seconds):
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes):02d}:{remainder:06.3f}"


def contact_sheet(output, samples):
    columns = min(4, len(samples))
    cell_w, cell_h = 320, 212
    rows = math.ceil(len(samples) / columns)
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), "#e8eaed")
    draw = ImageDraw.Draw(sheet)
    for index, sample in enumerate(samples):
        x, y = (index % columns) * cell_w, (index // columns) * cell_h
        with Image.open(output / sample["file"]) as image:
            image.thumbnail((cell_w - 12, cell_h - 30), Image.Resampling.LANCZOS)
            sheet.paste(image, (x + (cell_w - image.width) // 2, y + 5))
        draw.text((x + 8, y + cell_h - 22),
                  f"#{index + 1:02d}  {time_label(sample['time_s'])}", fill="#17191c")
    sheet.save(output / "contact-sheet.jpg", quality=92)


def video_extract(args):
    if not 1 <= args.max_decoded <= 1_000_000 or not 1 <= args.timeout <= 600:
        raise ValueError("Decode budget must be positive and within documented limits")
    source = local_file(args.input)
    handle, container = open_video(source)
    try:
        stream, info = metadata(container, args.video_index)
        check_pixels(stream.width, stream.height)
        targets = target_times(args, info["duration_s"])
        output = new_output(args.output)
        samples, unresolved = [], list(targets)
        origin = info["start_time_s"]
        origin_source = "stream_start" if origin is not None else "first_decoded_pts"
        decoded = missing_pts = 0
        first_time = last_time = None
        reason = "end_of_stream"
        started = time.monotonic()
        for frame in container.decode(stream):
            if decoded >= args.max_decoded:
                reason = "decoded_frame_budget"
                break
            if time.monotonic() - started >= args.timeout:
                reason = "elapsed_budget"
                break
            decoded += 1
            if frame.pts is None or frame.time_base is None:
                missing_pts += 1
                continue
            absolute = float(frame.pts * frame.time_base)
            if origin is None:
                origin = absolute
            current = absolute - origin
            if last_time is not None and current < last_time - 0.000001:
                raise ValueError("Non-monotonic video timestamps; use a specialized reader")
            if first_time is None:
                first_time = current
            last_time = current
            if not unresolved or current + 0.000001 < unresolved[0]:
                continue
            matched = []
            while unresolved and current + 0.000001 >= unresolved[0]:
                matched.append(unresolved.pop(0))
            check_pixels(frame.width, frame.height)
            image = frame.to_image()
            rotation = getattr(frame, "rotation", 0)
            if rotation:
                image = image.rotate(rotation, expand=True)
            image.thumbnail((args.max_side, args.max_side), Image.Resampling.LANCZOS)
            name = f"frame-{len(samples) + 1:03d}.png"
            image.save(output / name)
            samples.append({"file": name, "time_s": round(current, 9),
                            "pts": frame.pts, "time_base": str(frame.time_base),
                            "absolute_pts_s": absolute, "requested_times_s": matched,
                            "rotation_ccw_degrees": rotation, "output_size": list(image.size)})
            if not unresolved:
                reason = "targets_satisfied"
                break
        if samples:
            contact_sheet(output, samples)
        return write_manifest(output, {
            "kind": "video", "source": source_info(source), **info,
            "timeline_origin_s": origin, "timeline_origin_source": origin_source,
            "requested_times_s": targets, "samples": samples,
            "unresolved_times_s": unresolved,
            "all_requested_samples_extracted": not unresolved,
            "coverage": {"decoded_frames": decoded, "missing_pts_frames": missing_pts,
                         "first_decoded_time_s": first_time, "last_decoded_time_s": last_time,
                         "stop_reason": reason},
            "contact_sheet": "contact-sheet.jpg" if samples else None,
            "limitations": ["Sparse samples are not complete viewing.",
                            "Audio is not analyzed.",
                            "RGB frames are not color or geometry measurements."],
        })
    finally:
        container.close()
        handle.close()


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    image = sub.add_parser("image", help="Oriented image overview and optional native crop")
    image.add_argument("--input", required=True)
    image.add_argument("--output", required=True)
    image.add_argument("--crop")
    image.add_argument("--max-side", type=bounded_side, default=1280)
    image.set_defaults(run=image_extract)
    for command, run in (("probe", probe), ("video", video_extract)):
        item = sub.add_parser(command)
        item.add_argument("--input", required=True)
        item.add_argument("--video-index", type=int, default=0)
        item.set_defaults(run=run)
        if command == "video":
            item.add_argument("--output", required=True)
            item.add_argument("--frames", type=int, default=12)
            item.add_argument("--times")
            item.add_argument("--start", type=float, default=0)
            item.add_argument("--end", type=float)
            item.add_argument("--max-side", type=bounded_side, default=1280)
            item.add_argument("--max-decoded", type=int, default=100000)
            item.add_argument("--timeout", type=float, default=90)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    try:
        result = main()
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except Exception as error:
        print(f"Media extraction failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
