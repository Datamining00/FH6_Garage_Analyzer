from __future__ import annotations

import argparse
from pathlib import Path
import shutil


PINNED_KFPS_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"

_BASE_CLI = '''            if (args.Length == 3 && args[0] == "--decode-swatchbin")
            {
                var diagnostic = NativeSwatchbinDecoder.Decode(args[1], args[2]);
                Console.WriteLine(JsonSerializer.Serialize(diagnostic, JsonOptions()));
                return 0;
            }
            if (args.Length != 2 || args[0] != "--request")
                throw new InvalidDataException(
                    "Usage: Kfps.ChassisConverter --request <request.json> OR --decode-swatchbin <input.swatchbin> <output.dds>");'''

_EXTENDED_CLI = '''            if (args.Length == 3 && args[0] == "--decode-swatchbin")
            {
                var diagnostic = NativeSwatchbinDecoder.Decode(args[1], args[2]);
                Console.WriteLine(JsonSerializer.Serialize(diagnostic, JsonOptions()));
                return 0;
            }
            if (args.Length == 2 && args[0] == "--diagnose-materialbin")
            {
                var diagnostic = MaterialbinReferenceRuntime.Diagnose(args[1]);
                Console.WriteLine(JsonSerializer.Serialize(diagnostic, JsonOptions()));
                return 0;
            }
            if (args.Length != 2 || args[0] != "--request")
                throw new InvalidDataException(
                    "Usage: Kfps.ChassisConverter --request <request.json> OR --decode-swatchbin <input.swatchbin> <output.dds> OR --diagnose-materialbin <input.materialbin>");'''


def patch(kfps_root: Path, helper_source: Path) -> None:
    converter = kfps_root / "tools" / "livery" / "chassis-converter"
    program = converter / "Program.cs"
    if not program.is_file():
        raise RuntimeError(f"Pinned/patched KFPS Program.cs was not found: {program}")
    if not helper_source.is_file():
        raise RuntimeError(f"MaterialbinReferenceDiagnostic.cs was not found: {helper_source}")

    text = program.read_text(encoding="utf-8-sig")
    if "--diagnose-materialbin" in text:
        raise RuntimeError("Program.cs already contains the materialbin diagnostic mode.")
    count = text.count(_BASE_CLI)
    if count != 1:
        raise RuntimeError(
            "Expected exactly one established --decode-swatchbin CLI contract before adding "
            f"materialbin diagnostics; found {count}."
        )
    text = text.replace(_BASE_CLI, _EXTENDED_CLI, 1)
    program.write_text(text, encoding="utf-8-sig")
    shutil.copy2(helper_source, converter / "MaterialbinReferenceDiagnostic.cs")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add the read-only materialbin reference diagnostic mode after the established W3 KFPS patch."
    )
    parser.add_argument("--kfps-root", required=True, type=Path)
    parser.add_argument(
        "--helper-source",
        type=Path,
        default=Path(__file__).resolve().parent / "kfps_wheel_morph" / "MaterialbinReferenceDiagnostic.cs",
    )
    args = parser.parse_args()
    patch(args.kfps_root.resolve(), args.helper_source.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
