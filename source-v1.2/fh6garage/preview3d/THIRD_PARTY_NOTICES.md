# FH6 Assistant 3D preview — third-party notices

The 3D preview backend does not bundle Forza Horizon 6 game assets. Vehicle archives, livery masks, built-in decals, and C_livery data are read from the user's local FH6 installation/save as read-only inputs. Derived data is written under LocalAppData only.

## Kloudy's Forza Painter Suite (KFPS)

- Project: `heyitshestia/kloudys-forza-painter-suite`
- Pinned source commit: `6f53ca3c584d78659d06d4b4a39561db67d79345`
- License: MIT
- Used for: pinned `Kfps.ChassisConverter.exe`, C_livery decoder/rendering code, FH6 livery projection contract, built-in raster decal decoding, and vinyl resources required by that renderer.
- Local runtime is downloaded on demand and integrity-checked against the pinned revision/known converter blob.

The upstream license text is preserved in `licenses/KFPS_LICENSE.txt`.

## ForzaTechStudio

- Project: `D3FEKT/ForzaTechStudio`
- Structural reference commit: `4f373c5fb192551ce5249e320dd79b1399b693ca`
- License: MIT
- Used as a structural reference for FH6/ForzaTech carbin serialization, including numeric `CCarParts` classifications and serialized model-instance metadata. The Assistant implementation is reduced to the fields needed by the read-only 3D preview pipeline.

The upstream license text is preserved in `licenses/FORZATECHSTUDIO_LICENSE.txt`.
