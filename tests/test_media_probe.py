from fractions import Fraction
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

import av
from PIL import Image, ImageDraw, ImageOps


spec = importlib.util.spec_from_file_location(
    "media_probe", Path(__file__).resolve().parents[1] / "scripts" / "media_probe.py"
)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def make_video(path, times=(0, 0.2, 0.5, 1.0), audio=False):
    with av.open(str(path), "w") as container:
        stream = container.add_stream("ffv1", rate=10)
        stream.width, stream.height = 160, 100
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        stream.codec_context.time_base = Fraction(1, 1000)
        sound = container.add_stream("pcm_s16le", rate=8000) if audio else None
        for index, seconds in enumerate(times):
            image = Image.new("RGB", (160, 100), (index * 40, 80, 120))
            ImageDraw.Draw(image).text((10, 10), f"frame {index}", fill="white")
            frame = av.VideoFrame.from_image(image)
            frame.pts = round(seconds * 1000)
            frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        if sound:
            frame = av.AudioFrame(format="s16", layout="mono", samples=8000)
            frame.sample_rate, frame.pts, frame.time_base = 8000, 0, Fraction(1, 8000)
            frame.planes[0].update(bytes(frame.planes[0].buffer_size))
            for packet in sound.encode(frame):
                container.mux(packet)
            for packet in sound.encode():
                container.mux(packet)


class MediaProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="media-read-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_image_crop_preserves_native_pixels_and_source(self):
        source = self.root / "image.png"
        original = Image.new("RGB", (600, 300), "white")
        ImageDraw.Draw(original).rectangle((100, 80, 180, 160), fill="red")
        original.save(source)
        digest = hashlib.sha256(source.read_bytes()).digest()
        output = self.root / "output"
        result = helper.main(["image", "--input", str(source), "--output", str(output),
                              "--crop", "90,70,190,170", "--max-side", "128"])
        self.assertEqual(result["crop_box_oriented_pixels"], [90, 70, 190, 170])
        with Image.open(output / "crop.png") as crop:
            self.assertEqual(crop.size, (100, 100))
            self.assertEqual(crop.tobytes(), original.crop((90, 70, 190, 170)).tobytes())
        with Image.open(output / "overview.png") as preview:
            self.assertEqual(preview.width, 128)
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), digest)

    def test_exif_orientation_is_applied_before_crop(self):
        source = self.root / "oriented.jpg"
        image = Image.new("RGB", (40, 20), "green")
        exif = image.getexif()
        exif[274] = 6
        image.save(source, exif=exif)
        output = self.root / "output"
        result = helper.main(["image", "--input", str(source), "--output", str(output),
                              "--crop", "0,0,20,30"])
        self.assertEqual(result["oriented_size"], [20, 40])
        with Image.open(source) as original, Image.open(output / "crop.png") as crop:
            self.assertEqual(crop.tobytes(),
                             ImageOps.exif_transpose(original).convert("RGB").crop((0, 0, 20, 30)).tobytes())

    def test_transparency_is_preserved_in_crop_and_declared_in_overview(self):
        source = self.root / "transparent.png"
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((5, 5, 10, 10), fill="black")
        image.save(source)
        output = self.root / "output"
        result = helper.main(["image", "--input", str(source), "--output", str(output),
                              "--crop", "0,0,20,20"])
        with Image.open(output / "crop.png") as crop, Image.open(output / "overview.png") as overview:
            self.assertEqual(crop.mode, "RGBA")
            self.assertEqual(crop.tobytes(), image.tobytes())
            self.assertEqual(overview.getpixel((0, 0)), (255, 255, 255))
        self.assertTrue(result["crop_preserves_alpha"])
        self.assertEqual(result["overview_alpha_background"], "white")

    def test_existing_output_is_not_overwritten(self):
        source = self.root / "image.png"
        Image.new("RGB", (20, 20)).save(source)
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "important.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            helper.main(["image", "--input", str(source), "--output", str(output)])
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_invalid_crop_is_rejected_before_output_creation(self):
        source = self.root / "image.png"
        Image.new("RGB", (20, 20)).save(source)
        output = self.root / "output"
        with self.assertRaises(ValueError):
            helper.main(["image", "--input", str(source), "--output", str(output),
                         "--crop", "0,0,21,20"])
        self.assertFalse(output.exists())

    def test_variable_timestamps_not_nominal_frame_indices(self):
        source = self.root / "variable.mkv"
        make_video(source)
        output = self.root / "frames"
        result = helper.main(["video", "--input", str(source), "--output", str(output),
                              "--times", "0,0.15,0.49,0.9"])
        self.assertTrue(result["all_requested_samples_extracted"])
        self.assertEqual([sample["time_s"] for sample in result["samples"]], [0, 0.2, 0.5, 1.0])
        self.assertTrue((output / "contact-sheet.jpg").is_file())
        self.assertFalse(result["audio_analyzed"])

    def test_multiple_targets_at_one_frame_are_not_duplicated(self):
        source = self.root / "variable.mkv"
        make_video(source)
        result = helper.main(["video", "--input", str(source), "--output", str(self.root / "frames"),
                              "--times", "0.01,0.1,0.15"])
        self.assertEqual(len(result["samples"]), 1)
        self.assertEqual(result["samples"][0]["requested_times_s"], [0.01, 0.1, 0.15])
        self.assertEqual(result["samples"][0]["time_s"], 0.2)

    def test_nonzero_stream_start_uses_relative_presentation_times(self):
        source = self.root / "offset.mkv"
        make_video(source, times=(5.0, 5.2, 5.5, 6.0))
        result = helper.main(["video", "--input", str(source), "--output", str(self.root / "frames"),
                              "--times", "0,0.15,0.49,0.9"])
        self.assertEqual(result["timeline_origin_s"], 5.0)
        self.assertEqual([sample["time_s"] for sample in result["samples"]], [0, 0.2, 0.5, 1.0])
        self.assertEqual(result["samples"][0]["absolute_pts_s"], 5.0)

    def test_display_rotation_is_applied_and_recorded(self):
        source = self.root / "rotated.mp4"
        with av.open(str(source), "w") as container:
            stream = container.add_stream("mpeg4", rate=10)
            stream.width, stream.height, stream.pix_fmt = 160, 100, "yuv420p"
            stream.set_display_rotation(90)
            frame = av.VideoFrame.from_image(Image.new("RGB", (160, 100), "red"))
            for packet in stream.encode(frame):
                container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        result = helper.main(["video", "--input", str(source), "--output", str(self.root / "frames"),
                              "--times", "0"])
        self.assertEqual(result["samples"][0]["rotation_ccw_degrees"], 90)
        self.assertEqual(result["samples"][0]["output_size"], [100, 160])

    def test_decode_budget_exposes_unresolved_targets(self):
        source = self.root / "variable.mkv"
        make_video(source)
        result = helper.main(["video", "--input", str(source), "--output", str(self.root / "frames"),
                              "--times", "0,0.9", "--max-decoded", "1"])
        self.assertFalse(result["all_requested_samples_extracted"])
        self.assertEqual(result["unresolved_times_s"], [0.9])
        self.assertEqual(result["coverage"]["stop_reason"], "decoded_frame_budget")

    def test_audio_is_inventoried_not_claimed_analyzed(self):
        source = self.root / "audio.mkv"
        make_video(source, audio=True)
        result = helper.main(["probe", "--input", str(source)])
        self.assertEqual(len(result["audio_streams"]), 1)
        self.assertFalse(result["audio_analyzed"])

    def test_invalid_times_and_counts_are_rejected(self):
        args = helper.parser().parse_args(["video", "--input", "unused", "--output", "unused"])
        for bad in ("nan", "-1", "inf", "1.0"):
            args.times = bad
            with self.assertRaises(ValueError):
                helper.target_times(args, 1.0)
        args.times = None
        args.frames = 97
        with self.assertRaises(ValueError):
            helper.target_times(args, 1.0)

    def test_secondary_resources_are_rejected(self):
        with self.assertRaises(ValueError):
            helper.deny_secondary_resource("https://example.invalid/segment", 0, {})


if __name__ == "__main__":
    unittest.main()
