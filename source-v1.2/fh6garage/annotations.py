from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .local_storage import write_json_atomic


@dataclass(slots=True)
class LiveryAnnotation:
    note: str = ""
    checked: bool = False
    triangle: bool = False
    excluded: bool = False


def append_note(existing: str, addition: str) -> str:
    """Append a note block while preserving existing content and avoiding exact duplicates."""
    existing = (existing or "").strip()
    addition = (addition or "").strip()
    if not addition:
        return existing
    if not existing:
        return addition
    # Do not append the same complete block twice.
    blocks = [block.strip() for block in existing.split("\n\n") if block.strip()]
    if addition == existing or addition in blocks:
        return existing
    return f"{existing}\n\n{addition}"


class AnnotationStore:
    """Small local-only note/check store for saved content.

    No save file, thumbnail, path, creator name, vehicle name, or XUID is copied here.
    Each content item is represented only by a SHA-256 key derived from its GUID
    (preferred) or container-name fallback. Existing livery keys remain compatible.
    """

    SCHEMA = 1

    def __init__(self, path: Path | None = None):
        if path is None:
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            path = base / "FH6GarageAnalyzer" / "annotations.json"
        self.path = path
        self._entries: dict[str, dict[str, Any]] = {}
        self.load()

    @staticmethod
    def key_for(
        guid: str,
        container_name: str,
        namespace: str = "",
    ) -> str:
        base = (
            f"guid:{guid.strip().lower()}"
            if guid and guid.strip()
            else f"container:{container_name.strip().lower()}"
        )
        # Livery keeps the historic empty namespace so all existing annotations
        # continue to resolve. Tuning uses its own namespace.
        raw = f"{namespace.strip().lower()}:{base}" if namespace.strip() else base
        return hashlib.sha256(
            raw.encode("utf-8", errors="replace")
        ).hexdigest()

    @staticmethod
    def instance_key_for(
        guid: str,
        container_name: str,
        namespace: str = "",
    ) -> str:
        """Return a key for one physical saved-content container.

        Duplicate downloads can legitimately share a content GUID. Including
        the container name keeps check/triangle/note/X state independent for
        each entry shown in the UI.
        """
        raw = "|".join(
            (
                namespace.strip().lower(),
                guid.strip().lower(),
                container_name.strip().lower(),
            )
        )
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()

    def load(self) -> None:
        self._entries = {}
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != self.SCHEMA:
                return
            # v0.1.25 and older stored the same entries under "liveries".
            # Prefer the generic key but transparently migrate the old file.
            entries = data.get("contents", data.get("liveries", {}))
            if isinstance(entries, dict):
                for key, value in entries.items():
                    if not isinstance(key, str) or not isinstance(value, dict):
                        continue
                    self._entries[key] = {
                        "note": str(value.get("note", "")),
                        "checked": bool(value.get("checked", False)),
                        "triangle": bool(value.get("triangle", False)),
                        "excluded": bool(value.get("excluded", False)),
                    }
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # A damaged optional annotation file must never stop save scanning.
            self._entries = {}

    def get(self, key: str) -> LiveryAnnotation:
        value = self._entries.get(key, {})
        return LiveryAnnotation(
            note=str(value.get("note", "")),
            checked=bool(value.get("checked", False)),
            triangle=bool(value.get("triangle", False)),
            excluded=bool(value.get("excluded", False)),
        )

    def set_note(self, key: str, note: str) -> None:
        entry = self._default_entry(key)
        entry["note"] = (note or "").strip()
        self._cleanup_empty(key)
        self.save()

    def set_checked(self, key: str, checked: bool) -> None:
        entry = self._default_entry(key)
        entry["checked"] = bool(checked)
        self._cleanup_empty(key)
        self.save()

    def set_triangle(self, key: str, triangle: bool) -> None:
        entry = self._default_entry(key)
        entry["triangle"] = bool(triangle)
        self._cleanup_empty(key)
        self.save()

    def set_excluded(self, key: str, excluded: bool) -> None:
        entry = self._default_entry(key)
        entry["excluded"] = bool(excluded)
        self._cleanup_empty(key)
        self.save()

    def set(
        self,
        key: str,
        *,
        note: str | None = None,
        checked: bool | None = None,
        triangle: bool | None = None,
        excluded: bool | None = None,
        save: bool = True,
    ) -> None:
        entry = self._default_entry(key)
        if note is not None:
            entry["note"] = (note or "").strip()
        if checked is not None:
            entry["checked"] = bool(checked)
        if triangle is not None:
            entry["triangle"] = bool(triangle)
        if excluded is not None:
            entry["excluded"] = bool(excluded)
        self._cleanup_empty(key)
        if save:
            self.save()

    def save(self) -> bool:
        # Keep the legacy alias too so rolling back to an older analyzer
        # does not make existing livery annotations disappear.
        data = {
            "schema": self.SCHEMA,
            "contents": self._entries,
            "liveries": self._entries,
        }
        return write_json_atomic(self.path, data)

    def _cleanup_empty(self, key: str) -> None:
        entry = self._entries.get(key)
        if not entry:
            return
        if (
            not str(entry.get("note", "")).strip()
            and not bool(entry.get("checked", False))
            and not bool(entry.get("triangle", False))
            and not bool(entry.get("excluded", False))
        ):
            self._entries.pop(key, None)

    def _default_entry(self, key: str) -> dict[str, Any]:
        return self._entries.setdefault(
            key,
            {"note": "", "checked": False, "triangle": False, "excluded": False},
        )
