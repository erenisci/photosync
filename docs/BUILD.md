# Building & Distributing PhotoSync

PhotoSync ships as a single PyInstaller executable per platform, bundled with the
matching rclone binary. The end result is a release zip the user extracts onto a
USB flash drive.

## Prerequisites

- Python 3.11+
- Dev dependencies: `pip install -e ".[dev]"` (installs PyInstaller, ruff, mypy,
  pytest, customtkinter)

## Quick build (recommended)

`scripts/build.py` handles everything — rclone download, PyInstaller, and release
zip creation:

```bash
python scripts/build.py               # full build for current OS
python scripts/build.py --skip-rclone  # skip rclone download (if already in bin/)
python scripts/build.py --skip-package # build exe only, no zip
```

Output: `dist/PhotoSync-v0.1.0-{windows|linux|darwin}.zip`

## Manual steps (if needed)

### 1. Fetch the rclone binaries

The rclone binaries live in `bin/` and are **not** committed (gitignored).
Download the pinned version with checksum verification:

```bash
python scripts/download_rclone.py            # all platforms
python scripts/download_rclone.py --target windows  # one platform
```

The version is pinned in `scripts/download_rclone.py` (`RCLONE_VERSION = 1.74.2`)
because the `--progress` output we parse can change between rclone releases — bump
it deliberately and re-test.

### 2. Build the executable

```bash
pyinstaller --onefile --windowed --name PhotoSync \
  --add-data "bin:bin" \
  --icon assets/icon.ico \
  app/main.py
```

> On Windows the `--add-data` separator is `;` instead of `:` —
> `--add-data "bin;bin"`. `scripts/build.py` handles this automatically.

### 3. Package the release

Bundle the executable with `README.txt` and `LICENSE` into a per-platform zip:

```
PhotoSync-vX.Y.Z-{windows|macos|linux}.zip
```

`data/` is intentionally absent — PhotoSync creates it on first run.

## Development testing (without PyInstaller)

You can test directly from source on a USB flash drive:

```bash
# 1. Download rclone for your OS
python scripts/download_rclone.py --target windows

# 2. Run with GUI
python -m app

# 3. Or run in CLI mode (no GUI needed)
python -m app --cli --password <pw> --scan-root E:\
```

## Cross-platform builds

PyInstaller does not cross-compile: each OS must be built on its own runner. The
GitHub Actions release workflow (`.github/workflows/release.yml`) runs a 3-OS
matrix triggered by pushing a `v*` tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Each runner downloads its platform's rclone binary, builds the exe, and uploads
the zip as a GitHub Release artifact.

## Signing notes

- **macOS:** unsigned bundles are blocked by Gatekeeper; users must "open anyway"
  unless an Apple Developer certificate ($99/yr) is used.
- **Windows:** without a code-signing certificate, SmartScreen shows "Unknown
  publisher".

Both are documented for end users rather than worked around in the MVP.
