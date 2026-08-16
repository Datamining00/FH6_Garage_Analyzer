from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class LocalPreferences:
    """Small JSON-backed UI preference store under LocalAppData."""

    SCHEMA = 1

    def __init__(self, path: Path | None = None):
        if path is None:
            base = Path(
                os.environ.get("LOCALAPPDATA")
                or (Path.home() / "AppData" / "Local")
            )
            path = base / "FH6GarageAnalyzer" / "ui_preferences.json"
        self.path = path
        self._values: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        self._values = {}
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == self.SCHEMA:
                values = data.get("values", {})
                if isinstance(values, dict):
                    self._values = values
        except (OSError, UnicodeError, json.JSONDecodeError):
            self._values = {}

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._values.get(key, default)
        return value if isinstance(value, bool) else default

    def set_bool(self, key: str, value: bool) -> None:
        self._values[key] = bool(value)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": self.SCHEMA, "values": self._values}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
