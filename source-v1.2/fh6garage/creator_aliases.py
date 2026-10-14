from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Iterable

from .local_storage import write_json_atomic


_SCHEMA = 1


@dataclass(slots=True)
class CreatorAliasGroup:
    current: str
    previous: list[str]

    def all_names(self) -> list[str]:
        return [self.current, *self.previous]


class CreatorAliasStore:
    """User-managed creator-name equivalence groups stored outside FH6 data."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            path = base / "FH6GarageAnalyzer" / "creator_aliases.json"
        self.path = Path(path)
        self.groups: list[CreatorAliasGroup] = []
        self.load()

    @staticmethod
    def _clean(name: str) -> str:
        return (name or "").strip()

    @staticmethod
    def _key(name: str) -> str:
        return CreatorAliasStore._clean(name).casefold()

    @staticmethod
    def _dedupe(names: Iterable[str], *, exclude: str = "") -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        excluded = CreatorAliasStore._key(exclude)
        for raw in names:
            name = CreatorAliasStore._clean(raw)
            key = CreatorAliasStore._key(name)
            if not name or not key or key == excluded or key in seen:
                continue
            seen.add(key)
            result.append(name)
        return result

    def load(self) -> None:
        self.groups = []
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return
        if not isinstance(data, dict) or data.get("schema") != _SCHEMA:
            return
        raw_groups = data.get("groups")
        if not isinstance(raw_groups, list):
            return

        claimed: set[str] = set()
        for raw in raw_groups:
            if not isinstance(raw, dict):
                continue
            current = self._clean(str(raw.get("current") or ""))
            if not current or self._key(current) in claimed:
                continue
            previous_raw = raw.get("previous")
            previous = self._dedupe(previous_raw if isinstance(previous_raw, list) else [], exclude=current)
            filtered: list[str] = []
            for name in previous:
                key = self._key(name)
                if key in claimed:
                    continue
                claimed.add(key)
                filtered.append(name)
            claimed.add(self._key(current))
            self.groups.append(CreatorAliasGroup(current=current, previous=filtered))

    def _write(self) -> bool:
        payload = {
            "schema": _SCHEMA,
            "groups": [
                {"current": group.current, "previous": list(group.previous)}
                for group in self.groups
                if group.current
            ],
        }
        return write_json_atomic(self.path, payload)

    def find_group(self, name: str) -> CreatorAliasGroup | None:
        key = self._key(name)
        if not key:
            return None
        for group in self.groups:
            if any(self._key(candidate) == key for candidate in group.all_names()):
                return group
        return None

    def group_for(self, name: str) -> CreatorAliasGroup:
        cleaned = self._clean(name)
        group = self.find_group(cleaned)
        if group is not None:
            return group
        return CreatorAliasGroup(cleaned, [])

    def canonical_name(self, name: str) -> str:
        group = self.group_for(name)
        return group.current

    def search_names(self, name: str) -> list[str]:
        return self.group_for(name).all_names()

    def display_name(self, name: str, *, max_previous: int = 2) -> str:
        group = self.group_for(name)
        if not group.current:
            return ""
        previous = list(group.previous)
        if not previous:
            return group.current
        shown = previous[:max_previous]
        remainder = len(previous) - len(shown)
        suffix = f" +{remainder}" if remainder > 0 else ""
        return f"{group.current} ({', '.join(shown)}{suffix})"

    def merge(self, source_name: str, new_current_name: str) -> CreatorAliasGroup:
        """Merge the complete source/target groups; the explicit target becomes current."""
        source = self._clean(source_name)
        target = self._clean(new_current_name)
        if not source or not target:
            raise ValueError("Creator names must not be empty.")

        source_group = self.find_group(source)
        target_group = self.find_group(target)

        if source_group is None:
            source_group = CreatorAliasGroup(source, [])
        if target_group is None:
            target_group = CreatorAliasGroup(target, [])

        if source_group is target_group:
            if self._key(source_group.current) == self._key(target):
                return source_group
            old_current = source_group.current
            source_group.current = target
            source_group.previous = self._dedupe(
                [old_current, *source_group.previous],
                exclude=target,
            )
            self._write()
            return source_group

        source_names = source_group.all_names()
        target_names = target_group.all_names()
        previous = self._dedupe(
            [source_group.current, *source_group.previous, *target_group.previous, target_group.current],
            exclude=target,
        )

        self.groups = [
            group
            for group in self.groups
            if group is not source_group and group is not target_group
        ]
        merged = CreatorAliasGroup(current=target, previous=previous)
        self.groups.append(merged)
        self._write()
        return merged

    def split(self, name: str) -> bool:
        """Detach one name from an existing group and make it an independent creator."""
        cleaned = self._clean(name)
        group = self.find_group(cleaned)
        if group is None or len(group.all_names()) <= 1:
            return False

        key = self._key(cleaned)
        remaining = [candidate for candidate in group.all_names() if self._key(candidate) != key]
        self.groups.remove(group)

        if remaining:
            if self._key(group.current) == key:
                remaining_current = remaining[0]
                remaining_previous = remaining[1:]
            else:
                remaining_current = group.current
                remaining_previous = [
                    candidate for candidate in group.previous
                    if self._key(candidate) != key
                ]
            self.groups.append(
                CreatorAliasGroup(
                    remaining_current,
                    self._dedupe(remaining_previous, exclude=remaining_current),
                )
            )

        self.groups.append(CreatorAliasGroup(cleaned, []))
        self._write()
        return True

    def reset_with_backup(self) -> Path | None:
        """Back up the matching file first, then reset to an empty mapping."""
        backup_path: Path | None = None
        if self.path.is_file():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            backup_dir = self.path.parent / "creator_alias_backups"
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"creator_aliases_{stamp}.json"
                shutil.copy2(self.path, backup_path)
            except OSError:
                backup_path = None
        self.groups = []
        self._write()
        return backup_path
