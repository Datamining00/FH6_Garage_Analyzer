from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_wheel_morph_bake_diagnostic.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("wheel_morph_bake_request_schema", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WheelMorphBakeRequestSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_script()

    def test_scene_request_uses_kfps_snake_case_property_names(self):
        payload = self.module.conversion_request_payload(
            Path(r"C:\cars\FER_FXX_05.zip"),
            Path(r"C:\out\FER_FXX_05.glb"),
            "FER_FXX_05.carbin",
        )
        self.assertEqual(
            payload,
            {
                "archive": r"C:\cars\FER_FXX_05.zip",
                "output": r"C:\out\FER_FXX_05.glb",
                "carbin_entry": "FER_FXX_05.carbin",
                "entries": [],
            },
        )
        self.assertNotIn("CarbinEntry", payload)
        self.assertNotIn("Archive", payload)


if __name__ == "__main__":
    unittest.main()
