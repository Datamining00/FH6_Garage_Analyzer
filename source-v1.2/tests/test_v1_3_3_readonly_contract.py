from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "fh6garage"


class ReadOnlyContractTests(unittest.TestCase):
    def test_process_memory_has_no_write_or_injection_primitives(self):
        source = (PKG / "memory_applied_state.py").read_text(encoding="utf-8")
        for token in (
            "WriteProcessMemory",
            "PROCESS_VM_WRITE",
            "PROCESS_VM_OPERATION",
            "VirtualProtectEx",
            "CreateRemoteThread",
            "NtWriteVirtualMemory",
            "DebugActiveProcess",
            "SetThreadContext",
        ):
            self.assertNotIn(token, source)
        self.assertIn("PROCESS_VM_READ", source)
        self.assertIn("PROCESS_QUERY_INFORMATION", source)
        self.assertIn("VirtualQueryEx", source)
        self.assertIn("ReadProcessMemory", source)

    def test_game_data_modules_do_not_write_source_files(self):
        modules = (
            "scanner.py",
            "parsers.py",
            "auction_thumbnails.py",
            "auction_manifest_registry.py",
        )
        forbidden = (
            ".write_text(",
            ".write_bytes(",
            ".unlink(",
            "os.replace(",
            "shutil.move(",
            "shutil.copy2(",
        )
        for module in modules:
            source = (PKG / module).read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source, f"{module} contains {token}")

    def test_memory_snapshot_persists_only_under_app_local_state(self):
        source = (PKG / "memory_applied_state.py").read_text(encoding="utf-8")
        self.assertIn('"FH6GarageAnalyzer"', source)
        self.assertIn('"memory_applied_state.json"', source)


if __name__ == "__main__":
    unittest.main()
