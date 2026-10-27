"""Dependency-light tests for upload validation and plant progress logic."""
import ast
import io
import re
import unittest
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps


APP_SOURCE = Path(__file__).with_name("app.py")
if not APP_SOURCE.exists():
    APP_SOURCE = Path(__file__).with_name("plant_app.py")
SOURCE = APP_SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
NAMES = {"validated_upload", "calculate_days_grown", "estimate_harvest_progress", "harvest_percent", "model_signs", "harvest_guidance"}
DEFS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
namespace = {
    "Image": Image,
    "ImageOps": ImageOps,
    "io": io,
    "warnings": __import__("warnings"),
    "MAX_IMAGE_BYTES": 10 * 1024 * 1024,
    "HARVEST_PERCENT": {"成長途中": 20, "成熟中": 75},
    "VISUAL_STAGE_WEIGHT": .70,
    "ELAPSED_DAYS_WEIGHT": .30,
    "REFERENCE_FRUIT_TO_HARVEST_DAYS": 43,
    "date": date,
    "MODEL_NAMES": {"whole": "株全体", "leaf": "葉", "fruit": "実"},
    "HARVEST_GUIDANCE": {"実なし（未診断）": ("実の診断なし", "写真に実が写るようになったら成熟度を確認できます。")},
}
exec(compile(ast.Module(body=DEFS, type_ignores=[]), "plant_app.py", "exec"), namespace)


class Upload:
    def __init__(self, data):
        self.data = data

    def getvalue(self):
        return self.data


class TestPlantApp(unittest.TestCase):
    def test_without_fruit(self):
        signs = namespace["model_signs"]({"whole": {"label": "良好"}, "leaf": {"label": "正常"}})
        self.assertIn("株全体：良好", signs)
        self.assertNotIn("実：", signs)
        stage, _ = namespace["harvest_guidance"]("実なし（未診断）")
        self.assertEqual(stage, "実の診断なし")

    def test_model_files_match_label_count(self):
        root = Path(__file__).parent / "models"
        for name, expected in (("whole", 3), ("leaf", 11), ("fruit", 5)):
            model = (root / name / "keras_model.h5").read_bytes()
            self.assertEqual(model[:8], b"\x89HDF\r\n\x1a\n")
            outputs = re.findall(rb'"units": (\d+), "activation": "softmax"', model)
            self.assertEqual(int(outputs[-1]), expected)
            labels = (root / name / "labels.txt").read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(len([line for line in labels if line.strip()]), expected)

    def test_valid_photo(self):
        buf = io.BytesIO()
        Image.new("RGB", (32, 24), "green").save(buf, "PNG")
        photo = namespace["validated_upload"](Upload(buf.getvalue()))
        self.assertEqual(photo.size, (32, 24))

    def test_invalid_photo(self):
        with self.assertRaises(ValueError):
            namespace["validated_upload"](Upload(b"not an image"))

    def test_large_photo(self):
        with self.assertRaisesRegex(ValueError, "10MB"):
            namespace["validated_upload"](Upload(b"x" * (10 * 1024 * 1024 + 1)))

    def test_day_count(self):
        self.assertEqual(namespace["calculate_days_grown"](date(2026, 5, 1), date(2026, 5, 1)), 1)

    def test_progress(self):
        percent, _ = namespace["estimate_harvest_progress"]("成熟中", None, date.today())
        self.assertEqual(percent, 75)


if __name__ == "__main__":
    unittest.main()
