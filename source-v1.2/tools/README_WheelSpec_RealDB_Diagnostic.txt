FH6 WheelSpec RealDB Diagnostic (Car ID 1006 / FER_FXX_05)
===============================================================

Purpose
-------
Read the stock wheel specification for Car ID 1006 from a readable/extracted FH6 SQLite database.
The selected database is opened read-only by validate_wheel_spec_real_db.py.

Usage
-----
1. Double-click Run_FH6_WheelSpec_RealDB_Diagnostic.cmd
2. Select a readable/extracted FH6 SQLite database (.sqlite/.db or any file if applicable).
3. The diagnostic writes:
   %LOCALAPPDATA%\FH6 Assistant\Diagnostics\FER_FXX_05_wheelspec_realdb.json
4. Upload that JSON for analysis.

Important
---------
- This tool does NOT decrypt or modify gamedbRC.slt.
- A raw/obfuscated gamedbRC.slt that is not SQLite will fail safely.
- The database is opened with SQLite mode=ro and PRAGMA query_only=ON.
- SHA-256 is recorded before and after the diagnostic to verify it was unchanged.
- Only Car ID 1006 is requested by the launcher.
