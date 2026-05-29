StereoDandifier
================

An opinionated stereoscopic image tool for making stereo cards.

Project Layout
--------------

- `src/stereo_dandifier/` contains the application package.
- `src/stereo_dandifier/ui.py` contains the PySide window.
- `src/stereo_dandifier/image_ops.py` contains pure image rendering operations.
- `src/stereo_dandifier/formats.py` contains card format data and unit conversion helpers.
- `src/stereo_dandifier/exif.py` contains EXIF and caption helpers.
- `tests/` contains unit tests for the non-Qt logic.

Run
---

```bash
.venv/bin/python -m stereo_dandifier
```

After installation, the console script is also available:

```bash
stereo-dandifier
```

Test
----

```bash
.venv/bin/python -m pytest
```
