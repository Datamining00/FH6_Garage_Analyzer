from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .exact_livery_preview import ExactLiveryPreviewError, raster_resolver_for_game, require_fh6_game_folder
from .livery_analysis import LiveryAnalysisError
from .livery_preview import (
    KFPS_VENDOR_COMMIT,
    LiveryPreviewError,
    RenderedLiverySection,
    _analysis_cached,
    _decode_cached,
    _file_signature,
    _load_backend,
    _validate_exact_assets_and_filter_noops,
)
from .livery_preview_preview2 import (
    QUALITY_DIMENSIONS,
    _checkerboard_preview,
    _projection_supersampled,
    normalize_quality,
)

WEB_CANVAS_CACHE_VERSION = "v14-web-canvas-r1"
WEB_CANVAS_TIMEOUT_SECONDS = 120.0
WEB_CANVAS_MAX_POST_BYTES = 128 * 1024 * 1024
_CACHE_LOCK = threading.RLock()


@dataclass(frozen=True, slots=True)
class _WebScene:
    payload: dict[str, Any]
    images: dict[str, bytes]
    vector_layers: int
    fallback_layers: int


def _app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FH6GarageAnalyzer"
    return Path.home() / ".fh6garage"


def _disk_cache_dir() -> Path:
    return _app_data_dir() / "livery_preview_cache" / WEB_CANVAS_CACHE_VERSION


def _cache_key(path_text: str, file_size: int, mtime_ns: int, section: str, game_folder_text: str, quality: str) -> str:
    text = "|".join((
        WEB_CANVAS_CACHE_VERSION,
        KFPS_VENDOR_COMMIT,
        str(Path(path_text).resolve()),
        str(int(file_size)),
        str(int(mtime_ns)),
        str(section),
        str(Path(game_folder_text).resolve()),
        normalize_quality(quality),
    ))
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def _cache_path(*args) -> Path:
    return _disk_cache_dir() / f"{_cache_key(*args)}.png"


def _read_disk_cache(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def _write_disk_cache(path: Path, data: bytes) -> None:
    temporary = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(data)
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def clear_web_canvas_cache() -> None:
    with _CACHE_LOCK:
        _render_cached.cache_clear()
    root = _disk_cache_dir()
    try:
        for item in root.glob("*.png"):
            item.unlink(missing_ok=True)
    except OSError:
        pass


def find_edge_executable() -> Path | None:
    """Locate the system Edge binary without adding a browser to the EXE."""
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        value = os.environ.get(env_name)
        if not value:
            continue
        candidate = Path(value) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            pass
    return None


def web_canvas_runtime_available() -> bool:
    return find_edge_executable() is not None


def _path_from_alpha_triangles(alpha_triangles) -> str:
    chunks: list[str] = []
    for points, _values in alpha_triangles:
        if len(points) != 3:
            continue
        try:
            p0, p1, p2 = points
            chunks.append(
                "M {:.9g} {:.9g} L {:.9g} {:.9g} L {:.9g} {:.9g} Z".format(
                    float(p0[0]), float(p0[1]),
                    float(p1[0]), float(p1[1]),
                    float(p2[0]), float(p2[1]),
                )
            )
        except (TypeError, ValueError, IndexError):
            continue
    return " ".join(chunks)


def _canvas_matrix(renderer, data: list[Any], scale: float) -> list[float]:
    """Derive Canvas2D's affine from the pinned KFPS placement transform."""
    transform = getattr(renderer, "_transform_resource_polygon", None)
    if not callable(transform):
        raise LiveryPreviewError("KFPS placement transform helper is unavailable.")
    basis = transform([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)], data)
    if len(basis) != 3:
        raise LiveryPreviewError("KFPS placement transform returned an invalid basis.")

    def to_canvas(point) -> tuple[float, float]:
        return ((float(point[0]) + 1024.0) * float(scale), (512.0 - float(point[1])) * float(scale))

    origin = to_canvas(basis[0])
    axis_x = to_canvas(basis[1])
    axis_y = to_canvas(basis[2])
    return [
        axis_x[0] - origin[0], axis_x[1] - origin[1],
        axis_y[0] - origin[0], axis_y[1] - origin[1],
        origin[0], origin[1],
    ]


