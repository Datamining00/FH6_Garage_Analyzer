from __future__ import annotations
from contextlib import contextmanager
import importlib
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image
from .kfps_runtime import ensure_runtime
from .vehicle_assets import VehicleAsset as IndexedVehicleAsset
from .livery_resolution import NATIVE_CANVAS_SIZE, resolve_livery_resolution
SECTION_NAMES = ['Front', 'Back', 'Top', 'Left', 'Right', 'Spoiler', 'FrontWindshield', 'BackWindshield', 'TopWindow', 'LeftWindow', 'RightWindow']

class DirectLiveryError(RuntimeError):
    pass

@dataclass(frozen=True)
class DirectLiveryTextures:
    car_id: int
    paint: np.ndarray
    mask_pages: np.ndarray
    source_regions: np.ndarray
    paint_regions: np.ndarray
    projection_axes: np.ndarray
    projection_mask_regions: np.ndarray
    section_facings: np.ndarray
    valid_slots: tuple[bool, ...]
    source_names: tuple[str, ...]
    visible_pixels: tuple[int, ...]
    paint_size: tuple[int, int]
    canvas_size: tuple[int, int] = NATIVE_CANVAS_SIZE
    resolution_name: str = 'normal'

def _load_contract_backend():
    root = ensure_runtime()
    root_str = str(root)
    import sys
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        vehicle_assets = importlib.import_module('tools.livery.vehicle_assets')
        render_contract = importlib.import_module('tools.livery.render_contract')
    except Exception as exc:
        raise DirectLiveryError(f'Could not import pinned KFPS projection backend: {exc}') from exc
    return (vehicle_assets, render_contract)

def _archive_masks_exact(archive: Path, contract) -> dict[str, tuple[Image.Image, dict, str]]:
    try:
        with zipfile.ZipFile(archive) as bundle:
            available = {name.casefold(): name for name in bundle.namelist()}
            xml_name = available.get('liverymasks/masks.xml')
            if not xml_name:
                raise DirectLiveryError(f'{archive.name} has no LiveryMasks/Masks.xml.')
            root = ET.fromstring(bundle.read(xml_name))
            projections = {element.tag.casefold(): dict(element.attrib) for element in root if element.attrib.get('valid', 'false').casefold() == 'true'}
            result = {}
            for slot in sorted(set(contract.SECTION_TO_SLOT.values())):
                source_name = available.get(f'liverymasks/{slot}.swatchbin')
                projection = projections.get(str(slot).casefold())
                if not source_name or projection is None:
                    continue
                data = bundle.read(source_name)
                texture = contract._parse_pc_texture_bundle(data)
                if int(texture['encoding']) != int(contract.UNSIGNED_BC4):
                    raise DirectLiveryError(f'{source_name} is not an unsigned BC4 livery mask.')
                width, height = (int(texture['width']), int(texture['height']))
                start = int(texture['payload_offset'])
                size = int(texture['payload_size'])
                values = contract._decode_unsigned_bc4(data[start:start + size], width, height)
                if tuple(values.shape) != (height, width):
                    raise DirectLiveryError(f'{source_name} decoded to {tuple(values.shape)}; header declares {(height, width)}.')
                result[slot] = (Image.fromarray(np.asarray(values, dtype=np.uint8), mode='L'), projection, source_name)
            return result
    except DirectLiveryError:
        raise
    except Exception as exc:
        raise DirectLiveryError(f'Could not decode exact read-only vehicle mask atlas: {exc}') from exc

@contextmanager
def _open_trusted_render(path: Path):
    old_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None
    image = None
    try:
        image = Image.open(path)
        yield image
    finally:
        if image is not None:
            image.close()
        Image.MAX_IMAGE_PIXELS = old_max_pixels

