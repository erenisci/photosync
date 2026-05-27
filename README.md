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

Early development. **Phase 0 (scaffolding)** is implemented:

- `app/paths.py` — USB root / bundle resolution and rclone binary lookup
- `app/config.py` — `settings.json` read/write
- `app/db.py` — SQLite upload history + scan cache
- `scripts/download_rclone.py` — fetches rclone binaries for packaging

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and the
development roadmap.

## Features (target)

- Scan photos/videos (extension whitelist + magic-byte check)
- SHA-256 hashing with a local scan cache (skip re-hashing unchanged files)
- Deduplication against a local SQLite history and the remote
- Multiple providers: Google Drive, Dropbox, OneDrive, S3-compatible (B2, R2, …)
- First-run setup wizard
- Per-file progress and match statistics
- Master-password-encrypted credentials (via rclone)
- Cross-platform: Windows, macOS, Linux
- Single binary (<50 MB) built with PyInstaller

## Development

Requires Python 3.11+.

```bash
pip install -e ".[dev]"   # install with dev tooling
ruff check .              # lint
mypy                      # type-check
pytest                    # run tests
```

See [docs/BUILD.md](docs/BUILD.md) for packaging and
[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for contribution guidelines.

## License

[MIT](LICENSE)
