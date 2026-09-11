"""Read-only, same-car ownership check for a single thumbnail update."""
import os
from pathlib import Path
from types import SimpleNamespace
from .thumbnail_marks import safe_path
from .auction_thumbnails import _header_livery_token
from .parsers import read_header_file


def verify_owner(record, containers, token, scope_records):
    root = safe_path(containers)
    parent = safe_path(record.container_path)
    car_id = record.car_id
    if parent.parent != root or car_id is None or not token:
        raise ValueError('캐시 연결 식별 정보가 부족하여 생략')
    known = {safe_path(r.container_path): r.kind for r in scope_records
             if getattr(r, 'car_id', None) == car_id and getattr(r, 'kind', None) in ('Livery', 'SoulBoundLivery')}
    def candidates():
        found = {}
        with os.scandir(root) as entries:
            for entry in entries:
                fields = entry.name.split('_', 2)
                if len(fields) < 2 or fields[0] not in ('Livery', 'SoulBoundLivery'):
                    continue
                try:
                    same_car = int(fields[1]) == car_id
                except ValueError:
                    same_car = False
                path = Path(entry.path).absolute()
                if not same_car and path not in known:
                    continue
                path = safe_path(path)
                if not entry.is_dir(follow_symlinks=False):
                    raise ValueError('같은 차량의 저장 상태가 불완전하여 캐시 쓰기 생략')
                found[path] = fields[0]
        return found
    before = candidates()
    if parent not in before:
        raise ValueError('대상 리버리를 확인할 수 없어 캐시 쓰기 생략')
    stamps = {}
    for path, kind in before.items():
        header = path / 'header'
        first = header.stat()
        read_header_file(header, kind)  # Reject incomplete or invalid peers.
        other_token = _header_livery_token(SimpleNamespace(container_path=path))
        if not other_token:
            raise ValueError('같은 차량의 헤더를 확인할 수 없어 캐시 쓰기 생략')
        if other_token == token and path != parent:
            raise ValueError('다른 리버리와 공유하는 캐시여서 쓰기 생략')
        if path == parent and other_token != token:
            raise ValueError('확인 중 리버리가 변경되어 캐시 쓰기 생략')
        stamp = lambda s: (s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino)
        stamps[header] = stamp(first)
        if stamp(header.stat()) != stamps[header]:
            raise ValueError('확인 중 헤더가 변경되어 캐시 쓰기 생략')
    if before != candidates() or any(stamp(p.stat()) != value for p, value in stamps.items()):
        raise ValueError('확인 중 저장 목록이 변경되어 캐시 쓰기 생략')
    return True