def _scaled_warped_uv_layer(artwork: Image.Image, slot: str, projection: dict, *, scale: int, contract) -> Image.Image:
    if scale == 1:
        return contract._warped_uv_layer(artwork, slot, projection)
    target_w = NATIVE_CANVAS_SIZE[0] * scale
    target_h = NATIVE_CANVAS_SIZE[1] * scale
    if artwork.size != (target_w, target_h):
        raise DirectLiveryError(f'{slot} high-resolution artwork is {artwork.size}; expected {(target_w, target_h)}.')
    try:
        flip_x_slots = {str(v).casefold() for v in contract.FLIP_X_SLOTS}
        flip_y_slots = {str(v).casefold() for v in contract.FLIP_Y_SLOTS}
        transposed_slots = {str(v).casefold() for v in contract.TRANSPOSED_SLOTS}
    except Exception as exc:
        raise DirectLiveryError('Pinned KFPS render contract does not expose the audited slot-orientation sets.') from exc
    slot_key = str(slot).casefold()
    flip_x = -1.0 if slot_key in flip_x_slots else 1.0
    flip_y = -1.0 if slot_key in flip_y_slots else 1.0
    center_x = target_w / 2.0
    center_y = target_h / 2.0
    x_origin = float(projection.get('xorigin', 0.0)) * scale
    y_origin = float(projection.get('yorigin', 0.0)) * scale
    if slot_key in transposed_slots:
        affine = (0.0, -flip_x, center_x + flip_x * (center_y - y_origin), -flip_y, 0.0, center_y + flip_y * (center_x + x_origin))
    else:
        affine = (flip_x, 0.0, center_x - flip_x * (center_x + x_origin), 0.0, flip_y, center_y - flip_y * (center_y - y_origin))
    return artwork.convert('RGBA').transform((target_w, target_h), Image.Transform.AFFINE, affine, resample=Image.Resampling.BILINEAR, fillcolor=(0, 0, 0, 0))

def _scaled_warped_uv_tile(artwork: Image.Image, slot: str, projection: dict, source_bounds: tuple[int, int, int, int], *, scale: int, contract) -> Image.Image:
    left, top, right, bottom = (int(v) for v in source_bounds)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise DirectLiveryError(f'{slot} produced an empty projection rectangle {source_bounds}.')
    if scale == 1:
        return contract._warped_uv_layer(artwork, slot, projection).crop(source_bounds)
    target_w = NATIVE_CANVAS_SIZE[0] * scale
    target_h = NATIVE_CANVAS_SIZE[1] * scale
    if artwork.size != (target_w, target_h):
        raise DirectLiveryError(f'{slot} high-resolution artwork is {artwork.size}; expected {(target_w, target_h)}.')
    try:
        flip_x_slots = {str(v).casefold() for v in contract.FLIP_X_SLOTS}
        flip_y_slots = {str(v).casefold() for v in contract.FLIP_Y_SLOTS}
        transposed_slots = {str(v).casefold() for v in contract.TRANSPOSED_SLOTS}
    except Exception as exc:
        raise DirectLiveryError('Pinned KFPS render contract does not expose the audited slot-orientation sets.') from exc
    slot_key = str(slot).casefold()
    flip_x = -1.0 if slot_key in flip_x_slots else 1.0
    flip_y = -1.0 if slot_key in flip_y_slots else 1.0
    center_x = target_w / 2.0
    center_y = target_h / 2.0
    x_origin = float(projection.get('xorigin', 0.0)) * scale
    y_origin = float(projection.get('yorigin', 0.0)) * scale
    if slot_key in transposed_slots:
        affine = (0.0, -flip_x, center_x + flip_x * (center_y - y_origin), -flip_y, 0.0, center_y + flip_y * (center_x + x_origin))
    else:
        affine = (flip_x, 0.0, center_x - flip_x * (center_x + x_origin), 0.0, flip_y, center_y - flip_y * (center_y - y_origin))
    a, b, c, d, e, f = affine
    local_affine = (a, b, a * left + b * top + c, d, e, d * left + e * top + f)
    fillcolor = (0, 0, 0, 0) if artwork.mode == 'RGBA' else 0
    tile = artwork.transform((width, height), Image.Transform.AFFINE, local_affine, resample=Image.Resampling.BILINEAR, fillcolor=fillcolor)
    if tile.mode != 'RGBA':
        tile = tile.convert('RGBA')
    return tile

