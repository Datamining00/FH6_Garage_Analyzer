from __future__ import annotations

import sys


def install_cold_livery_render_fastpath_patch() -> bool:
    """Use the renderer's single decode to omit empty section image work."""
    from . import kfps_render_backend as backend

    if getattr(backend, "_fh6_cold_livery_render_fastpath_patched", False):
        return False
    original = backend.render_clivery_sections

    def wrapped(source, *, game_folder=None, resolution=None, output_root=None, log=None):
        return original(
            source,
            game_folder=game_folder,
            resolution=resolution,
            output_root=output_root,
            log=log,
            skip_empty_sections=True,
        )

    backend.render_clivery_sections = wrapped
    backend._fh6_cold_livery_render_fastpath_patched = True
    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "render_clivery_sections", None) is original:
        integration.render_clivery_sections = wrapped
    return True
