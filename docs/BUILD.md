# Building & Distributing PhotoSync

PhotoSync ships as a **single PyInstaller executable per platform**, with the
matching rclone binary embedded inside via `--add-data`. Distribution is the
bare binary — no installer, no archive. The user downloads one file and runs
it from the flash drive.

| OS      | Release asset name        | Binary inside |
| ------- | ------------------------- | ------------- |
| Windows | `PhotoSync-windows.exe`   | `PhotoSync.exe` |
| macOS   | `PhotoSync-macos`         | `PhotoSync`     |
| Linux   | `PhotoSync-linux`         | `PhotoSync`     |

## Prerequisites

- Python 3.11+
- Dev dependencies: `pip install -e ".[dev]"` (installs PyInstaller, ruff, mypy,
  pytest, Pillow, customtkinter)

## Quick build (local)

`scripts/build.py` handles rclone download + PyInstaller:

```bash
python scripts/build.py                  # full build for current OS
python scripts/build.py --skip-rclone    # skip rclone download (if already in bin/)
python scripts/build.py --skip-package   # build exe only, no release-zip wrap
```

Output: `dist/PhotoSync(.exe)` — the bare binary. The release CI uses
`--skip-package` and renames the file per platform; the optional zip from
`build.py` exists only for users who want to hand-ship the binary alongside
a `README.txt` / `LICENSE`.

## Manual steps (if you want full control)

### 1. Fetch the rclone binary

The rclone binaries live in `bin/` and are **not** committed (gitignored).
Download the pinned version with checksum verification:

```bash
python scripts/download_rclone.py            # all platforms
python scripts/download_rclone.py --target windows  # one platform
```

The version is pinned in `scripts/download_rclone.py`
(`RCLONE_VERSION = 1.74.2`) because the `--progress` output we parse can
change between rclone releases — bump it deliberately and re-test.

### 2. Build the executable

```bash
pyinstaller --onefile --windowed --name PhotoSync \
  --add-data "bin:bin" \
  --icon assets/icon.ico \
  app/main.py
```

> On Windows the `--add-data` separator is `;` instead of `:` —
> `--add-data "bin;bin"`. `scripts/build.py` handles this automatically.

The bundled `bin/` is extracted at runtime into `sys._MEIPASS`;
`paths.get_bin_dir()` looks there first when frozen.

## Development testing (from source, no PyInstaller)

You can run PhotoSync straight from a USB flash drive without building:

```bash
# 1. Download rclone for your OS
python scripts/download_rclone.py --target windows

# 2. Create a PhotoSync/ folder with some media — only this folder is synced
mkdir PhotoSync
cp /some/photos/*.jpg PhotoSync/

# 3. Run with GUI (first launch shows the setup wizard)
python -m app

# 4. Or run in CLI mode
python -m app --cli --password <pw> --scan-root E:\PhotoSync --mode catalog
```

The `--mode` flag toggles between `backup` (keep originals; default) and
`catalog` (replace with thumbnail + URL stub, write index.html galleries).

## Releasing

PyInstaller does not cross-compile: each OS must be built on its own runner.
The GitHub Actions workflow `.github/workflows/release.yml` runs a 3-OS
matrix triggered by pushing a `v*` tag:

```bash
git tag -a v0.1.0 -m "PhotoSync v0.1.0"
git push origin v0.1.0
```

Each runner:

1. Downloads its platform's rclone binary.
2. Runs `python scripts/build.py --skip-package` to build the bare exe.
3. Renames the binary to `PhotoSync-{windows.exe|macos|linux}`.
4. Uploads it as a workflow artifact.

The `publish` job then attaches all three binaries to a new GitHub Release.
End users download a single file from
[Releases](https://github.com/erenisci/photosync/releases/latest).

## Signing notes

- **macOS:** unsigned bundles are blocked by Gatekeeper. Users must run
  `xattr -d com.apple.quarantine PhotoSync && chmod +x PhotoSync` or
  right-click → Open. An Apple Developer certificate ($99/yr) would
  remove this friction.
- **Windows:** without a code-signing certificate, SmartScreen shows
  "Unknown publisher" on first launch. Users click "More info → Run anyway".

Both are documented for end users in the [README](../README.md#quick-start)
rather than worked around in the MVP.