def _clone_as_visible_layer(layer: dict[str, Any]) -> dict[str, Any]:
    clone = dict(layer)
    clone["mask"] = False
    clone["is_mask"] = False
    clone["isMask"] = False
    data = list(clone.get("data") or [])
    if len(data) > 6:
        data[6] = 0
    clone["data"] = data
    return clone


def _single_layer_png(renderer, layer: dict[str, Any], *, width: int, height: int, raster_resolver) -> bytes:
    """Keep gradient/raster special cases on the validated KFPS path for the A/B test."""
    visible = _clone_as_visible_layer(layer)
    try:
        result = renderer.render_typecode_layers_canvas(
            [visible], width=width, height=height,
            raster_resolver=raster_resolver, strict_assets=False,
        )
    except Exception as exc:
        raise LiveryPreviewError(f"Web Canvas fallback layer generation failed: {exc}") from exc
    if result:
        return result
    from PIL import Image
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def _build_web_scene(renderer, layers: list[dict[str, Any]], *, width: int, height: int, scale: float, raster_resolver) -> _WebScene:
    resolve_resource = getattr(renderer, "_resolve_vinyl_resource", None)
    alpha_triangles_for = getattr(renderer, "_resource_alpha_triangles", None)
    color_tuple = getattr(renderer, "_color_tuple", None)
    if not callable(resolve_resource) or not callable(alpha_triangles_for) or not callable(color_tuple):
        raise LiveryPreviewError("KFPS native-resource helpers are unavailable for Web Canvas A/B rendering.")

    resources: dict[str, str] = {}
    commands: list[dict[str, Any]] = []
    images: dict[str, bytes] = {}
    vector_layers = 0
    fallback_layers = 0

    for layer_index, layer in enumerate(layers, 1):
        data = list(layer.get("data") or [])
        if len(data) < 4:
            continue
        is_mask = bool(layer.get("mask") or layer.get("is_mask") or layer.get("isMask"))
        color = color_tuple(layer.get("color")) or (255, 255, 255, 255)

        if not bool(layer.get("is_raster_logo")):
            try:
                type_code = int(layer.get("type", 0))
            except (TypeError, ValueError):
                type_code = 0
            resource = resolve_resource(type_code, layer)
            alpha_triangles = alpha_triangles_for(*resource) if resource else None
            opaque_native = bool(alpha_triangles) and all(
                int(value) == 255 for _points, values in alpha_triangles for value in values
            )
            if resource and alpha_triangles and opaque_native:
                resource_key = f"{resource[0]}/{int(resource[1])}"
                if resource_key not in resources:
                    path_text = _path_from_alpha_triangles(alpha_triangles)
                    if not path_text:
                        raise LiveryPreviewError(f"layer {layer_index} has no usable Web Canvas path for {resource_key}.")
                    resources[resource_key] = path_text
                commands.append({
                    "kind": "path",
                    "resource": resource_key,
                    "matrix": _canvas_matrix(renderer, data, scale),
                    "color": [int(color[0]), int(color[1]), int(color[2]), int(color[3])],
                    "mask": is_mask,
                })
                vector_layers += 1
                continue

        # Variable native vertex-alpha and raster logos remain on the same KFPS
        # raster path. That makes ordinary vector/text rasterization the controlled
        # A/B variable instead of silently changing gradient or decal semantics.
        image_name = f"layer-{layer_index:05d}.png"
        images[image_name] = _single_layer_png(
            renderer, layer, width=width, height=height, raster_resolver=raster_resolver
        )
        commands.append({"kind": "image", "url": image_name, "mask": is_mask})
        fallback_layers += 1

    return _WebScene(
        payload={"width": int(width), "height": int(height), "resources": resources, "commands": commands},
        images=images,
        vector_layers=vector_layers,
        fallback_layers=fallback_layers,
    )


