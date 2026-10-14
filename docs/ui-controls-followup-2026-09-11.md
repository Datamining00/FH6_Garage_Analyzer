# Settings and 2D UI follow-up

- Settings now sits immediately after Performance in the sidebar and uses the same navigation styling.
- Settings, export selection, preview tab headers and the 2D toolbar explicitly use light colors, including under a dark Windows palette. This corrects dark backgrounds with dark text inherited from native widget styling.
- 2D section selection is a top row of buttons. Only sections with positive layer counts and available PNG files appear. Right is initially selected when available; otherwise the first available section is selected. A selected section is retained during re-render when still available.
- The vehicle conversion message shown in the fourth screenshot identifies the geometry preparation required for a cold 3D preview. No conversion-disable setting was added: an existing geometry cache avoids repeated conversion, and the 2D view never requests vehicle geometry.

Validation: 993 regression tests passed locally. The fully patched main window was checked for sidebar order, and settings/2D panels were rendered with an explicit dark application palette. Screenshots verified readable backgrounds, present-only sections and default Right selection. A deferred initial image-fit timer is now owned by its viewer so destroying an unopened/early-closed viewer cancels the callback; an explicit destruction test covers this lifecycle.

The previously reviewed backup concurrency and lock-policy findings remain deferred at the user's request; this change does not apply those fixes.