def _pack_paint_tiles_scaled(tiles: list[dict], *, scale: int, contract) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    if scale == 1:
        return contract._pack_paint_tiles(tiles)
    atlas_width = int(contract.PAINT_ATLAS_WIDTH) * scale
    padding = int(contract.PAINT_PADDING) * scale
    ordered = sorted(tiles, key=lambda item: (-int(item['image'].height), -int(item['image'].width), int(item['slot_index'])))
    placements: dict[str, tuple[int, int, int, int]] = {}
    x = padding
    y = padding
    row_height = 0
    max_bottom = padding
    for item in ordered:
        image: Image.Image = item['image']
        if image.width + padding * 2 > atlas_width:
            raise DirectLiveryError(f"The {item['section']} high-resolution paint region is too wide for the {atlas_width}px local texture atlas.")
        if x + image.width + padding > atlas_width:
            x = padding
            y += row_height + padding * 2
            row_height = 0
        placements[item['section']] = (x, y, image.width, image.height)
        x += image.width + padding * 2
        row_height = max(row_height, image.height)
        max_bottom = max(max_bottom, y + image.height + padding)
    height = max(1, max_bottom)
    max_height = 8192 * scale
    if height > max_height:
        raise DirectLiveryError(f'The high-resolution local section paint atlas would be {atlas_width} x {height} pixels; maximum is {max_height}px high.')
    atlas = Image.new('RGBA', (atlas_width, height), (0, 0, 0, 0))
    for item in ordered:
        left, top, _, _ = placements[item['section']]
        atlas.alpha_composite(item['image'], (left, top))
    return (atlas, placements)

def _scaled_bounds(native_bounds: tuple[int, int, int, int], scale: int) -> tuple[int, int, int, int]:
    return tuple((int(v) * int(scale) for v in native_bounds))

