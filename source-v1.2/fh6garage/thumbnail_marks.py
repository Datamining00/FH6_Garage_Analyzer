"""Reversible image-only writes with a durable, per-file recovery journal."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from PIL import Image, ImageDraw, ImageFont

_LOCK = RLock()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('연결된 경로는 수정하지 않습니다')
    return path


def atomic(path, data):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.fh6-thumbnail-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(path)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def draw_marks(data, auction, locked):
    with Image.open(io.BytesIO(data)) as image:
        fmt = image.format
        if fmt not in ('WEBP', 'PNG', 'JPEG', 'BMP') or getattr(image, 'is_animated', False):
            raise ValueError('지원하지 않는 이미지 형식')
        image.load()
        canvas = image.convert('RGBA')
        w, h = canvas.size
        scale = max(1, min(w / 540, h / 300))
        size = max(14, round(16 * scale))
        font = None
        for name in (Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'segoeuib.ttf', 'DejaVuSans-Bold.ttf'):
            try:
                font = ImageFont.truetype(str(name), size)
                break
            except OSError:
                pass
        font = font or ImageFont.load_default(size=size)
        draw = ImageDraw.Draw(canvas)
        pad = round(9 * scale)
        box_h = round(29 * scale)
        text_w = round(draw.textlength('Auction', font=font)) if auction else 0
        lock_w = round(25 * scale) if locked else 0
        width = pad * 2 + text_w + lock_w + (pad if auction and locked else 0)
        left, top = (w - width) // 2, max(0, h - box_h - round(6 * scale))
        draw.rounded_rectangle((left, top, left + width, top + box_h), radius=round(7 * scale),
                               fill=(255, 255, 255, 245), outline=(198, 186, 239, 255), width=max(3, round(3 * scale)))
        if auction:
            draw.text((left + pad, top + box_h / 2), 'Auction', font=font, anchor='lm', fill='#4e329c')
        if locked:
            x = left + width - pad - lock_w
            y = top + round(5 * scale)
            ink = '#6e4bf2'
            draw.arc((x + 6*scale, y, x + 19*scale, y + 15*scale), 180, 360, fill=ink, width=max(2, round(2*scale)))
            draw.rounded_rectangle((x + 3*scale, y + 8*scale, x + 22*scale, y + 21*scale), radius=3*scale, fill=ink)
            draw.ellipse((x + 11*scale, y + 12*scale, x + 14*scale, y + 15*scale), fill='white')
        result = io.BytesIO()
        options = {'lossless': True} if fmt == 'WEBP' else {'quality': 95, 'subsampling': 0} if fmt == 'JPEG' else {}
        if fmt in ('JPEG', 'BMP'):
            canvas = canvas.convert('RGB')
        canvas.save(result, format=fmt, **options)
        return result.getvalue()


class MarkStore:
    def __init__(self, root):
        self.root = safe_path(root)
        self.index = self.root / 'index.json'

    def load(self):
        if not self.index.exists():
            return {}
        value = json.loads(self.index.read_text(encoding='utf8'))
        if value.get('schema') != 1 or not isinstance(value.get('files'), dict):
            raise ValueError('썸네일 원본 기록을 읽을 수 없습니다')
        return value['files']

    def save(self, entries):
        atomic(self.index, json.dumps({'schema': 1, 'files': entries}, ensure_ascii=False).encode('utf8'))

    def original(self, entry):
        sha = entry['original']
        if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('잘못된 원본 식별자')
        path = safe_path(self.root / (sha + '.bin'))
        data = path.read_bytes()
        if digest(data) != sha:
            raise ValueError('보관된 원본이 손상되었습니다')
        return data

    def apply(self, targets, *, restore_all=False, reapply=False, partial=False):
        """targets = verified path -> (auction, locked). Never restore unmatched external replacements."""
        with _LOCK:
            entries = self.load()
            result = {'written': 0, 'restored': 0, 'deleted_backups': 0, 'failures': [], 'originals': {}, 'changed_paths': [], 'touched_paths': []}
            retired = set()
            work = {str(Path(p).absolute()): flags for p, flags in targets.items()}
            if restore_all:
                work = {p: (False, False) for p in entries}
            result["touched_paths"] = [p.casefold() for p in work]
            for raw, flags in work.items():
                try:
                    path = safe_path(raw)
                    if path.suffix.lower() not in ('.webp', '.png', '.jpg', '.jpeg', '.bmp'):
                        raise ValueError('썸네일 확장자가 아닙니다')
                    current = path.read_bytes()
                    now = digest(current)
                    entry = entries.get(raw)
                    old_entry = dict(entry) if entry else None
                    if entry and now not in (entry['original'], entry['output'], entry.get('previous_output')):
                        if not reapply:
                            raise ValueError('게임 또는 다른 프로그램이 교체한 파일: 재적용 필요')
                        entry = None  # Explicit reapply adopts the new, verified image.
                    if (entry and not reapply and now == entry["output"]
                            and entry.get("flags") == list(flags) and entry.get("renderer") == 2):
                        continue
                    original = self.original(entry) if entry else current
                    active = any(flags)
                    if not entry and not active and not (reapply and old_entry):
                        continue
                    output = draw_marks(original, *flags) if active else original
                    if entry is None:
                        sha = digest(original)
                        backup = self.root / (sha + '.bin')
                        if not backup.exists():
                            atomic(backup, original)
                        elif backup.read_bytes() != original:
                            raise ValueError('원본 백업 충돌')
                        entry = {'original': sha, 'output': now}
                    # Journal the planned bytes first: a crash before/after replace
                    # can always recover using either original or output hash.
                    previous = old_entry or dict(entry)
                    entry = dict(entry, output=digest(output), previous_output=now, active=active, flags=list(flags), renderer=2)
                    entries[raw] = entry
                    self.save(entries)
                    if safe_path(path).read_bytes() != current:
                        entries[raw] = previous
                        self.save(entries)
                        raise ValueError('처리 중 파일이 변경되어 생략')
                    try:
                        if output != current:
                            atomic(path, output)
                    except Exception:
                        entries[raw] = previous
                        self.save(entries)
                        raise
                    if output != current:
                        result['written' if active else 'restored'] += 1
                        result['changed_paths'].append(raw.casefold())
                    if reapply and old_entry and old_entry['original'] != entry['original']:
                        retired.add(old_entry['original'])
                except Exception as exc:
                    result['failures'].append(f'{raw}: {exc}')
            # Only retire superseded originals after new backup + target commit.
            # Another thumbnail may still share the same original bytes.
            used = {entry['original'] for entry in entries.values()}
            for sha in retired - used:
                try:
                    if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                        raise ValueError('잘못된 이전 백업 이름')
                    old = safe_path(self.root / (sha + '.bin'))
                    if old.exists():
                        old.unlink()
                        result['deleted_backups'] += 1
                except Exception as exc:
                    result['failures'].append(f'이전 백업 삭제 실패: {exc}')
            # Original images let the app draw one crisp badge without stacking
            # its UI overlay on top of the already-stamped file.
            for path, entry in entries.items():
                if path not in work:
                    continue
                try:
                    if entry.get('active') and digest(safe_path(path).read_bytes()) == entry['output']:
                        self.original(entry)
                        result['originals'][path.casefold()] = str(self.root / (entry['original'] + '.bin'))
                except Exception:
                    pass
            return result
