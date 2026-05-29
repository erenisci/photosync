<div align="center">

# PhotoSync

**Portable USB-to-cloud photo & video catalog with on-drive thumbnail previews.**

[![CI](https://github.com/erenisci/photosync/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-80%20passing-success.svg)](tests/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-success.svg)](pyproject.toml)

</div>

---

PhotoSync turns any USB flash drive into a portable, cloud-backed photo library.
Drop the executable onto the drive, put your media in the `PhotoSync/` folder,
and double-click. The app scans, deduplicates by SHA-256, and uploads only what
isn't already in your cloud. No installation required — settings, history, and
encrypted credentials all live on the drive.

## Why PhotoSync?

> *"I want my photos in the cloud, but I also want to carry a flash with me
> that can preview them all — without filling 1 TB of storage on a 64 GB stick."*

That's the problem this tool solves. In **catalog mode**, your originals upload
to the cloud and are replaced on the drive by small thumbnail-with-URL stubs
plus a clickable HTML gallery. Online → click any thumbnail, see the
full-resolution original. Offline → still see every preview, just no full file.

It's *iCloud Photos' "Optimize Storage"* — but on a portable USB stick, with
the cloud of your choice.

## Features

- **Two sync modes** — Backup (keep originals) or Catalog (replace with thumbnail stub).
- **Selective sync** — only files inside `<drive>/PhotoSync/` are touched.
  Everything else on the drive is left alone.
- **Smart deduplication** — content-addressed by SHA-256; renames don't trigger
  re-uploads. A local scan cache means unchanged files aren't re-hashed.
- **Clickable offline catalog** — each folder gets a dependency-free
  `index.html` gallery. Online: thumbnails link to the cloud original. Offline:
  the previews still browse.
- **Master-password-encrypted credentials** via rclone — keys never leave
  the drive in plaintext.
- **70+ cloud providers** through bundled rclone — Google Drive, Dropbox,
  OneDrive, S3-compatible (Backblaze B2, Cloudflare R2, Wasabi presets),
  and easily extensible to any other rclone backend.
- **First-run setup wizard** — 4 screens, no manual config files.
- **Cross-platform** — Windows, macOS, Linux. Single ~55 MB executable.
- **Zero installation** — runs straight from the flash drive.

## Quick start

1. Download `PhotoSync.exe` (Windows) / `PhotoSync` (macOS/Linux) from the
   [Releases](../../releases) page.
2. Drop it onto your flash drive.
3. Create a `PhotoSync/` folder next to the executable, drop your photos
   and videos inside.
4. Double-click `PhotoSync`. The setup wizard runs on first launch:
   - Pick a cloud provider and a sync mode.
   - Authenticate (browser OAuth or S3 keys).
   - Choose a target folder name on the cloud side.
   - Set a master password — this encrypts your cloud credentials.
5. Press **Start**. Watch the progress; when it finishes, double-click the
   `PhotoSync/index.html` to browse your catalog.

## How catalog mode works

```
USB drive (D:\)
└── PhotoSync/                       ← only this folder is synced
    ├── 2024-Trip/
    │   ├── IMG_0001.jpg              (1024 px thumbnail, ~100 KB; cloud URL in EXIF)
    │   ├── IMG_0002.jpg
    │   ├── clip.mp4.preview.jpg      (video frame thumbnail)
    │   └── index.html                ← double-click → clickable gallery
    ├── Wedding/
    │   └── ...
    └── index.html                    ← top-level catalog
```

Each thumbnail JPEG carries the cloud URL of the original in its EXIF
`UserComment` tag, and the per-folder `index.html` renders the thumbnails as
a grid of `<a href="cloud-url"><img></a>` cards. Click any tile → the
full-resolution original opens from the cloud in a new browser tab.

### Safety invariant

PhotoSync **uploads first, then replaces**. If an upload fails, the original is
never touched. Stub recognition is double-layered: SQLite content-hash dedup
*and* an EXIF marker check — so even a wiped database can't trick the app into
re-uploading or destroying a stub.

## Supported cloud providers

The wizard ships with four ready-to-pick providers:

| Provider          | Auth          | Notes                              |
| ----------------- | ------------- | ---------------------------------- |
| Google Drive      | OAuth browser | 15 GB free                         |
| Dropbox           | OAuth browser | 2 GB free                          |
| OneDrive          | OAuth browser | 5 GB free                          |
| S3-compatible     | Access keys   | Presets: B2, R2, Wasabi, or custom |

Under the hood PhotoSync uses [rclone](https://rclone.org/), which supports
[70+ providers](https://rclone.org/overview/) (Box, pCloud, Mega, Storj,
Yandex, Mail.ru, MinIO, …). **Adding a new provider takes about 10 lines** —
see [Adding a cloud provider](docs/CONTRIBUTING.md#adding-a-cloud-provider).

## Recommended cloud per use case

- **Cheap and tiny photo budget** → Backblaze B2 ($0.006/GB/month, 10 GB free)
- **Frequent online viewing** → Cloudflare R2 (free egress traffic)
- **Already in the Google ecosystem** → Google Drive
- **Fully self-hosted** → MinIO / S3-compatible via "Other" preset

## Build from source

Requires Python 3.11+.

```bash
git clone https://github.com/erenisci/photosync.git
cd photosync
pip install -e ".[dev]"

python scripts/download_rclone.py --target windows   # or: macos, linux
python scripts/build.py                              # exe + release zip
```

Output: `dist/PhotoSync-v<version>-<os>.zip`. See [docs/BUILD.md](docs/BUILD.md)
for the GitHub Actions release workflow and signing notes.

## Development

```bash
pip install -e ".[dev]"
ruff check .       # lint
ruff format .      # auto-format
mypy               # type-check (strict)
pytest             # 80 tests
python -m app      # run with GUI from source
```

The codebase ships with **mypy strict** + **ruff** + **80 pytest tests** all
passing on every commit (CI: 3-OS matrix). The architecture is documented in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Contributing

PRs welcome! Read [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) before opening
one — the document covers code style, the catalog-mode safety invariants, and
how to add new cloud providers.

If you find a bug or want a feature, please open an issue with reproduction
steps or a clear use case.

## Roadmap (post-MVP)

- Bundled ffmpeg for proper video thumbnails (currently optional / placeholder)
- Cancellation in the main window
- Parallel hash + upload worker pool
- "Undo a stub" — re-download from cloud back to the drive
- Argon2 master-password layer
- Optional SQLite database encryption

## Security

PhotoSync's security model and threat analysis live in
[docs/ARCHITECTURE.md#security-model](docs/ARCHITECTURE.md#security-model). In
short: rclone encrypts credentials with your master password; PhotoSync never
stores secrets itself; all subprocess calls run with `shell=False` and explicit
argument lists; SQLite writes are parameterised.

Found a security issue? Please report it privately rather than via a public
issue.

## License

Released under the [MIT License](LICENSE).

Built with [rclone](https://rclone.org/) (MIT), [Pillow](https://python-pillow.org/) (HPND),
[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (MIT),
and Python 3.11+.
