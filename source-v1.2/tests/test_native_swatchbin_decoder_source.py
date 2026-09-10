from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "patch_kfps_wheel_morph_diagnostic.py"
DECODER = ROOT / "tools" / "kfps_wheel_morph" / "NativeSwatchbinDecoder.cs"


class NativeSwatchbinDecoderSourceTests(unittest.TestCase):
    def test_patcher_stages_read_only_decode_mode(self):
        patcher = PATCHER.read_text(encoding="utf-8")
        self.assertIn("NativeSwatchbinDecoder.cs", patcher)
        self.assertIn("NativeSwatchbinDecoder.Decode", patcher)
        self.assertIn("--decode-swatchbin", patcher)
        self.assertIn("shutil.copy2(swatch_helper", patcher)

    def test_decoder_uses_forzatools_txcb_txch_contract(self):
        text = DECODER.read_text(encoding="utf-8")
        self.assertIn("new Bundle()", text)
        self.assertIn("OfType<TextureContentBlob>()", text)
        self.assertIn("TextureContentHeaderMetadata", text)
        self.assertIn("BundleMetadata.TAG_METADATA_TextureContentHeader", text)
        self.assertIn("ParseWithBlobVersion", text)
        self.assertIn("PCTextureContentHeader", text)
        self.assertIn("DurangoTextureContentHeader", text)

    def test_decoder_writes_dds_derivative_without_overwriting_source(self):
        text = DECODER.read_text(encoding="utf-8")
        self.assertIn("Swatchbin decode output must not overwrite the source payload", text)
        self.assertIn("0x20534444u", text)
        self.assertIn("0x30315844u", text)
        self.assertIn("File.Move(temporary, output, true)", text)
        self.assertIn("GameDataModified", text)
        self.assertIn("false);", text)

    def test_decoder_supports_native_bc_formats_without_image_guessing(self):
        text = DECODER.read_text(encoding="utf-8")
        for dxgi in ("71", "72", "77", "78", "83", "84", "95", "96", "98", "99"):
            self.assertIn(dxgi, text)
        self.assertNotIn("vehicle", text.casefold())
        self.assertNotIn("car id", text.casefold())

    def test_decoder_marks_platform_and_refuses_tiled_durango_bytes(self):
        text = DECODER.read_text(encoding="utf-8")
        self.assertIn("bool IsDurangoFormat", text)
        self.assertIn("isDurango = false", text)
        self.assertIn("isDurango = true", text)
        self.assertIn("if (isDurango)", text)
        self.assertIn("XG detile/dealign", text)
        self.assertIn("refusing to wrap tiled texture bytes as linear DDS", text)
        durango_guard = text.index("if (isDurango)")
        raw_read = text.index("var raw = textureBlob.Data")
        dds_build = text.index("var dds = CreateDds")
        self.assertLess(durango_guard, raw_read)
        self.assertLess(durango_guard, dds_build)


if __name__ == "__main__":
    unittest.main()
