from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.wheel_geometry import repair_wheelstyle_lateral_translation


def _write_fixture(path) -> None:
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 0}], "bufferViews": [], "accessors": [], "meshes": []}
    binary = bytearray()
    sets = [
        [(0.94, 0.0, 0.0), (1.00, 0.2, 0.0), (0.96, 0.0, 0.2)],
        [(0.95, 0.0, 0.0), (1.01, 0.2, 0.0), (0.97, 0.0, 0.2)],
        [(0.00, 0.0, 0.0), (1.00, 0.2, 0.0), (0.02, 0.0, 0.2)],
    ]
    for number, positions in enumerate(sets):
        position_offset = len(binary)
        for point in positions:
            binary.extend(struct.pack("<fff", *point))
        index_offset = len(binary)
        binary.extend(struct.pack("<HHH", 0, 1, 2))
        binary.extend(b"\x00\x00")
        p_view = len(document["bufferViews"])
        document["bufferViews"].append({"buffer": 0, "byteOffset": position_offset, "byteLength": 36})
        i_view = len(document["bufferViews"])
        document["bufferViews"].append({"buffer": 0, "byteOffset": index_offset, "byteLength": 6})
        p_accessor = len(document["accessors"])
        document["accessors"].append({"bufferView": p_view, "componentType": 5126, "count": 3, "type": "VEC3"})
        i_accessor = len(document["accessors"])
        document["accessors"].append({"bufferView": i_view, "componentType": 5123, "count": 3, "type": "SCALAR"})
        document["meshes"].append({
            "name": f"structural_{number}",
            "extras": {"kfps_part_type": "WheelStyle", "kfps_instance_identity": "instance-a"},
            "primitives": [{"attributes": {"POSITION": p_accessor}, "indices": i_accessor}],
        })
    document["buffers"][0]["byteLength"] = len(binary)
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(binary)
    path.write_bytes(
        b"glTF" + struct.pack("<II", 2, total)
        + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
        + struct.pack("<II", len(binary), 0x004E4942) + binary
    )


class WheelGeometryTests(unittest.TestCase):
    def test_repairs_only_confirmed_mixed_lateral_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "wheel.glb"
            _write_fixture(target)

            first = repair_wheelstyle_lateral_translation(target)
            second = repair_wheelstyle_lateral_translation(target)

        self.assertEqual(first.status, "applied")
        self.assertEqual(first.wheel_instances, 1)
        self.assertEqual(first.repaired_primitives, 1)
        self.assertEqual(first.repaired_vertices, 2)
        self.assertEqual(second.status, "no_confirmed_candidates")


if __name__ == "__main__":
    unittest.main()
