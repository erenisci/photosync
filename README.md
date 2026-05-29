# PhotoSync

> Portable USB-to-cloud photo & video catalog with thumbnail-on-drive previews.

PhotoSync runs straight from a USB flash drive — no installation required. Plug
the drive into any computer, run `PhotoSync`, and it scans the drive's
`PhotoSync/` folder for new photos and videos, computes their SHA-256 hashes,
and uploads only the files that are not already in your chosen cloud.

Two modes are supported:

- **Backup mode** — uploads copies; originals stay on the drive untouched.
- **Catalog mode** — after a successful upload, the original is replaced with a
  small thumbnail-with-URL stub, and an `index.html` gallery is generated per
  folder. The flash holds a clickable preview library; full files live in the
  cloud and open in your browser when you click a thumbnail.

File transfer is delegated to [rclone](https://rclone.org/), which handles OAuth
flows and encryption for us and supports 70+ cloud providers.

## Status

**MVP complete.** 80 tests, mypy strict, ruff clean. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Features

- Only files under the drive's **`PhotoSync/` folder** are synced — everything
  else on the drive is left alone, giving you explicit control.
- Photo/video extension whitelist + magic-byte sanity check.
- SHA-256 hashing with a local scan cache (unchanged files aren't re-hashed).
- Deduplication against a local SQLite history.
- Multiple providers: Google Drive, Dropbox, OneDrive, S3-compatible (B2, R2, …).
- First-run setup wizard (4-screen CustomTkinter GUI).
- Per-file progress and match statistics.
- Master-password-encrypted credentials (via rclone).
- **Catalog mode** generates a clickable HTML gallery per folder.
- Cross-platform: Windows, macOS, Linux. Single binary (~55 MB).

## How catalog mode works

```
USB drive (D:\)
└── PhotoSync/              ← only this folder is synced
    ├── 2024-Trip/
    │   ├── IMG_0001.jpg       (1024px thumbnail, ~100 KB; cloud URL in EXIF)
    │   ├── IMG_0002.jpg
    │   ├── clip.mp4.preview.jpg  (video frame thumbnail; ffmpeg-extracted)
    │   └── index.html         ← open in browser → clickable gallery
    ├── Wedding/
    │   └── ...
    └── index.html            ← top-level catalog linking to each folder
```

Each thumbnail JPEG carries the cloud URL of the original in its EXIF
`UserComment`, and the per-folder `index.html` renders the thumbnails as a grid
of `<a href="cloud-url"><img></a>` — clicking opens the full-resolution
original from the cloud in a new tab. Offline you still see the thumbnails.

## Quick start

Drop `PhotoSync.exe` onto your flash drive, create a `PhotoSync/` folder next
to it, and put your photos/videos inside that folder. Double-click `PhotoSync`.
On first run the setup wizard walks you through choosing a cloud, authenticating,
and creating a master password.

## Building from source

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
python scripts/download_rclone.py --target windows
python scripts/build.py      # PyInstaller exe + release zip
```

See [docs/BUILD.md](docs/BUILD.md) for details and the GitHub Actions release
workflow.

## Development

```bash
ruff check .     # lint
ruff format .    # auto-format
mypy             # type-check (strict)
pytest           # 80 tests
```

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for contribution guidelines.

## License

[MIT](LICENSE)
