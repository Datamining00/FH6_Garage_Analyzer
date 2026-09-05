from __future__ import annotations

import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "source-v1.2" / "fh6garage" / "preview3d" / "chassis_converter.py"
EXPECTED_SOURCE_BLOB = "5f1f895a5da23b82a2b35f5177de6329d68ecc07"
FTS_BINARY_COMMIT = "e0a0b5e3ad5054b8410ae4497c5dacf2db6adf19"
FTS_BINARY_BLOB = "7556c1e4cd3b3d532339a9226241988be69cd27d"
FTS_REFERENCE_COMMIT = "4f373c5fb192551ce5249e320dd79b1399b693ca"
FTS_FORMAT = "fh6_fts_chassis_conversion_v1"
FTS_GEOMETRY_REVISION = "fts_native_transform_v1"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    raw = SOURCE.read_bytes()
    text = raw.decode("utf-8")

    if f'CONVERTER_COMMIT = "{FTS_BINARY_COMMIT}"' in text:
        print("FTS app integration already applied; no changes required.")
        return

    actual_blob = git_blob_sha1(raw)
    if actual_blob != EXPECTED_SOURCE_BLOB:
        raise RuntimeError(
            "Refusing to patch an unknown chassis_converter.py: "
            f"expected Git blob {EXPECTED_SOURCE_BLOB}, got {actual_blob}"
        )

    text = replace_once(
        text,
        '''from .wheel_geometry import (\n    WHEEL_GEOMETRY_REVISION,\n    WheelGeometryError,\n    repair_wheelstyle_lateral_translation,\n)\n\n''',
        "",
        "legacy WheelStyle heuristic import",
    )

    text = replace_once(
        text,
        '''CONVERTER_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"\nCONVERTER_BLOB_SHA1 = "7d3f83ce4d787c752a01729d1a5a6b81ca5cc800"\nCONVERTER_URL = (\n    "https://raw.githubusercontent.com/heyitshestia/kloudys-forza-painter-suite/"\n    f"{CONVERTER_COMMIT}/tools/livery/chassis-converter/bin/win-x64/Kfps.ChassisConverter.exe"\n)\n''',
        f'''# Real ForzaTechStudio geometry port. The binary is reproducibly built in this\n# repository from the pinned KFPS headless exporter plus the pinned FTS geometry\n# semantics patch. Do not silently fall back to the legacy KFPS binary.\nCONVERTER_COMMIT = "{FTS_BINARY_COMMIT}"\nCONVERTER_BLOB_SHA1 = "{FTS_BINARY_BLOB}"\nCONVERTER_URL = (\n    "https://raw.githubusercontent.com/Datamining00/FH6_Garage_Analyzer/"\n    f"{{CONVERTER_COMMIT}}/tools/fts-chassis-converter/bin/win-x64/FH6.FtsChassisConverter.exe"\n)\nFTS_REFERENCE_COMMIT = "{FTS_REFERENCE_COMMIT}"\nFTS_CONVERTER_FORMAT = "{FTS_FORMAT}"\nFTS_NATIVE_GEOMETRY_REVISION = "{FTS_GEOMETRY_REVISION}"\n''',
        "converter pin",
    )

    text = replace_once(
        text,
        'return tools_dir() / "Kfps.ChassisConverter.exe"',
        'return tools_dir() / "FH6.FtsChassisConverter.exe"',
        "converter filename",
    )
    text = replace_once(
        text,
        'progress("Downloading the pinned KFPS chassis converter (about 37 MB)...")',
        'progress("Downloading the pinned ForzaTechStudio chassis converter (about 37 MB)...")',
        "download progress",
    )
    text = replace_once(
        text,
        '"Could not download Kfps.ChassisConverter.exe from the pinned upstream source. "',
        '"Could not download FH6.FtsChassisConverter.exe from the pinned repository source. "',
        "download error",
    )

    text = replace_once(
        text,
        '''    wheel_geometry_summary: dict = {}\n    wheel_geometry_error: str | None = None\n''',
        '''    # FTS reconstructs WheelStyle in source-space. Never apply the legacy\n    # lateral_translation_v1 vertex heuristic to FTS-generated geometry.\n    wheel_geometry_summary: dict = {\n        "status": "fts_native_geometry",\n        "revision": FTS_NATIVE_GEOMETRY_REVISION,\n        "repaired_vertices": 0,\n    }\n    wheel_geometry_error: str | None = None\n''',
        "native geometry diagnostic initialization",
    )

    text = replace_once(
        text,
        '''            # Repair only after the WheelStyle source/primitive mapping above has\n            # validated. This aid is fail-open and never invalidates a usable GLB.\n            if not wheel_visibility_error:\n                try:\n                    wheel_geometry_summary = repair_wheelstyle_lateral_translation(output).as_dict()\n                except (OSError, ValueError, WheelGeometryError) as exc:\n                    wheel_geometry_error = f"{type(exc).__name__}: {exc}"\n\n''',
        '''            # Geometry is already reconstructed by the pinned FTS converter.\n            # Wheel visibility validation remains fail-open, but no vertex-position\n            # repair is permitted on this path.\n\n''',
        "legacy WheelStyle repair call",
    )

    text = replace_once(
        text,
        'raise ChassisConverterError(f"Could not start Kfps.ChassisConverter.exe: {exc}") from exc',
        'raise ChassisConverterError(f"Could not start FH6.FtsChassisConverter.exe: {exc}") from exc',
        "converter start error",
    )

    text = replace_once(
        text,
        '''    if wheel_geometry_error:\n        wheel_geometry_summary = dict(wheel_geometry_summary or {})\n        wheel_geometry_summary.setdefault("status", "validation_failed_proceeding")\n''',
        "",
        "legacy wheel geometry error handling",
    )

    text = replace_once(
        text,
        '''        if isinstance(candidate, dict):\n            diagnostics = candidate\n\n    # The raw carbin can mention optional/unselected models that are absent from\n''',
        '''        if isinstance(candidate, dict):\n            diagnostics = candidate\n\n    # A valid GLB is not enough for this branch: refuse to represent a legacy or\n    # unknown exporter as an FTS result. The binary itself is Git-blob pinned above.\n    converter_format = str(diagnostics.get("format") or "")\n    if converter_format != FTS_CONVERTER_FORMAT:\n        try:\n            output.unlink(missing_ok=True)\n        except OSError:\n            pass\n        raise ChassisConverterError(\n            "Pinned ForzaTechStudio converter returned an unexpected format marker: "\n            f"{converter_format or '<missing>'}; expected {FTS_CONVERTER_FORMAT}."\n        )\n\n    # The raw carbin can mention optional/unselected models that are absent from\n''',
        "FTS format validation",
    )

    text = replace_once(
        text,
        'diagnostics["wheel_geometry_revision"] = WHEEL_GEOMETRY_REVISION',
        'diagnostics["wheel_geometry_revision"] = FTS_NATIVE_GEOMETRY_REVISION',
        "geometry revision diagnostic",
    )

    # Retain the existing fail-open visibility behavior and fail-closed neutral A+B/C
    # classification. Only the legacy positional heuristic is removed.
    SOURCE.write_text(text, encoding="utf-8", newline="\n")
    print(f"Applied FTS app integration to {SOURCE}")
    print(f"Pinned converter commit: {FTS_BINARY_COMMIT}")
    print(f"Pinned converter Git blob: {FTS_BINARY_BLOB}")
    print(f"FTS reference commit: {FTS_REFERENCE_COMMIT}")


if __name__ == "__main__":
    main()