_WEB_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><title>FH6 Web Canvas Renderer</title>
<style>html,body{margin:0;padding:0;background:transparent;overflow:hidden}canvas{display:block}</style></head>
<body><canvas id="canvas"></canvas><script>
(async () => {
  const root = location.pathname.replace(/index\.html$/, '');
  const scene = await fetch(root + 'scene.json', {cache:'no-store'}).then(r => { if (!r.ok) throw new Error('scene '+r.status); return r.json(); });
  const canvas = document.getElementById('canvas'); canvas.width = scene.width; canvas.height = scene.height;
  const ctx = canvas.getContext('2d', {alpha:true, desynchronized:false}); if (!ctx) throw new Error('Canvas2D unavailable');
  ctx.clearRect(0,0,canvas.width,canvas.height); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  const paths = new Map(); for (const [key,d] of Object.entries(scene.resources || {})) paths.set(key, new Path2D(d));
  const images = new Map();
  async function loadImage(name) {
    if (images.has(name)) return images.get(name);
    const promise = new Promise((resolve,reject) => { const image = new Image(); image.onload=()=>resolve(image); image.onerror=()=>reject(new Error('image load failed: '+name)); image.src=root+'layer/'+encodeURIComponent(name); });
    images.set(name,promise); return promise;
  }
  await Promise.all((scene.commands||[]).filter(c=>c.kind==='image').map(c=>loadImage(c.url)));
  for (const cmd of (scene.commands||[])) {
    ctx.save(); ctx.globalCompositeOperation = cmd.mask ? 'destination-out' : 'source-over';
    if (cmd.kind === 'path') {
      const m=cmd.matrix, color=cmd.color||[255,255,255,255]; ctx.setTransform(m[0],m[1],m[2],m[3],m[4],m[5]);
      ctx.globalAlpha = cmd.mask ? 1 : Math.max(0,Math.min(1,Number(color[3])/255)); ctx.fillStyle=`rgb(${color[0]},${color[1]},${color[2]})`; ctx.fill(paths.get(cmd.resource));
    } else if (cmd.kind === 'image') {
      ctx.setTransform(1,0,0,1,0,0); ctx.globalAlpha=1; ctx.drawImage(await loadImage(cmd.url),0,0,canvas.width,canvas.height);
    }
    ctx.restore();
  }
  ctx.setTransform(1,0,0,1,0,0); ctx.globalCompositeOperation='source-over'; ctx.globalAlpha=1;
  const blob = await new Promise((resolve,reject)=>canvas.toBlob(v=>v?resolve(v):reject(new Error('canvas.toBlob returned null')),'image/png'));
  const response = await fetch(root+'complete',{method:'POST',body:blob,headers:{'Content-Type':'image/png'}}); if (!response.ok) throw new Error('complete '+response.status);
  document.title='FH6_WEB_CANVAS_DONE';
})().catch(async error => { try { const root=location.pathname.replace(/index\.html$/,''); await fetch(root+'error',{method:'POST',body:String(error&&error.stack||error)}); } catch (_) {} document.title='FH6_WEB_CANVAS_ERROR'; });
</script></body></html>'''


class _SceneServer:
    def __init__(self, scene: _WebScene):
        self.scene = scene
        self.token = secrets.token_urlsafe(24)
        self.done = threading.Event()
        self.png: bytes | None = None
        self.error: str | None = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "FH6WebCanvas/1"
            def log_message(self, _format, *_args):
                return
            def _route(self) -> str | None:
                path = urlparse(self.path).path
                prefix = f"/{owner.token}/"
                return path[len(prefix):] if path.startswith(prefix) else None
            def _send(self, status: int, content_type: str, payload: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if payload:
                    self.wfile.write(payload)
            def do_GET(self):
                route = self._route()
                if route is None:
                    return self._send(404, "text/plain", b"not found")
                if route in ("", "index.html"):
                    return self._send(200, "text/html; charset=utf-8", _WEB_HTML.encode("utf-8"))
                if route == "scene.json":
                    data = json.dumps(owner.scene.payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
                    return self._send(200, "application/json", data)
                if route.startswith("layer/"):
                    name = unquote(route[len("layer/"):])
                    if "/" in name or "\\" in name or name not in owner.scene.images:
                        return self._send(404, "text/plain", b"not found")
                    return self._send(200, "image/png", owner.scene.images[name])
                return self._send(404, "text/plain", b"not found")
            def do_POST(self):
                route = self._route()
                if route not in ("complete", "error"):
                    return self._send(404, "text/plain", b"not found")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length < 0 or length > WEB_CANVAS_MAX_POST_BYTES:
                    return self._send(413, "text/plain", b"too large")
                payload = self.rfile.read(length)
                if route == "complete":
                    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
                        owner.png = payload
                    else:
                        owner.error = "Web Canvas returned a non-PNG payload."
                else:
                    owner.error = payload.decode("utf-8", errors="replace")[:8000]
                owner.done.set()
                self._send(204, "text/plain", b"")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="fh6-web-canvas-http")

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}/{self.token}/index.html"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2.0)


def _render_scene_in_edge(scene: _WebScene, *, timeout: float = WEB_CANVAS_TIMEOUT_SECONDS) -> bytes:
    edge = find_edge_executable()
    if edge is None:
        raise LiveryPreviewError("Web Canvas A/B 렌더러에는 Microsoft Edge가 필요합니다. Windows의 Edge 설치를 확인해 주세요.")

    with tempfile.TemporaryDirectory(prefix="fh6-web-canvas-") as temp, _SceneServer(scene) as server:
        profile = Path(temp) / "edge-profile"
        command = [
            str(edge), "--headless=new", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-background-networking", "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding", "--disable-sync", "--metrics-recording-only",
            f"--user-data-dir={profile}", "--window-size=800,600", server.url,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=creationflags, text=True)
        except OSError as exc:
            raise LiveryPreviewError(f"Microsoft Edge Web Canvas 프로세스를 시작하지 못했습니다: {exc}") from exc
        deadline = time.monotonic() + float(timeout)
        try:
            while not server.done.wait(0.05):
                if process.poll() is not None:
                    stderr = process.stderr.read() if process.stderr is not None else ""
                    raise LiveryPreviewError("Microsoft Edge Web Canvas 렌더러가 결과를 반환하기 전에 종료되었습니다. " + stderr.strip()[-1200:])
                if time.monotonic() >= deadline:
                    raise LiveryPreviewError(f"Web Canvas 렌더링이 {float(timeout):.0f}초 제한 시간을 초과했습니다.")
            if server.error:
                raise LiveryPreviewError(f"Web Canvas JavaScript 오류: {server.error}")
            if not server.png:
                raise LiveryPreviewError("Web Canvas 렌더러가 PNG 결과를 반환하지 않았습니다.")
            return server.png
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
            if process.stderr is not None:
                process.stderr.close()


def web_canvas_smoke_test() -> tuple[int, int]:
    scene = _WebScene(
        payload={
            "width": 128, "height": 64,
            "resources": {"triangle": "M 0 0 L 30 0 L 0 30 Z"},
            "commands": [{"kind": "path", "resource": "triangle", "matrix": [1,0,0,1,20,20], "color": [255,0,0,255], "mask": False}],
        },
        images={}, vector_layers=1, fallback_layers=0,
    )
    png = _render_scene_in_edge(scene, timeout=30.0)
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        if image.size != (128, 64):
            raise LiveryPreviewError(f"Web Canvas smoke image has unexpected size {image.size}.")
        return image.size


@lru_cache(maxsize=12)
def _render_cached(path_text: str, file_size: int, mtime_ns: int, section: str, game_folder_text: str, quality: str) -> RenderedLiverySection:
    quality = normalize_quality(quality)
    decoded = _decode_cached(path_text, file_size, mtime_ns)
    if section not in decoded.sections:
        raise LiveryPreviewError(f"지원하지 않는 리버리 영역입니다: {section}")
    layers = list(decoded.sections[section])
    if not layers:
        raise LiveryPreviewError("이 영역에는 표시할 리버리 배치가 없습니다.")

    try:
        analysis = _analysis_cached(path_text, file_size, mtime_ns)
    except LiveryAnalysisError as exc:
        raise LiveryPreviewError(f"리버리의 대상 차량을 확인하지 못했습니다: {exc}") from exc
    if analysis.car_id <= 0:
        raise LiveryPreviewError("C_livery에서 대상 Car ID를 확인할 수 없습니다.")

    cache_path = _cache_path(path_text, file_size, mtime_ns, section, game_folder_text, quality)
    cached = _read_disk_cache(cache_path)
    if cached is not None:
        return RenderedLiverySection(section=section, png_bytes=cached, placement_count=len(layers), skipped_raster_logos=0, warnings=decoded.warnings)

    game_folder = Path(game_folder_text)
    _decoder, renderer = _load_backend()
    raster_count = sum(1 for layer in layers if bool(layer.get("is_raster_logo")))
    raster_resolver = None
    if raster_count:
        try:
            raster_resolver = raster_resolver_for_game(game_folder)
        except ExactLiveryPreviewError as exc:
            raise LiveryPreviewError(f"{section} 영역의 FH6 내장 래스터 데칼을 불러오지 못했습니다: {exc}") from exc

    prepared_layers, invisible_count = _validate_exact_assets_and_filter_noops(renderer, layers, raster_resolver)
    if not prepared_layers:
        raise LiveryPreviewError(f"{section} 영역에 표시 가능한 placement가 없습니다.")

    width, height, scale = QUALITY_DIMENSIONS[quality]
    scene = _build_web_scene(renderer, prepared_layers, width=int(width), height=int(height), scale=float(scale), raster_resolver=raster_resolver)
    canonical_png = _render_scene_in_edge(scene)
    projected = _projection_supersampled(canonical_png, section, analysis.car_id, game_folder=game_folder, scale=float(scale))
    preview_png = _checkerboard_preview(projected)
    _write_disk_cache(cache_path, preview_png)

    warnings = list(decoded.warnings)
    warnings.append(
        f"Web Canvas A/B: {scene.vector_layers} ordinary native vector layers were rasterized by Edge Canvas2D; "
        f"{scene.fallback_layers} gradient/raster layers retained the KFPS Pillow path."
    )
    if invisible_count:
        warnings.append(f"{section}: {invisible_count} fully transparent native placements were omitted as no-ops.")
    return RenderedLiverySection(section=section, png_bytes=preview_png, placement_count=len(layers), skipped_raster_logos=0, warnings=tuple(dict.fromkeys(warnings)))


def render_livery_section_web_canvas(path: Path | str, section: str, quality: str = "balanced") -> RenderedLiverySection:
    source = Path(path)
    if not source.is_file():
        raise LiveryPreviewError("C_livery 파일을 찾을 수 없습니다.")
    if find_edge_executable() is None:
        raise LiveryPreviewError("Web Canvas A/B 렌더러에는 Microsoft Edge가 필요합니다. Edge 설치를 확인해 주세요.")
    try:
        game_folder = require_fh6_game_folder()
    except ExactLiveryPreviewError as exc:
        raise LiveryPreviewError(str(exc)) from exc
    signature = _file_signature(source)
    with _CACHE_LOCK:
        return _render_cached(signature[0], signature[1], signature[2], str(section), str(game_folder.resolve()), normalize_quality(quality))
