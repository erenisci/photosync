# PhotoSync

> Portable USB-to-cloud photo & video backup with SHA-256 deduplication.

PhotoSync runs straight from a USB flash drive — no installation required. Plug
the drive into any computer, run `PhotoSync`, and it scans every photo and video
on the drive, computes their SHA-256 hashes, and uploads only the files that are
not already in your chosen cloud. Configuration, upload history, and credentials
all live on the flash drive itself.

File transfer is delegated to [rclone](https://rclone.org/), which supports 70+
cloud providers and handles OAuth flows and encryption for us.

## Status

**MVP complete.** All four development phases are implemented and tested (60 tests,
mypy strict, ruff). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full
design.

## Features

- Scan photos/videos (extension whitelist + magic-byte check)
- SHA-256 hashing with a local scan cache (skip re-hashing unchanged files)
- Deduplication against a local SQLite history and the remote
- Multiple providers: Google Drive, Dropbox, OneDrive, S3-compatible (B2, R2, …)
- First-run setup wizard (4-screen CustomTkinter GUI)
- Per-file progress and match statistics
- Master-password-encrypted credentials (via rclone)
- Cross-platform: Windows, macOS, Linux
- Single binary (<50 MB) built with PyInstaller

## Quick start (from source)

Requires Python 3.11+.

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Download rclone for your OS
python scripts/download_rclone.py --target windows   # or: macos, linux

# 3a. Run with GUI (setup wizard on first launch)
python -m app

# 3b. Or run in CLI mode (headless, e.g. for testing)
python -m app --cli \
  --endpoint https://s3.us-west-004.backblazeb2.com \
  --access-key-id YOUR_KEY \
  --secret-access-key YOUR_SECRET \
  --password masterpass \
  --scan-root E:\
```

## Testing on a USB flash drive (dev mode)

You can test PhotoSync directly on a flash drive without building a PyInstaller
binary:

1. Copy the entire `photosync/` repo folder to the flash drive (or work from it).
2. Make sure `bin/rclone.exe` exists (`python scripts/download_rclone.py --target windows`).
3. Run `python -m app` from the repo root — it will scan the **repo root** (the
   USB drive if that's where the repo is).
4. Alternatively, use `--scan-root E:\` to scan any path while keeping the repo
   elsewhere.

PhotoSync creates `data/` in the repo root on first run (settings, database,
rclone config). This folder is gitignored.

## Building a release binary

```bash
python scripts/build.py     # downloads rclone + builds exe + creates release zip
```

Output: `dist/PhotoSync-v0.1.0-windows.zip`. See [docs/BUILD.md](docs/BUILD.md)
for details and CI release workflow.

## Development

```bash
ruff check .     # lint
ruff format .    # auto-format
mypy             # type-check (strict)
pytest           # 60 tests
```

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for contribution guidelines.

## License

[MIT](LICENSE)
