# Building & Distributing PhotoSync

PhotoSync ships as a single PyInstaller executable per platform, bundled with the
matching rclone binary. The end result is a release zip the user extracts onto a
USB flash drive.

## Prerequisites

- Python 3.11+
- Dev dependencies: `pip install -e ".[dev]"` (installs PyInstaller, ruff, mypy,
  pytest)

## 1. Fetch the rclone binaries

The rclone binaries live in `bin/` and are **not** committed (they are
gitignored). Download the pinned version with checksum verification:

```bash
python scripts/download_rclone.py            # all platforms
python scripts/download_rclone.py --target linux   # one platform
```

This writes `bin/rclone.exe`, `bin/rclone-mac`, and `bin/rclone-linux`. The
version is pinned in `scripts/download_rclone.py` (`RCLONE_VERSION`) because the
`--progress` output we parse can change between rclone releases — bump it
deliberately and re-test.

## 2. Build the executable

```bash
pyinstaller --onefile --windowed --name PhotoSync \
  --add-data "bin:bin" \
  --icon assets/icon.ico \
  app/main.py
```

> On Windows the `--add-data` separator is `;` instead of `:` —
> `--add-data "bin;bin"`. `scripts/build.py` (Phase 4) abstracts this per-OS.

The output is `dist/PhotoSync` (or `dist/PhotoSync.exe`).

## 3. Package the release

Bundle the executable with `README.txt` and `LICENSE` into a per-platform zip:

```
PhotoSync-vX.Y.Z-{windows|macos|linux}.zip
```

`data/` is intentionally absent — PhotoSync creates it on first run, keeping the
release minimal.

## Cross-platform builds

PyInstaller does not cross-compile: each OS must be built on its own runner. The
intended setup is a GitHub Actions matrix (`windows-latest`, `macos-latest`,
`ubuntu-latest`), with each job downloading its own rclone binary and producing
its own zip. See [.github/workflows/ci.yml](../.github/workflows/ci.yml) for the
lint/type-check/test pipeline; the release build job is added in Phase 4.

## Signing notes

- **macOS:** unsigned bundles are blocked by Gatekeeper; users must "open anyway"
  unless an Apple Developer certificate ($99/yr) is used.
- **Windows:** without a code-signing certificate, SmartScreen shows "Unknown
  publisher".

Both are documented for end users rather than worked around in the MVP.
