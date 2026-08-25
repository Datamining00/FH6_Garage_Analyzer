from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from fh6garage.v1_3_2_global_ui_patch import (
    DEFAULT_THUMBNAIL_ASPECT,
    _AspectFitThumbnailController,
    _load_original_pixmap,
    _relax_fixed_card_text_heights,
)


ROOT = Path(__file__).resolve().parents[1]


class V132GlobalUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _card_with_image(self):
        card = QFrame()
        layout = QVBoxLayout(card)
        host = QWidget(card)
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(host)
        host_layout.addWidget(label)
        layout.addWidget(host)
        card._fh6_image_label = label
        return card, host, label

    def test_original_16_9_thumbnail_keeps_16_9_host(self) -> None:
        card, host, label = self._card_with_image()
        controller = _AspectFitThumbnailController(card, label)
        source = QPixmap(640, 360)
        source.fill()
        controller.set_source(source)

        self.assertAlmostEqual(controller.aspect_ratio, 16 / 9, places=5)
        self.assertEqual(controller.target_height(400), 225)

        host.resize(400, 100)
        controller.apply()
        self.assertEqual(host.height(), 225)
        rendered = label.pixmap()
        self.assertIsNotNone(rendered)
        self.assertFalse(rendered.isNull())
        self.assertEqual((rendered.width(), rendered.height()), (400, 225))

    def test_non_16_9_thumbnail_uses_its_real_ratio(self) -> None:
        card, _host, label = self._card_with_image()
        controller = _AspectFitThumbnailController(card, label)
        source = QPixmap(600, 400)
        source.fill()
        controller.set_source(source)
        self.assertAlmostEqual(controller.aspect_ratio, 1.5, places=5)
        self.assertEqual(controller.target_height(450), 300)

    def test_clear_source_restores_safe_default_ratio(self) -> None:
        card, _host, label = self._card_with_image()
        controller = _AspectFitThumbnailController(card, label)
        source = QPixmap(600, 400)
        source.fill()
        controller.set_source(source)
        controller.clear_source()
        self.assertAlmostEqual(
            controller.aspect_ratio,
            DEFAULT_THUMBNAIL_ASPECT,
            places=5,
        )
        self.assertTrue(label.pixmap().isNull())

    def test_fixed_metadata_height_becomes_dpi_safe_minimum(self) -> None:
        card, _host, image = self._card_with_image()
        text = QLabel("Vehicle: 2025 Toyota Land Cruiser", card)
        text.setFixedHeight(28)
        card.layout().addWidget(text)

        _relax_fixed_card_text_heights(card, image)

        self.assertGreater(text.maximumHeight(), 28)
        self.assertGreaterEqual(text.minimumHeight(), 28)

    def test_original_image_loader_does_not_force_crop_target(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "thumb.png"
            source = QPixmap(640, 360)
            source.fill()
            self.assertTrue(source.save(str(path), "PNG"))
            loaded = _load_original_pixmap(path)
            self.assertFalse(loaded.isNull())
            self.assertEqual((loaded.width(), loaded.height()), (640, 360))

    def test_patch_order_preserves_thread_affinity_finalizer(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        perf = "apply_v1_3_2_ui_performance_patches(MainWindow)"
        global_ui = "apply_v1_3_2_global_ui_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertNotIn(perf, source)
        self.assertLess(source.index(global_ui), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
