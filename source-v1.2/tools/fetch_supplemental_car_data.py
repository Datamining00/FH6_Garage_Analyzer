from __future__ import annotations

import base64
import gzip
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fh6garage.acquisition_db import AcquisitionDatabase  # noqa: E402


API_URL = "https://api.github.com/repos/Datamining00/FH6-Assistant-Data/contents/fh6_cars.json.gz?ref=main"
MAX_RESPONSE_BYTES = 256 * 1024
MIN_CAR_COUNT = 500


def _validate(raw: bytes) -> int:
    try:
        payload = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"supplemental data is not valid gzip JSON: {exc}") from exc

    # Use the same parser as the application. This prevents a build from
    # accepting a private-data schema that the shipped runtime cannot decode.
    try:
        parsed = AcquisitionDatabase._parse_payload(payload)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"supplemental data is not runtime-compatible: {exc}") from exc
    if len(parsed) < MIN_CAR_COUNT:
        raise RuntimeError(f"supplemental car count is too small: {len(parsed)}")
    return len(parsed)


def fetch(token: str, destination: Path) -> int:
    request = urllib.request.Request(
        API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "FH6-Assistant-build",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("GitHub contents response is unexpectedly large")
    envelope = json.loads(body.decode("utf-8"))
    if not isinstance(envelope, dict) or envelope.get("encoding") != "base64":
        raise RuntimeError("GitHub contents response did not contain base64 file content")
    encoded = str(envelope.get("content") or "").replace("\n", "")
    raw = base64.b64decode(encoded, validate=True)
    count = _validate(raw)

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="fh6_cars_", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return count


def main() -> int:
    token = os.environ.get("FH6_ASSISTANT_DATA_TOKEN", "").strip()
    if not token:
        raise SystemExit("FH6_ASSISTANT_DATA_TOKEN is required to stage private supplemental data")
    destination = PROJECT_ROOT / "data" / "fh6_cars.json.gz"
    count = fetch(token, destination)
    print(f"Staged supplemental car data: {count} cars -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
