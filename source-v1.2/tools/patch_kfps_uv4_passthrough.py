from __future__ import annotations

import argparse
from pathlib import Path


PINNED_KFPS_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"


def _replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact occurrence, found {count}")
    return text.replace(old, new, 1)


def patch(kfps_root: Path) -> None:
    """Preserve source UV channel 4 through the pinned KFPS GLB converter.

    This patch does not synthesize, copy, or project UV coordinates. It only
    extends the converter's existing accepted channel range from 0..3 to 0..4.
    The existing GlbWriter already emits every retained channel as
    TEXCOORD_<channel>.
    """
    converter = kfps_root / "tools" / "livery" / "chassis-converter"
    program = converter / "Program.cs"
    writer = converter / "GlbWriter.cs"
    if not program.is_file():
        raise RuntimeError(f"Pinned KFPS Program.cs was not found: {program}")
    if not writer.is_file():
        raise RuntimeError(f"Pinned KFPS GlbWriter.cs was not found: {writer}")

    text = program.read_text(encoding="utf-8-sig")
    text = _replace_exact(
        text,
        "item.Key is >= 0 and <= 3 && item.Value.Length == vertexCount",
        "item.Key is >= 0 and <= 4 && item.Value.Length == vertexCount",
        "include UV4 in output-size accounting",
    )
    text = _replace_exact(
        text,
        "channel is < 0 or > 3 || source.Length != vertexCount",
        "channel is < 0 or > 4 || source.Length != vertexCount",
        "preserve native UV4 in TransformUvChannels",
    )

    writer_text = writer.read_text(encoding="utf-8-sig")
    expected_writer_contract = 'attributes[$"TEXCOORD_{channel}"] = AddVector2Accessor'
    if writer_text.count(expected_writer_contract) != 1:
        raise RuntimeError(
            "Pinned KFPS GlbWriter no longer exposes the generic TEXCOORD_<channel> contract."
        )

    program.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Patch pinned KFPS to preserve an existing native UV4 channel in GLB output; "
            "no UV data is synthesized."
        )
    )
    parser.add_argument("--kfps-root", required=True, type=Path)
    args = parser.parse_args()
    patch(args.kfps_root.resolve())
    print(f"Patched pinned KFPS native UV4 pass-through: {args.kfps_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