def build_direct_livery_textures(render_result, asset: IndexedVehicleAsset) -> DirectLiveryTextures:
    if int(render_result.car_id) != int(asset.car_id):
        raise DirectLiveryError(f'C_livery targets Car ID {render_result.car_id}, but the selected vehicle is Car ID {asset.car_id}.')
    archive = Path(asset.archive_path)
    if not archive.is_file():
        raise DirectLiveryError('Selected vehicle archive no longer exists.')
    try:
        render_resolution = resolve_livery_resolution(getattr(render_result, 'resolution_name', 'normal'))
    except ValueError as exc:
        raise DirectLiveryError(str(exc)) from exc
    expected_canvas = tuple((int(v) for v in getattr(render_result, 'canvas_size', NATIVE_CANVAS_SIZE)))
    if expected_canvas != render_resolution.canvas_size:
        raise DirectLiveryError(f'Render result canvas {expected_canvas} does not match resolution {render_resolution.label}.')
    scale = int(render_resolution.scale)
    vehicle_assets, contract = _load_contract_backend()
    stat = archive.stat()
    runtime_asset = vehicle_assets.VehicleAsset(car_id=int(asset.car_id), model_code=str(asset.model_code), archive_path=str(archive), archive_name=archive.name, archive_size=int(stat.st_size), archive_mtime_ns=int(stat.st_mtime_ns), clip_entry='')
    masks = _archive_masks_exact(archive, contract)
    atlas_w, atlas_h = (int(contract.ATLAS_SIZE[0]), int(contract.ATLAS_SIZE[1]))
    if (atlas_w, atlas_h) != NATIVE_CANVAS_SIZE:
        raise DirectLiveryError(f'Pinned KFPS native atlas changed to {(atlas_w, atlas_h)}; M6.23B scaling was audited for {NATIVE_CANVAS_SIZE}.')
    target_w, target_h = render_resolution.canvas_size
    page_count = int(contract.MASK_PAGE_COUNT)
    channels = int(contract.MASK_CHANNELS)
    mask_pages = [np.zeros((atlas_h, atlas_w, channels), dtype=np.uint8) for _ in range(page_count)]
    paint_tiles: list[dict] = []
    pending: list[dict] = []
    valid = [False] * len(SECTION_NAMES)
    sources = [''] * len(SECTION_NAMES)
    visible_pixels = [0] * len(SECTION_NAMES)
    section_to_slot = dict(contract.SECTION_TO_SLOT)
    projection_axes = np.zeros((len(SECTION_NAMES), 4), dtype=np.float32)
    projection_mask_regions = np.zeros((len(SECTION_NAMES), 4), dtype=np.float32)
    section_facings = np.zeros((len(SECTION_NAMES), 3), dtype=np.float32)
    for facing_index, facing_name in enumerate(SECTION_NAMES):
        try:
            section_facings[facing_index] = np.asarray(contract.SECTION_FACING[facing_name], dtype=np.float32)
        except Exception as exc:
            raise DirectLiveryError(f'Pinned KFPS render contract has no valid facing for {facing_name}: {exc}') from exc
    for index, section in enumerate(SECTION_NAMES):
        slot = section_to_slot.get(section)
        item = masks.get(slot) if slot else None
        png_path = Path(render_result.png_paths.get(section, ''))
        if item is None or not png_path.is_file():
            continue
        mask, projection, source_name = item
        if mask.size != (atlas_w, atlas_h):
            raise DirectLiveryError(f'{section} vehicle mask is {mask.size}; expected {(atlas_w, atlas_h)}.')
        mask_values = np.asarray(mask.convert('L'), dtype=np.uint8)
        page = index // channels
        channel = index % channels
        mask_pages[page][..., channel] = mask_values
        sources[index] = str(source_name)
        if mask.getbbox() is None:
            continue
        try:
            native_source_bounds = tuple((int(v) for v in contract._projection_pixel_bounds(projection)))
            source_bounds = _scaled_bounds(native_source_bounds, scale)
            axis_x, axis_x_scale = contract._projection_axis(projection, 'xAxis', 'xScale')
            axis_y, axis_y_scale = contract._projection_axis(projection, 'yAxis', 'yScale')
            projection_axes[index] = (float(axis_x), float(axis_y), float(axis_x_scale), float(axis_y_scale))
            projection_mask_regions[index] = np.asarray(contract._projection_mask_region(projection), dtype=np.float32)
            with _open_trusted_render(png_path) as artwork:
                if artwork.size != (target_w, target_h):
                    raise DirectLiveryError(f'{section} artwork is {artwork.size}; expected {(target_w, target_h)}.')
                tile = _scaled_warped_uv_tile(artwork, slot, projection, source_bounds, scale=scale, contract=contract)
        except DirectLiveryError:
            raise
        except Exception as exc:
            raise DirectLiveryError(f'Could not build the exact KFPS paint tile for {section}: {exc}') from exc
        if tile.width <= 0 or tile.height <= 0:
            raise DirectLiveryError(f'{section} produced an empty projection rectangle {source_bounds}.')
        alpha = np.asarray(tile.getchannel('A'), dtype=np.uint8)
        native_mask_crop = mask_values[native_source_bounds[1]:native_source_bounds[3], native_source_bounds[0]:native_source_bounds[2]]
        if scale == 1:
            mask_crop = native_mask_crop
        else:
            mask_crop = np.asarray(Image.fromarray(native_mask_crop, mode='L').resize((tile.width, tile.height), Image.Resampling.NEAREST), dtype=np.uint8)
        visible = int(np.count_nonzero((alpha > 0) & (mask_crop > 0)))
        visible_pixels[index] = visible
        valid[index] = True
        paint_tiles.append({'section': section, 'slot_index': index, 'image': tile})
        pending.append({'section': section, 'slot_index': index, 'source_bounds': source_bounds})
    if not paint_tiles:
        raise DirectLiveryError('The rendered livery and selected vehicle have no shared direct-UV paint sections.')
    try:
        paint_atlas, placements = _pack_paint_tiles_scaled(paint_tiles, scale=scale, contract=contract)
    except Exception as exc:
        raise DirectLiveryError(f'Could not pack the exact KFPS section paint atlas: {exc}') from exc
    source_regions = np.zeros((11, 4), dtype=np.float32)
    paint_regions = np.zeros((11, 4), dtype=np.float32)
    for record in pending:
        index = int(record['slot_index'])
        left, top, right, bottom = record['source_bounds']
        px, py, width, height = placements[record['section']]
        source_regions[index] = (left / target_w, top / target_h, right / target_w, bottom / target_h)
        paint_regions[index] = (px / paint_atlas.width, py / paint_atlas.height, (px + width) / paint_atlas.width, (py + height) / paint_atlas.height)
    paint = np.ascontiguousarray(np.asarray(paint_atlas.convert('RGBA'), dtype=np.uint8))
    pages = np.ascontiguousarray(np.stack(mask_pages, axis=0), dtype=np.uint8)
    return DirectLiveryTextures(car_id=int(asset.car_id), paint=paint, mask_pages=pages, source_regions=np.ascontiguousarray(source_regions), paint_regions=np.ascontiguousarray(paint_regions), projection_axes=np.ascontiguousarray(projection_axes), projection_mask_regions=np.ascontiguousarray(projection_mask_regions), section_facings=np.ascontiguousarray(section_facings), valid_slots=tuple(valid), source_names=tuple(sources), visible_pixels=tuple(visible_pixels), paint_size=(int(paint_atlas.width), int(paint_atlas.height)), canvas_size=(target_w, target_h), resolution_name=render_resolution.key)
