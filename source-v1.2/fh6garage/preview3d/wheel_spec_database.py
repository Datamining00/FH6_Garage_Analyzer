from __future__ import annotations

from .pipeline_diagnostics import timed

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Callable
import urllib.error
import urllib.request


@dataclass(frozen=True)
class WheelSpecDatabaseSource:
    repository: str
    commit: str
    url: str
    size: int
    git_blob_sha1: str
    sha256: str
    cache_name: str = "fh6_game_db.sqlite"


PINNED_WHEEL_SPEC_DATABASE = WheelSpecDatabaseSource(
    repository="Dr-hydra/FH6-Adjust-Tool",
    commit="25cfd00195e74f8a85180b5f3193ee105259e2e2",
    url=(
        "https://raw.githubusercontent.com/Dr-hydra/FH6-Adjust-Tool/"
        "25cfd00195e74f8a85180b5f3193ee105259e2e2/"
        "src/FH6AdjustTool/Data/fh6_game_db.sqlite"
    ),
    size=15_773_696,
    git_blob_sha1="2cc259bd7f3815109b5f95c8e979cb5ec0b892dc",
    sha256="8720a361e4161532d7a22cd883166c834b79ea054ed86a0edb00e7bab9789d3c",
)


class WheelSpecDatabaseError(RuntimeError):
    """Raised when the pinned stock wheel database cannot be verified safely."""


# Full SHA-1 + SHA-256 verification reads the ~16 MiB pinned database twice. Keep
# the first verification strict, then reuse that verdict while the exact same file
# identity remains unchanged in this process. Any path/size/mtime change forces a
# fresh cryptographic verification.
_VERIFIED_FILE_IDENTITIES: set[tuple[str, int, int, str, str]] = set()


def _runtime_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base) / "FH6GarageAnalyzer" / "preview3d_runtime"
    else:
        root = Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root


def stock_wheel_database_path(
    source: WheelSpecDatabaseSource = PINNED_WHEEL_SPEC_DATABASE,
) -> Path:
    target = _runtime_root() / "data" / source.cache_name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _git_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_identity(path: Path, source: WheelSpecDatabaseSource) -> tuple[str, int, int, str, str]:
    stat = path.stat()
    return (
        str(path.resolve()),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        str(source.git_blob_sha1).casefold(),
        str(source.sha256).casefold(),
    )


def stock_wheel_database_is_valid(
    path: str | Path,
    source: WheelSpecDatabaseSource = PINNED_WHEEL_SPEC_DATABASE,
) -> bool:
    target = Path(path)
    try:
        if not target.is_file() or target.stat().st_size != int(source.size):
            return False
        identity = _verified_identity(target, source)
        if identity in _VERIFIED_FILE_IDENTITIES:
            return True
        if _git_blob_sha1(target).casefold() != source.git_blob_sha1.casefold():
            return False
        if _sha256(target).casefold() != source.sha256.casefold():
            return False
        _VERIFIED_FILE_IDENTITIES.add(identity)
        return True
    except OSError:
        return False


@timed('wheel_database_verify')
def ensure_stock_wheel_database(
    progress: Callable[[str], None] | None = None,
    *,
    source: WheelSpecDatabaseSource = PINNED_WHEEL_SPEC_DATABASE,
) -> Path:
    """Return a verified cached FH6 stock-wheel SQLite snapshot.

    The database is not distributed with FH6 Assistant. It is downloaded only
    when requested, stored under LocalAppData, integrity-checked by byte size,
    Git blob SHA-1 and SHA-256, and later opened read-only by FH6WheelSpecResolver.
    """

    target = stock_wheel_database_path(source)
    if stock_wheel_database_is_valid(target, source):
        return target

    if target.exists():
        try:
            target.unlink()
        except OSError as exc:
            raise WheelSpecDatabaseError(
                f"Invalid cached stock wheel database could not be replaced: {exc}"
            ) from exc

    temp = target.with_suffix(target.suffix + ".download")
    try:
        temp.unlink(missing_ok=True)
    except OSError:
        pass

    if progress:
        progress("Downloading the pinned FH6 stock wheel database (about 16 MB)...")

    try:
        request = urllib.request.Request(
            source.url,
            headers={"User-Agent": "FH6-Assistant-v1.4-wheel-morph"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise WheelSpecDatabaseError(
            f"Could not download the pinned FH6 stock wheel database: {exc}"
        ) from exc

    if not stock_wheel_database_is_valid(temp, source):
        try:
            actual_size = temp.stat().st_size
            actual_blob = _git_blob_sha1(temp)
            actual_sha256 = _sha256(temp)
        except OSError:
            actual_size = -1
            actual_blob = "<unreadable>"
            actual_sha256 = "<unreadable>"
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise WheelSpecDatabaseError(
            "Downloaded FH6 stock wheel database failed integrity verification. "
            f"Expected size={source.size}, blob={source.git_blob_sha1}, sha256={source.sha256}; "
            f"got size={actual_size}, blob={actual_blob}, sha256={actual_sha256}."
        )

    try:
        temp.replace(target)
        # The bytes were cryptographically verified immediately before the atomic
        # replace. Seed the target identity so the next lookup does not re-read the
        # same 16 MiB file twice again.
        _VERIFIED_FILE_IDENTITIES.add(_verified_identity(target, source))
    except OSError as exc:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise WheelSpecDatabaseError(
            f"Verified stock wheel database could not be installed in the runtime cache: {exc}"
        ) from exc

    if progress:
        progress("FH6 stock wheel database downloaded and integrity-verified.")
    return target
