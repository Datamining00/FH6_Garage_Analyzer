from __future__ import annotations

import unittest

from fh6garage.livery_layer_reverse_probe import (
    _BUTTON_NAME,
    _reverse_container,
    consume_transient_reverse,
    request_transient_reverse,
)


class LayerReverseProbeTests(unittest.TestCase):
    def test_reverse_container_preserves_tuple_type(self) -> None:
        source = ({"id": 1}, {"id": 2}, {"id": 3})
        result = _reverse_container(source)
        self.assertIsInstance(result, tuple)
        self.assertEqual([item["id"] for item in result], [3, 2, 1])

    def test_reverse_container_preserves_list_type(self) -> None:
        source = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = _reverse_container(source)
        self.assertIsInstance(result, list)
        self.assertEqual([item["id"] for item in result], [3, 2, 1])

    def test_reverse_request_is_one_shot(self) -> None:
        request_transient_reverse("Right", 4)
        self.assertTrue(consume_transient_reverse("Right", 4))
        self.assertFalse(consume_transient_reverse("Right", 4))

    def test_reverse_request_is_scoped_by_scale(self) -> None:
        request_transient_reverse("Left", 8)
        self.assertFalse(consume_transient_reverse("Left", 4))
        self.assertTrue(consume_transient_reverse("Left", 8))

    def test_probe_uses_a_dedicated_nonpersistent_ui_button(self) -> None:
        self.assertEqual(_BUTTON_NAME, "liveryPreviewReverseLayersButton")


if __name__ == "__main__":
    unittest.main()
