# Application icon

Place the finalized `.icns` file generated from the MAHI LLM branding artwork in this folder as `icon.icns` before running `make package`. The PyInstaller spec automatically wires this asset into the `.app` bundle.

You can convert a 1024×1024 PNG into the required iconset with:

```bash
iconutil -c icns MAHI.iconset
```

Where `MAHI.iconset` contains the standard `icon_{16,32,128,256,512}@2x.png` variants.
