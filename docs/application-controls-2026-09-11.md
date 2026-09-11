# Application controls and section preview

The sidebar Settings dialog persists options in LocalAppData/FH6GarageAnalyzer/app_options.json. Workers snapshot settings at start; preview changes apply to the next job.

- Preview tabs: thumbnail, 2D, 3D. 2D lazily renders section PNGs at 1x/2x/4x without converting vehicle geometry. Sections can be switched, zoomed, and fitted to the window.
- Both bulk export actions open a checked selection list. Individual card export remains available.
- Backup cards replace the movement action with a trash button. A confirmed deletion removes only the indexed backup and its unreferenced preview. Index failure restores the staged backup folder.
- Locked sources are excluded at the final cut boundary, even after successful backup verification. Disabling export cut also prevents source deletion at that boundary.
- Auto backup defaults OFF and requires a configured backup directory. It runs after scan results change and omits previously backed-up identical container/name/content combinations even when manual duplicate backups are enabled.
- Automatic recognition defaults ON. It performs the existing startup scan and checks livery payload changes every three seconds while idle. Manual refresh remains available when OFF.
- Cache defaults ON. OFF bypasses persistent geometry, tire and livery-result cache reads/writes, using the preview's temporary workspace. Existing cache files, shared tools/databases and diagnostic logs are retained.
- Download date, auction badge and hide-button visibility default ON.
- Different-name duplicate permission and unconditional duplicate permission default OFF. Unconditional permission takes precedence for manual exports.
- Applied-livery movement warnings default ON and use the application's available applied-state information.
- CPU job count defaults to automatic; explicit values are limited to the machine's logical processor count. It controls concurrent native texture conversion jobs, not CPU affinity.
- Skip vehicle materials defaults OFF. ON retains geometry/livery and omits native material texture preparation. Its cache entries are separate from full-material entries.

Validation: 990 regression tests passed locally, including 12 new tests covering settings persistence/snapshots, selection, 2D image replacement, duplicate policies, deletion rollback/path confinement, auto-backup idempotence, locked/disabled cut, CPU limits and cache bypass. The fully patched main window and settings dialog were constructed offscreen; a backup card exposed the visible trash action. No game save was mutated by these checks.
