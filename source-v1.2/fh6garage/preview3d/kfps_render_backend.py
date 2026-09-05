from __future__ import annotations

import hashlib
import binascii
import importlib
import io
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from .livery_resolution import LiveryResolution, resolve_livery_resolution

KFPS_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"
RUNTIME_REVISION = "m6.24b-final-verify-v1"
KFPS_ARCHIVE_URL = (
    "https://codeload.github.com/heyitshestia/kloudys-forza-painter-suite/zip/"
    + KFPS_COMMIT
)
SECTION_NAMES = [
    "Front", "Back", "Top", "Left", "Right", "Spoiler",
    "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
]


class KfpsRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    source_path: Path
    output_dir: Path
    car_id: int
    layer_count: int
    section_counts: dict[str, int]
    png_paths: dict[str, Path]
    decoder_warnings: list[str]
    canvas_size: tuple[int, int] = (2048, 1024)
    resolution_name: str = "normal"
    raster_ids: tuple[int, ...] = ()
    raster_skipped_ids: tuple[int, ...] = ()
    raster_skipped_layer_count: int = 0


def _app_root() -> Path:
    """Persistent root for the required pinned KFPS renderer runtime only."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FH6GarageAnalyzer" / "preview3d_runtime"
    return Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"


def runtime_dir() -> Path:
    return _app_root() / "third_party" / f"kfps-renderer-{KFPS_COMMIT[:12]}"


def render_cache_root() -> Path:
    return _app_root() / "livery_sections"


def _apply_decoder_nested_group_patch(root: Path, log: Callable[[str], None] | None = None) -> None:
    """Align the pinned KFPS nested markerless-group decision with FLS evidence.

    In an FH6 livery tree the parent child bitmap is authoritative about whether
    the next direct child is a group.  The pinned KFPS decoder only probes a
    markerless group here when a transform is already pending.  FLS also probes
    when the bitmap explicitly expects a group.  Without that second condition,
    nested markerless groups can be consumed byte-by-byte as control/transform
    state and all descendant transforms become attached to the wrong node.
    """
    path = root / "tools" / "cgroup" / "forza_source_decoder.py"
    if not path.is_file():
        raise KfpsRenderError("Pinned decoder source is missing before compatibility patch.")
    text = path.read_text(encoding="utf-8")
    patched = "if (state.pending_transform or expected_group is True) and may_decode_group"
    if patched in text:
        return
    original = "if state.pending_transform and may_decode_group"
    if original not in text:
        raise KfpsRenderError(
            "Pinned decoder nested-group probe no longer matches the audited source; "
            "refusing an unverified runtime rewrite."
        )
    text = text.replace(original, patched, 1)
    path.write_text(text, encoding="utf-8")
    if log:
        log(
            "M6.23 nested-group compatibility patch active: parent bitmap may prove a "
            "nested markerless group even without pending transform."
        )


def _apply_decoder_no_skew_cutoff_patch(root: Path, log: Callable[[str], None] | None = None) -> None:
    """Remove empirical raw/effective-skew cutoffs from the pinned decoder.

    Shape candidates are still required to have valid framing/native identity
    and finite numeric fields.  Whether a candidate is structurally real is
    decided by the parent child bitmap and successful tree/section completion,
    not by an arbitrary skew magnitude.
    """
    path = root / "tools" / "cgroup" / "forza_source_decoder.py"
    if not path.is_file():
        raise KfpsRenderError("Pinned decoder source is missing before no-skew-cutoff patch.")
    text = path.read_text(encoding="utf-8")

    # Accept either the pristine pinned source or the M6.11 runtime that may
    # already exist in LocalAppData.  Rewrites are exact-string guarded.
    import re
    # Migrate either the pristine decoder or an older PoC-patched runtime.
    # The regex deliberately does not introduce a new acceptance magnitude.
    patterns = [
        r"and\s*\(abs\(skew\)\s*<\s*[0-9.]+\s*or\s*abs\(sy\s*\*\s*skew\)\s*<\s*[0-9.]+\)",
        r"and\s+abs\(skew\)\s*<\s*[0-9.]+",
    ]
    changed = False
    for pattern in patterns:
        text, count = re.subn(pattern, "", text, count=1)
        if count:
            changed = True
            break
    if not changed and "and math.isfinite(skew)" not in text:
        raise KfpsRenderError(
            "Pinned decoder shape validator no longer matches the audited source; "
            "refusing an unverified runtime rewrite."
        )
    path.write_text(text, encoding="utf-8")
    if log:
        log(
            "M6.23 decoder compatibility patch active: no empirical skew cutoff; "
            "shape validity is resolved by finite numeric data and structural completion."
        )


def _fh6_shape_validator_source(text: str) -> str | None:
    """Return only the FH6/current-shape validator body.

    The upstream module also contains an FM8 legacy validator with its own
    compatibility limits.  This PoC must not treat unrelated FM8 policy as
    evidence that the FH6 patch failed.
    """
    start = text.find("def is_valid_shape_at(")
    if start < 0:
        return None
    end = text.find("\ndef is_fm8_legacy_shape_at(", start)
    if end < 0:
        return None
    return text[start:end]


def _decoder_no_skew_cutoff_patch_present(root: Path) -> bool:
    path = root / "tools" / "cgroup" / "forza_source_decoder.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    validator = _fh6_shape_validator_source(text)
    if validator is None:
        return False
    import re
    empirical_cutoff = re.search(
        r"abs\(skew\)\s*<\s*[0-9.]|abs\(sy\s*\*\s*skew\)\s*<\s*[0-9.]",
        validator,
    )
    return "math.isfinite(skew)" in validator and empirical_cutoff is None

def _decoder_nested_group_patch_present(root: Path) -> bool:
    path = root / "tools" / "cgroup" / "forza_source_decoder.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "if (state.pending_transform or expected_group is True) and may_decode_group" in text


def _apply_renderer_canvas_limit_patch(
    root: Path, log: Callable[[str], None] | None = None
) -> None:
    """Remove the upstream 8192px preview clamp for explicit livery renders.

    The application already constrains requests to named livery-resolution modes.
    Keeping the upstream thumbnail-oriented clamp makes 8x/16x requests silently
    return the wrong dimensions, which then fail the exact output-size check.
    Rewriting is exact-string guarded so upstream drift fails closed.
    """
    path = root / "json_preview_renderer.py"
    if not path.is_file():
        raise KfpsRenderError("Pinned renderer source is missing before high-resolution patch.")
    text = path.read_text(encoding="utf-8")
    patched_width = "width = max(1, int(width))"
    patched_height = "height = max(1, int(height))"
    if patched_width in text and patched_height in text:
        return
    original_width = "width = max(1, min(8192, int(width)))"
    original_height = "height = max(1, min(8192, int(height)))"
    if original_width not in text or original_height not in text:
        raise KfpsRenderError(
            "Pinned renderer canvas clamp no longer matches the audited source; "
            "refusing an unverified runtime rewrite."
        )
    text = text.replace(original_width, patched_width, 1)
    text = text.replace(original_height, patched_height, 1)
    path.write_text(text, encoding="utf-8")
    if log:
        log(
            "M6.24B renderer compatibility patch active: explicit livery canvases "
            "are no longer clamped to 8192px."
        )


def _renderer_canvas_limit_patch_present(root: Path) -> bool:
    path = root / "json_preview_renderer.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        "width = max(1, int(width))" in text
        and "height = max(1, int(height))" in text
        and "min(8192, int(width))" not in text
        and "min(8192, int(height))" not in text
    )


def _apply_raster_inventory_patch(
    root: Path, log: Callable[[str], None] | None = None
) -> None:
    """Resolve FH6 built-in raster decals from the actual Decals.zip inventory."""
    path = root / "tools" / "livery" / "raster_decals.py"
    if not path.is_file():
        raise KfpsRenderError("Pinned raster decoder source is missing before inventory patch.")
    text = path.read_text(encoding="utf-8")
    if "self._members_by_id" in text and "_DECAL_MEMBER_RE" in text:
        return
    if "import re\n" not in text:
        text = text.replace("import io\n", "import io\nimport re\n", 1)
    anchor = "class FH6RasterDecalResolver:\n"
    if anchor not in text:
        raise KfpsRenderError("Pinned raster resolver class no longer matches audited source.")
    text = text.replace(
        anchor,
        '_DECAL_MEMBER_RE = re.compile(r"^textures/decal(\\d+)\\.swatchbin$", re.IGNORECASE)\n\n\n' + anchor,
        1,
    )
    old_members = '                self._members = {name.casefold(): name for name in bundle.namelist()}\n'
    new_members = (
        '                self._members_by_id: dict[int, str] = {}\n'
        '                for name in bundle.namelist():\n'
        '                    match = _DECAL_MEMBER_RE.fullmatch(name.replace("\\\\", "/"))\n'
        '                    if match is None:\n'
        '                        continue\n'
        '                    decal_id = int(match.group(1), 10)\n'
        '                    if decal_id in self._members_by_id:\n'
        '                        raise RasterDecalError(\n'
        '                            f"The FH6 built-in decal archive contains duplicate numeric ID {decal_id}."\n'
        '                        )\n'
        '                    self._members_by_id[decal_id] = name\n'
    )
    if old_members not in text:
        raise KfpsRenderError("Pinned raster inventory initialization no longer matches audited source.")
    text = text.replace(old_members, new_members, 1)
    old_lookup = (
        '        candidates = [\n'
        '            f"textures/decal{raster_id}.swatchbin",\n'
        '            f"textures/decal{raster_id:03d}.swatchbin",\n'
        '        ]\n'
        '        member = next((self._members[name] for name in candidates if name in self._members), "")\n'
    )
    new_lookup = '        member = self._members_by_id.get(raster_id, "")\n'
    if old_lookup not in text:
        raise KfpsRenderError("Pinned raster ID lookup no longer matches audited source.")
    text = text.replace(old_lookup, new_lookup, 1)
    path.write_text(text, encoding="utf-8")
    if log:
        log("FinalVerify raster inventory patch active: Decals.zip numeric IDs are indexed from actual archive entries.")


def _raster_inventory_patch_present(root: Path) -> bool:
    path = root / "tools" / "livery" / "raster_decals.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        "_DECAL_MEMBER_RE" in text
        and "self._members_by_id" in text
        and "member = self._members_by_id.get(raster_id" in text
        and 'f"textures/decal{raster_id}.swatchbin"' not in text
    )


def _runtime_complete(root: Path) -> bool:
    required = [
        root / "json_preview_renderer.py",
        root / "geometry_json.py",
        root / "kfps_shapes" / "__init__.py",
        root / "tools" / "cgroup" / "forza_source_decoder.py",
        root / "tools" / "cgroup" / "shape_identity.py",
        root / "tools" / "livery" / "render_contract.py",
        root / "tools" / "livery" / "vehicle_assets.py",
        root / "tools" / "livery" / "raster_decals.py",
        root / "RUNTIME_REVISION.txt",
        root / "tools" / "fabric-editor" / "shape-words.json",
        root / "tools" / "fabric-editor" / "Resources" / "Vinyls",
        root / "PINNED_COMMIT.txt",
    ]
    if not all(path.exists() for path in required):
        return False
    try:
        return (
            (root / "RUNTIME_REVISION.txt").read_text(encoding="ascii").strip() == RUNTIME_REVISION
            and _decoder_nested_group_patch_present(root)
            and _decoder_no_skew_cutoff_patch_present(root)
            and _renderer_canvas_limit_patch_present(root)
            and _raster_inventory_patch_present(root)
        )
    except OSError:
        return False


def _safe_extract_subset(archive: zipfile.ZipFile, destination: Path) -> None:
    members = archive.infolist()
    if not members:
        raise KfpsRenderError("Downloaded KFPS source archive is empty.")
    top = members[0].filename.split("/", 1)[0]
    exact = {
        "json_preview_renderer.py",
        "geometry_json.py",
        "tools/__init__.py",
        "tools/cgroup/__init__.py",
        "tools/cgroup/forza_source_decoder.py",
        "tools/cgroup/shape_identity.py",
        "tools/livery/render_contract.py",
        "tools/livery/vehicle_assets.py",
        "tools/livery/raster_decals.py",
        "tools/fabric-editor/shape-words.json",
    }
    prefixes = (
        "kfps_shapes/",
        "tools/fabric-editor/Resources/Vinyls/",
    )
    copied = 0
    for info in members:
        name = info.filename.replace("\\", "/")
        prefix = top + "/"
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):]
        if not rel or (rel not in exact and not any(rel.startswith(p) for p in prefixes)):
            continue
        target = (destination / rel).resolve()
        if destination.resolve() not in target.parents and target != destination.resolve():
            raise KfpsRenderError(f"Unsafe archive member: {rel}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        copied += 1
    if copied < 8:
        raise KfpsRenderError("Pinned KFPS archive did not contain the expected renderer files.")


def _repair_existing_runtime(root: Path, log: Callable[[str], None] | None = None) -> bool:
    # M5/M6 may already have downloaded the pinned runtime. Those revisions copied
    # upstream tools/livery/__init__.py, which eagerly imports save-installation
    # helpers irrelevant to this read-only viewer. Repair that package in place.
    core = [
        root / "json_preview_renderer.py",
        root / "geometry_json.py",
        root / "kfps_shapes" / "__init__.py",
        root / "tools" / "cgroup" / "forza_source_decoder.py",
        root / "tools" / "cgroup" / "shape_identity.py",
        root / "tools" / "livery" / "render_contract.py",
        root / "tools" / "livery" / "vehicle_assets.py",
        root / "tools" / "livery" / "raster_decals.py",
        root / "tools" / "fabric-editor" / "shape-words.json",
        root / "tools" / "fabric-editor" / "Resources" / "Vinyls",
        root / "PINNED_COMMIT.txt",
    ]
    if not root.exists() or not all(path.exists() for path in core):
        return False
    try:
        if (root / "PINNED_COMMIT.txt").read_text(encoding="ascii").strip() != KFPS_COMMIT:
            return False
        livery_init = root / "tools" / "livery" / "__init__.py"
        livery_init.write_text(
            '"""Minimal read-only projection runtime package."""\n',
            encoding="utf-8",
        )
        _apply_decoder_nested_group_patch(root, log)
        _apply_decoder_no_skew_cutoff_patch(root, log)
        _apply_renderer_canvas_limit_patch(root, log)
        _apply_raster_inventory_patch(root, log)
        (root / "RUNTIME_REVISION.txt").write_text(RUNTIME_REVISION + "\n", encoding="ascii")
    except OSError:
        return False
    if log:
        log("Repaired existing pinned KFPS runtime for read-only projection use.")
    return _runtime_complete(root)


def ensure_runtime(log: Callable[[str], None] | None = None) -> Path:
    root = runtime_dir()
    if _runtime_complete(root):
        _runtime_self_test(root)
        return root
    if _repair_existing_runtime(root, log):
        _runtime_self_test(root)
        return root
    if log:
        log("Downloading pinned KFPS MIT section-renderer runtime...")
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fh6_kfps_renderer_") as td:
        tmp = Path(td)
        archive_path = tmp / "kfps.zip"
        try:
            request = urllib.request.Request(
                KFPS_ARCHIVE_URL,
                headers={"User-Agent": "FH6-Livery-3D-Viewer-PoC-M6.23"},
            )
            with urllib.request.urlopen(request, timeout=30) as response, archive_path.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                next_report = 5 * 1024 * 1024
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    received += len(chunk)
                    if log and (received >= next_report or (total and received == total)):
                        if total:
                            log(f"Downloading KFPS runtime: {received / 1048576:.1f}/{total / 1048576:.1f} MB")
                        else:
                            log(f"Downloading KFPS runtime: {received / 1048576:.1f} MB")
                        next_report = received + 5 * 1024 * 1024
        except Exception as exc:
            raise KfpsRenderError(f"Could not download pinned KFPS renderer runtime: {exc}") from exc
        if archive_path.stat().st_size < 100_000:
            raise KfpsRenderError("Downloaded KFPS source archive is unexpectedly small.")
        staging = tmp / "runtime"
        staging.mkdir()
        try:
            with zipfile.ZipFile(archive_path) as bundle:
                _safe_extract_subset(bundle, staging)
        except zipfile.BadZipFile as exc:
            raise KfpsRenderError("Downloaded KFPS source archive is not a valid ZIP.") from exc
        # Do not copy upstream tools/livery/__init__.py: it imports save-installation
        # modules that are unrelated to read-only projection rendering. Keep this
        # runtime package deliberately minimal.
        livery_init = staging / "tools" / "livery" / "__init__.py"
        livery_init.parent.mkdir(parents=True, exist_ok=True)
        livery_init.write_text("\"\"\"Minimal read-only projection runtime package.\"\"\"\n", encoding="utf-8")
        _apply_decoder_nested_group_patch(staging, log)
        _apply_decoder_no_skew_cutoff_patch(staging, log)
        _apply_renderer_canvas_limit_patch(staging, log)
        _apply_raster_inventory_patch(staging, log)
        (staging / "PINNED_COMMIT.txt").write_text(KFPS_COMMIT + "\n", encoding="ascii")
        (staging / "RUNTIME_REVISION.txt").write_text(RUNTIME_REVISION + "\n", encoding="ascii")
        if not _runtime_complete(staging):
            raise KfpsRenderError("KFPS renderer runtime extraction is incomplete.")
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        shutil.move(str(staging), str(root))
    _runtime_self_test(root)
    if log:
        log("Pinned KFPS renderer runtime ready; decoder/render/raster/projection capabilities self-tested.")
    return root


def _runtime_self_test(root: Path) -> None:
    if not _decoder_nested_group_patch_present(root):
        raise KfpsRenderError("Pinned KFPS decoder nested-group compatibility patch is not active.")
    if not _raster_inventory_patch_present(root):
        raise KfpsRenderError("Pinned KFPS raster inventory patch is not active.")
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        decoder = importlib.import_module("tools.cgroup.forza_source_decoder")
        renderer = importlib.import_module("json_preview_renderer")
        raster = importlib.import_module("tools.livery.raster_decals")
        projection = importlib.import_module("tools.livery.render_contract")
        vehicle_assets = importlib.import_module("tools.livery.vehicle_assets")
        required = (
            (decoder, "clivery_to_layers"),
            (renderer, "render_typecode_layers_canvas"),
            (raster, "FH6RasterDecalResolver"),
            (projection, "_archive_masks"),
            (projection, "_projection_pixel_bounds"),
            (projection, "_projection_axis"),
            (projection, "_projection_mask_region"),
            (projection, "_pack_paint_tiles"),
            (vehicle_assets, "VehicleAsset"),
        )
        missing = [f"{module.__name__}.{name}" for module, name in required if not hasattr(module, name)]
        if missing:
            raise RuntimeError("missing capability: " + ", ".join(missing))
    except Exception as exc:
        raise KfpsRenderError(f"Pinned KFPS runtime capability self-test failed: {exc}") from exc


def _load_backend(root: Path):
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        decoder = importlib.import_module("tools.cgroup.forza_source_decoder")
        renderer = importlib.import_module("json_preview_renderer")
        raster = importlib.import_module("tools.livery.raster_decals")
    except Exception as exc:
        raise KfpsRenderError(f"Could not import the pinned KFPS renderer runtime: {exc}") from exc
    return decoder, renderer, raster


def _prepare_raster_layers(
    json_layers: list[dict],
    raster_backend,
    game_folder: str | Path | None,
    log: Callable[[str], None] | None = None,
):
    """Resolve available built-in raster layers and skip only unresolved raster layers.

    Returns (render_layers, resolver, referenced_ids, skipped_ids, skipped_layer_count).
    Vector layers are never dropped by raster-resource failure.
    """
    raster_ids = sorted({
        int(layer.get("raster_id") or 0)
        for layer in json_layers
        if layer.get("is_raster_logo") and int(layer.get("raster_id") or 0) > 0
    })
    raster_resolver = None
    skipped_raster_ids: set[int] = set()
    skip_all_raster = False
    has_raster_layers = any(layer.get("is_raster_logo") for layer in json_layers)
    if has_raster_layers:
        if not game_folder:
            skip_all_raster = True
            skipped_raster_ids.update(raster_ids)
            if log:
                log(
                    "Raster/logo resources unavailable because no FH6 game folder is selected; "
                    "raster layers will be skipped and rendering will continue."
                )
        else:
            try:
                raster_resolver = raster_backend.FH6RasterDecalResolver(game_folder)
            except Exception as exc:
                skip_all_raster = True
                skipped_raster_ids.update(raster_ids)
                raster_resolver = None
                if log:
                    log(
                        f"Could not open FH6 built-in raster decals ({exc}); "
                        "raster layers will be skipped and rendering will continue."
                    )
            if raster_resolver is not None:
                for raster_id in raster_ids:
                    try:
                        if raster_resolver(raster_id) is None:
                            skipped_raster_ids.add(raster_id)
                    except Exception:
                        skipped_raster_ids.add(raster_id)
                if log:
                    resolved = [value for value in raster_ids if value not in skipped_raster_ids]
                    if resolved:
                        log(
                            f"Raster/logo support active: {len(resolved)} built-in decal ID(s) "
                            "resolved directly from Decals.zip inventory: "
                            + ", ".join(map(str, resolved))
                        )
                    if skipped_raster_ids:
                        log(
                            "Raster/logo resource absent or undecodable; skipping ID(s) and continuing: "
                            + ", ".join(map(str, sorted(skipped_raster_ids)))
                        )

    def keep_render_layer(layer: dict) -> bool:
        if not layer.get("is_raster_logo"):
            return True
        raster_id = int(layer.get("raster_id") or 0)
        if skip_all_raster or raster_id <= 0 or raster_id in skipped_raster_ids:
            return False
        return raster_resolver is not None

    render_layers = [layer for layer in json_layers if keep_render_layer(layer)]
    skipped_raster_layer_count = sum(
        1 for layer in json_layers if layer.get("is_raster_logo") and not keep_render_layer(layer)
    )
    return (
        render_layers,
        raster_resolver,
        tuple(raster_ids),
        tuple(sorted(skipped_raster_ids)),
        int(skipped_raster_layer_count),
    )


def _section_layers(layers: list[dict]) -> dict[str, list[dict]]:
    result = {name: [] for name in SECTION_NAMES}
    for layer in layers:
        name = str(layer.get("source_section") or "")
        if name in result:
            result[name].append(layer)
    return result




def _decode_livery_sections_boundary_aware(decoder, payload: bytes):
    """Decode FH6 livery sections using structural boundaries before logical stats targets."""
    body, counts, meta = decoder.extract_livery_payload(payload)
    names = list(decoder.LIVERY_SECTION_NAMES)
    empty_size = int(decoder.LIVERY_EMPTY_SLOT_SIZE)
    remnant_size = int(decoder.LIVERY_POPULATED_REMNANT_SIZE)
    layers = []
    warnings = []
    physical_counts = {}
    raster_counts = {}
    logical_deltas = {}
    pos = 0
    end = len(body)

    for slot, name in enumerate(names):
        target = int(counts[slot] if slot < len(counts) else 0)
        if target <= 0:
            physical_counts[name] = 0
            raster_counts[name] = 0
            logical_deltas[name] = 0
            pos = min(end, pos + empty_size)
            continue

        section_start = pos
        section_root = decoder.GroupNode(source="livery_section", offset=pos, section=name)
        holder = decoder.GroupNode(source="livery_holder")
        holder.items.append(section_root)
        state = decoder.WalkState(stack=[holder, section_root])

        reserved_tail = remnant_size
        for later_slot in range(slot + 1, len(names)):
            later_target = int(counts[later_slot] if later_slot < len(counts) else 0)
            reserved_tail += empty_size if later_target <= 0 else later_target * 32
        walk_limit = max(pos, end - reserved_tail)

        next_populated = None
        empty_between = 0
        for later_slot in range(slot + 1, len(names)):
            later_target = int(counts[later_slot] if later_slot < len(counts) else 0)
            if later_target > 0:
                next_populated = later_slot
                break
            empty_between += 1

        guard = 0
        ended_by_boundary = False
        while state.decoded_shapes < target and pos < end and guard < end + 4096:
            guard += 1
            decoder.close_complete_stack(state.stack)
            if len(state.stack) < 2:
                warnings.append(f"{name}: parser stack closed before section boundary")
                break

            at_section_root = state.stack[-1] is section_root
            if at_section_root and not state.pending_transform and state.decoded_shapes > 0:
                if next_populated is not None:
                    candidate_pos = pos + remnant_size + empty_between * empty_size
                    if candidate_pos < end:
                        candidate = decoder.valid_markerless_group_at(
                            body, candidate_pos, end, allow_count_one=True, livery=True
                        )
                        if candidate is not None:
                            ended_by_boundary = True
                            break
                else:
                    trailing_empty = len(names) - slot - 1
                    tail_floor = trailing_empty * empty_size
                    if end - pos <= remnant_size + tail_floor:
                        ended_by_boundary = True
                        break

            if at_section_root and not state.pending_transform:
                markerless = decoder.valid_markerless_group_at(
                    body, pos, end, allow_count_one=True, livery=True
                )
                if markerless:
                    pos = decoder.push_markerless_group(
                        body, pos, end, markerless, state, livery=True
                    )
                    continue

            if pos >= walk_limit and next_populated is None:
                ended_by_boundary = True
                break

            next_pos = decoder.walk_step(
                body, pos, end, state, livery=True,
                livery_invert_odd_rotation=slot != 2,
            )
            if next_pos <= pos:
                warnings.append(f"{name}: decoder made no progress at body offset 0x{pos:x}")
                break
            pos = next_pos

        decoder.close_complete_stack(state.stack)
        if pos < end and body[pos] == 0x01:
            decoder.mark_previous_terminal_shape_as_mask(state)
        decoded = decoder.flatten_tree(section_root, layer_start=0, section=name)
        if slot == 5:
            for layer in decoded:
                data = layer.get("data") or []
                if len(data) >= 5:
                    data[0] = -float(data[0])
                    data[1] = -float(data[1])
                    data[4] = decoder.normalize_rotation(float(data[4]) + 180.0)

        physical = len(decoded)
        rasters = sum(1 for layer in decoded if layer.get("is_raster_logo"))
        delta = target - physical
        physical_counts[name] = physical
        raster_counts[name] = rasters
        logical_deltas[name] = delta
        if delta < 0:
            warnings.append(f"{name}: physical decode exceeded stats target by {-delta}")
        elif delta > 0 and rasters == 0:
            warnings.append(
                f"{name}: physical decode is {delta} below stats target without raster/logo records"
            )
        elif delta > 0 and rasters > 0:
            warnings.append(
                f"{name}: stats target exceeds physical placements by {delta}; "
                f"{rasters} raster/logo record(s) present (logical occupancy)"
            )
        if next_populated is not None and not ended_by_boundary and physical < target:
            warnings.append(f"{name}: next-section structural boundary was not proven")

        for layer in decoded:
            layer["section_start"] = section_start
            layers.append(layer)
        pos = min(pos, end)
        pos = min(end, pos + remnant_size)

    report = {
        "source_kind": "clivery",
        "payload_size": len(payload),
        "section_counts": dict(zip(names, counts)),
        "decoded_layers": len(layers),
        "physical_section_counts": physical_counts,
        "raster_section_counts": raster_counts,
        "logical_count_deltas": logical_deltas,
        "boundary_aware": True,
        "warnings": warnings,
        **meta,
    }
    return layers, report


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    if len(kind) != 4:
        raise ValueError("PNG chunk type must be four bytes.")
    length = len(payload).to_bytes(4, "big")
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return length + kind + payload + checksum.to_bytes(4, "big")


class _RgbaPngStreamWriter:
    """Write an RGBA8 PNG sequentially without materializing the full canvas."""

    def __init__(self, path: Path, width: int, height: int) -> None:
        self.path = Path(path)
        self.width = int(width)
        self.height = int(height)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("PNG dimensions must be positive.")
        self._file = self.path.open("wb")
        self._file.write(b"\x89PNG\r\n\x1a\n")
        ihdr = (
            self.width.to_bytes(4, "big")
            + self.height.to_bytes(4, "big")
            + bytes((8, 6, 0, 0, 0))  # 8-bit RGBA, deflate, filter, no interlace.
        )
        self._file.write(_png_chunk(b"IHDR", ihdr))
        self._compressor = zlib.compressobj(level=6)
        self._pending = bytearray()
        self._rows_written = 0
        self._row_bytes = self.width * 4

    def _emit_compressed(self, data: bytes) -> None:
        if not data:
            return
        self._pending.extend(data)
        # Keep individual IDAT chunks bounded while avoiding one chunk per row.
        if len(self._pending) >= 1024 * 1024:
            self._file.write(_png_chunk(b"IDAT", bytes(self._pending)))
            self._pending.clear()

    def write_rgba_rows(self, rgba_bytes: bytes, rows: int) -> None:
        rows = int(rows)
        expected = self._row_bytes * rows
        if len(rgba_bytes) != expected:
            raise ValueError(
                f"RGBA strip has {len(rgba_bytes)} bytes; expected {expected} "
                f"for {rows} row(s) at width {self.width}."
            )
        zero_filter = b"\x00"
        view = memoryview(rgba_bytes)
        for row in range(rows):
            start = row * self._row_bytes
            end = start + self._row_bytes
            self._emit_compressed(self._compressor.compress(zero_filter))
            self._emit_compressed(self._compressor.compress(view[start:end]))
            self._rows_written += 1

    def write_transparent_rows(self, rows: int) -> None:
        rows = int(rows)
        zero_filter = b"\x00"
        zero_row = bytes(self._row_bytes)
        for _ in range(rows):
            self._emit_compressed(self._compressor.compress(zero_filter))
            self._emit_compressed(self._compressor.compress(zero_row))
            self._rows_written += 1

    def close(self) -> None:
        if self._file.closed:
            return
        try:
            if self._rows_written != self.height:
                raise ValueError(
                    f"PNG stream wrote {self._rows_written} rows; expected {self.height}."
                )
            self._emit_compressed(self._compressor.flush())
            if self._pending:
                self._file.write(_png_chunk(b"IDAT", bytes(self._pending)))
                self._pending.clear()
            self._file.write(_png_chunk(b"IEND", b""))
        finally:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            try:
                self._file.close()
            finally:
                try:
                    self.path.unlink(missing_ok=True)
                except OSError:
                    pass
        return False


def _render_large_section_streamed(
    renderer,
    layers: list[dict],
    path: Path,
    *,
    width: int,
    height: int,
    raster_resolver,
    log: Callable[[str], None] | None = None,
    strip_height: int = 1024,
    overlap: int = 2,
) -> None:
    """Render >8192px livery canvases as exact-scale horizontal strips.

    The renderer's world-space mapping is affine, so a pixel-range sub-window can
    be rendered with the corresponding world_bounds while preserving the same
    pixels-per-Forza-unit ratio as the full canvas. A small vertical overlap is
    rendered and cropped at each strip boundary to keep bicubic raster decals and
    edge coverage continuous without allocating the full 8x/16x RGBA image.
    """
    width = int(width)
    height = int(height)
    strip_height = max(64, int(strip_height))
    overlap = max(0, int(overlap))
    world_min_x, world_min_y, world_max_x, world_max_y = (-1024.0, -512.0, 1024.0, 512.0)
    world_span_y = world_max_y - world_min_y

    with _RgbaPngStreamWriter(path, width, height) as writer:
        for output_y0 in range(0, height, strip_height):
            output_y1 = min(height, output_y0 + strip_height)
            render_y0 = max(0, output_y0 - overlap)
            render_y1 = min(height, output_y1 + overlap)
            render_h = render_y1 - render_y0

            # Renderer y=0 is world max_y. Preserve the exact full-canvas
            # pixel/world scale for this strip.
            tile_world_max_y = world_max_y - (render_y0 / height) * world_span_y
            tile_world_min_y = world_max_y - (render_y1 / height) * world_span_y
            tile_bounds = (
                world_min_x,
                tile_world_min_y,
                world_max_x,
                tile_world_max_y,
            )
            if log:
                log(
                    f"  strip {output_y0}:{output_y1} "
                    f"(render {render_y0}:{render_y1}, {width}x{render_h})"
                )
            try:
                png = renderer.render_typecode_layers_canvas(
                    layers,
                    width=width,
                    height=render_h,
                    world_bounds=tile_bounds,
                    transparent_background=True,
                    strict_assets=True,
                    raster_resolver=raster_resolver,
                )
            except TypeError:
                png = renderer.render_typecode_layers_canvas(
                    layers,
                    width=width,
                    height=render_h,
                    world_bounds=tile_bounds,
                    strict_assets=True,
                    raster_resolver=raster_resolver,
                )
            if not png:
                raise KfpsRenderError("The high-resolution strip renderer returned no PNG data.")

            old_max_pixels = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = None
            try:
                with Image.open(io.BytesIO(png)) as image:
                    if image.size != (width, render_h):
                        raise KfpsRenderError(
                            "High-resolution strip renderer returned "
                            f"{image.size[0]}x{image.size[1]}, expected {width}x{render_h}."
                        )
                    if image.mode != "RGBA":
                        image = image.convert("RGBA")
                    image.load()
                    crop_top = output_y0 - render_y0
                    crop_bottom = crop_top + (output_y1 - output_y0)
                    if crop_top or crop_bottom != render_h:
                        image = image.crop((0, crop_top, width, crop_bottom))
                    writer.write_rgba_rows(
                        image.tobytes(),
                        output_y1 - output_y0,
                    )
            finally:
                Image.MAX_IMAGE_PIXELS = old_max_pixels


def _write_large_transparent_section(path: Path, width: int, height: int) -> None:
    """Create an arbitrarily large transparent RGBA PNG with bounded memory."""
    with _RgbaPngStreamWriter(path, int(width), int(height)) as writer:
        writer.write_transparent_rows(int(height))


def render_clivery_sections(
    source: str | Path,
    *,
    game_folder: str | Path | None = None,
    resolution: str | LiveryResolution | None = None,
    output_root: str | Path | None = None,
    log: Callable[[str], None] | None = None,
) -> RenderResult:
    source_path = Path(source)
    if not source_path.is_file():
        raise KfpsRenderError("C_livery file does not exist.")
    try:
        render_resolution = resolve_livery_resolution(resolution)
    except ValueError as exc:
        raise KfpsRenderError(str(exc)) from exc
    canvas_w, canvas_h = render_resolution.canvas_size
    if log:
        log("M6.23 stage 1/4: preparing pinned renderer runtime")
    root = ensure_runtime(log)
    if log:
        log("M6.23 stage 2/4: importing renderer backend")
    decoder, renderer, raster_backend = _load_backend(root)
    try:
        if log:
            log("M6.23 stage 3/4: decoding C_livery layers")
        payload = decoder.unwrap_forza_container(source_path)
        if len(payload) < 0x1A or payload[:4] != b"vlrc":
            raise KfpsRenderError("The selected source is not an FH6 C_livery payload.")
        layers, report = decoder.clivery_to_layers(payload)
        standard_layers = layers
        standard_report = report
        standard_warnings = list((report or {}).get("warnings") or [])
        standard_has_count_mismatch = any("stats target" in str(w) for w in standard_warnings)
        standard_has_raster = any(layer.get("is_raster_logo") for layer in layers)
        if standard_has_raster and standard_has_count_mismatch:
            if log:
                log(
                    "Raster/logo + stats-count mismatch detected; switching to "
                    "boundary-aware physical section decode."
                )
            boundary_layers, boundary_report = _decode_livery_sections_boundary_aware(decoder, payload)
            if len(boundary_layers) >= len(standard_layers):
                layers, report = boundary_layers, boundary_report
                if log:
                    log(
                        f"Boundary-aware decode: {len(boundary_layers)} physical layer(s); "
                        f"counter-driven decode: {len(standard_layers)} layer(s)."
                    )
            else:
                layers, report = standard_layers, standard_report
                if log:
                    log(
                        "Boundary-aware decode did not improve physical coverage; "
                        "retaining counter-driven decoder result."
                    )
        json_layers, identity_warnings = decoder.layers_to_kfps_json_layers(layers, game="fh6")
    except KfpsRenderError:
        raise
    except Exception as exc:
        raise KfpsRenderError(f"KFPS C_livery decode failed: {exc}") from exc

    car_id = int.from_bytes(payload[0x10:0x14], "little")
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()[:16]
    if output_root is None:
        raise KfpsRenderError("A transient output_root is required for FH6 Assistant 3D rendering.")
    out_dir = Path(output_root) / f"car_{car_id}" / f"{digest}_{render_resolution.key}"
    out_dir.mkdir(parents=True, exist_ok=True)

    decoded_layer_count = len(json_layers)
    (
        render_layers,
        raster_resolver,
        raster_ids,
        skipped_raster_ids,
        skipped_raster_layer_count,
    ) = _prepare_raster_layers(json_layers, raster_backend, game_folder, log)
    by_section = _section_layers(render_layers)
    if log:
        log(f"M6.24B decoded {decoded_layer_count} layers; {len(render_layers)} renderable after raster-resource filtering; stage 4/4: rendering 11 sections at {canvas_w}x{canvas_h}")
    png_paths: dict[str, Path] = {}
    section_counts: dict[str, int] = {}
    use_streamed_large_canvas = canvas_w > 8192 or canvas_h > 8192
    for section in SECTION_NAMES:
        current = by_section[section]
        section_counts[section] = len(current)
        started = time.monotonic()
        path = out_dir / f"{section}.png"
        if log:
            mode = "streamed strips" if use_streamed_large_canvas else "single canvas"
            log(
                f"Rendering {section}: {len(current)} decoded layers "
                f"({canvas_w}x{canvas_h}, {mode})"
            )

        if use_streamed_large_canvas:
            try:
                if current:
                    _render_large_section_streamed(
                        renderer,
                        current,
                        path,
                        width=canvas_w,
                        height=canvas_h,
                        raster_resolver=raster_resolver,
                        log=log,
                    )
                else:
                    _write_large_transparent_section(path, canvas_w, canvas_h)
            except KfpsRenderError:
                raise
            except Exception as exc:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise KfpsRenderError(
                    f"Could not stream-render {section} at {canvas_w}x{canvas_h}: {exc}"
                ) from exc
        else:
            if current:
                try:
                    png = renderer.render_typecode_layers_canvas(
                        current,
                        width=canvas_w,
                        height=canvas_h,
                        transparent_background=True,
                        strict_assets=True,
                        raster_resolver=raster_resolver,
                    )
                except TypeError:
                    # Older pinned signatures do not expose transparent_background.
                    png = renderer.render_typecode_layers_canvas(
                        current,
                        width=canvas_w,
                        height=canvas_h,
                        strict_assets=True,
                        raster_resolver=raster_resolver,
                    )
                except Exception as exc:
                    raise KfpsRenderError(f"Could not render {section}: {exc}") from exc
                if not png:
                    raise KfpsRenderError(f"The {section} renderer returned no PNG data.")
            else:
                buffer = io.BytesIO()
                Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0)).save(
                    buffer, format="PNG"
                )
                png = buffer.getvalue()
            path.write_bytes(png)

        try:
            # All section files here are generated locally by the pinned renderer
            # or the bounded-memory transparent PNG writer.
            old_max_pixels = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = None
            try:
                with Image.open(path) as image:
                    if image.size != (canvas_w, canvas_h):
                        raise KfpsRenderError(
                            f"{section} output is {image.size[0]}x{image.size[1]}, "
                            f"expected {canvas_w}x{canvas_h}."
                        )
                    image.verify()
            finally:
                Image.MAX_IMAGE_PIXELS = old_max_pixels
        except KfpsRenderError:
            raise
        except Exception as exc:
            raise KfpsRenderError(f"{section} output PNG is unreadable: {exc}") from exc

        png_paths[section] = path
        if log:
            try:
                disk_size = path.stat().st_size
            except OSError:
                disk_size = 0
            log(
                f"Rendered {section} in {time.monotonic() - started:.1f}s "
                f"-> {path.name} ({disk_size / 1048576:.1f} MiB PNG)"
            )

    warnings = list((report or {}).get("warnings") or [])
    warnings.extend(identity_warnings or [])
    return RenderResult(
        source_path=source_path,
        output_dir=out_dir,
        car_id=car_id,
        layer_count=decoded_layer_count,
        section_counts=section_counts,
        png_paths=png_paths,
        decoder_warnings=warnings,
        canvas_size=(canvas_w, canvas_h),
        resolution_name=render_resolution.key,
        raster_ids=tuple(raster_ids),
        raster_skipped_ids=tuple(skipped_raster_ids),
        raster_skipped_layer_count=int(skipped_raster_layer_count),
    )
