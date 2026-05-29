# PhotoSync Architecture

PhotoSync is a portable application that runs from a USB flash drive and uploads
the contents of the drive's `PhotoSync/` folder to a chosen cloud provider,
skipping anything that has already been uploaded. File transfer is delegated to
[rclone](https://rclone.org/); PhotoSync orchestrates scanning, hashing,
deduplication, optional thumbnail-stub generation, and the user interface.

## Goals & non-goals

**In scope**

- Selective sync: only files under the drive's `PhotoSync/` folder are touched.
- Two sync modes:
  - **Backup** — uploads copies, originals stay on the drive.
  - **Catalog** — after upload, replace the original with a thumbnail-with-URL
    stub and (re)generate a clickable HTML gallery per folder.
- Scan photo/video files (extension whitelist + magic-byte check).
- SHA-256 hashing with a local scan cache.
- Deduplication against a local SQLite history.
- Providers: Google Drive, Dropbox, OneDrive, S3-compatible (B2, R2, …).
- First-run setup wizard, per-file progress, master-password-encrypted creds.
- Cross-platform: Windows, macOS, Linux. Single binary (~55 MB).
- Resume after interrupted network transfers (rclone behaviour).

**Out of scope (at least for MVP)**

- iCloud (overly restrictive API).
- Perceptual / near-duplicate detection.
- Two-way sync or cloud → drive download.
- Fan-out to multiple clouds at once.
- Cancellation mid-sync.

## Technology choices

| Layer             | Choice                          | Rationale                              |
| ----------------- | ------------------------------- | -------------------------------------- |
| Language          | Python 3.11+                    | Fast iteration, broad stdlib           |
| GUI               | CustomTkinter                   | Modern look, ~Tkinter API, +~5 MB      |
| Cloud transport   | rclone (subprocess)             | 70+ providers, OAuth & encryption done |
| Local cache       | SQLite (stdlib)                 | Single embedded file                   |
| Config encryption | rclone's own password mechanism | Avoid double-encrypting                |
| Packaging         | PyInstaller (`--onefile`)       | Single executable, no deps to install  |
| Concurrency       | threading + queue               | I/O-bound work; asyncio is overkill    |
| Logging           | stdlib `logging`                | Zero dependency, sufficient at scale   |
| Tests             | pytest                          | Less boilerplate, strong fixtures      |
| License           | MIT                             | Permissive, maximizes adoption         |

Electron/Tauri were rejected: with a single developer and a ~3-month timeline,
the learning curve isn't justified. rclone is used instead of integrating cloud
SDKs directly because its OAuth flows and provider support are already
battle-tested.

## Source layout

```
photosync/
├── app/
│   ├── main.py            # Entry point + CLI; routes to wizard / main window
│   ├── paths.py           # Bundle root + source folder + rclone binary lookup
│   ├── config.py          # settings.json read/write (incl. SyncMode)
│   ├── db.py              # SQLite operations (uploads + scan_cache)
│   ├── hasher.py          # SHA-256 chunked hashing
│   ├── scanner.py         # Media file discovery
│   ├── rclone_client.py   # rclone subprocess wrapper
│   ├── stub.py            # Catalog-mode thumbnail-with-URL stub generation
│   ├── catalog.py         # Per-folder index.html gallery generation
│   ├── sync_engine.py     # Core orchestrator (backup + catalog modes)
│   ├── providers/         # Per-provider setup (OAuth / S3)
│   └── ui/                # CustomTkinter wizard, main window, password prompt
├── bin/                   # Bundled rclone binary (gitignored; fetched by script)
├── scripts/
│   ├── download_rclone.py # Fetch + checksum rclone binaries
│   └── build.py           # PyInstaller wrapper, per-OS build
├── tests/
└── docs/
```

## USB drive layout (deployment)

What the user copies onto the flash drive:

```
USB_DRIVE/
├── PhotoSync(.exe)        # PyInstaller bundle for the platform
├── PhotoSync/             # ← user content goes here; only this is synced
│   ├── 2024-Trip/
│   │   ├── IMG_0001.jpg
│   │   └── ...
│   └── ...
└── data/                  # created on first run
    ├── rclone.conf        # written encrypted by rclone
    ├── settings.json      # remote, target path, sync mode
    └── sync.db            # SQLite upload history + scan cache
```

`PhotoSync/` and `data/` are created automatically. Anything else on the drive
is ignored — users can keep unrelated files alongside without them being
uploaded.

After a catalog-mode sync the `PhotoSync/` tree looks like:

```
PhotoSync/
├── 2024-Trip/
│   ├── IMG_0001.jpg          # 1024px thumbnail w/ cloud URL in EXIF
│   ├── clip.mp4.preview.jpg  # video frame stub (ffmpeg-extracted or placeholder)
│   └── index.html            # clickable gallery
└── index.html                # top-level catalog
```

## Module responsibilities

### `paths.py`

Detects PyInstaller bundles via `sys.frozen`. When frozen, the app root is
`Path(sys.executable).parent` (the USB root); in development it's the repo root.
`get_rclone_binary()` returns the correct binary for the current platform.

### `config.py`

Reads/writes `settings.json` (schema below). Writes are atomic (temp file +
replace). The master password is passed through to rclone and never stored here.

```json
{
  "version": 1,
  "remote_name": "my-gdrive",
  "remote_type": "drive",
  "target_path": "PhotoSync/Backup",
  "created_at": "2026-05-27T10:00:00Z"
}
```

### `db.py`

SQLite with two tables. `uploads` is the dedup source of truth (keyed by SHA-256).
`scan_cache` maps `abs_path + (mtime_ns, size)` to a hash so unchanged files are
not re-hashed. Runs `PRAGMA synchronous = NORMAL` for cheap USB flash drives.

```sql
CREATE TABLE uploads (
    sha256 TEXT PRIMARY KEY, filename TEXT NOT NULL, size_bytes INTEGER NOT NULL,
    remote_path TEXT NOT NULL, uploaded_at TEXT NOT NULL);
CREATE INDEX idx_filename ON uploads(filename);
CREATE TABLE scan_cache (
    abs_path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL, cached_at TEXT NOT NULL);
```

### `hasher.py` _(Phase 1)_

`sha256_file(path, chunk_size=1MB, progress_cb=None)`. Reuses the scan cache when
`(mtime, size)` match — a large win on re-runs.

### `scanner.py` _(Phase 1)_

`find_media_files(root)` over a photo/video extension whitelist with a magic-byte
check. Skips symlinks, hidden/system folders (`.Trash`, `System Volume
Information`), and crucially the drive's own `data/` folder.

### `rclone_client.py` _(Phase 1)_

All rclone subprocess calls funnel through here, always `shell=False` with an
argument list, `--config <path>`, and `--ask-password=false`. The master password
is passed via the `RCLONE_CONFIG_PASS` environment variable and cleared afterward.

| Purpose             | Command                                                             |
| ------------------- | ------------------------------------------------------------------- |
| OAuth headless auth | `rclone authorize <type>`                                           |
| Create config       | `rclone config create <name> <type> <key=value...>`                 |
| Remote hash listing | `rclone lsjson <remote>:<path> --hash --hash-type SHA-256 -R`       |
| Upload one file     | `rclone copyto <local> <remote>:<path> --progress --stats-one-line` |
| Connection test     | `rclone lsd <remote>:`                                              |

### `sync_engine.py`

For each scanned file: look up the cached hash (or compute + cache it), check
`uploads` — skip if present, otherwise `copyto` and record on success. MVP runs
serially; a worker pool is a v1.1 item.

In **catalog mode**, after a successful upload the engine calls
`stub.write_stub()` to atomically replace the original with a thumbnail-with-URL
JPEG, then records the _stub's_ hash in `uploads` so the next scan recognises
it as already-synced. As an extra safety net, before hashing each file the
engine asks `stub.is_stub()` — files that already carry our EXIF marker are
skipped even if the SQLite DB has been wiped. At the end of a catalog sync
the engine walks the source dir once, collects every stub it finds, and asks
`catalog.regenerate()` to write the per-folder and root `index.html` files.

### `stub.py`

Catalog-mode stub generation, built on Pillow.

- **Photos** keep their original path. The file is replaced with a JPEG
  thumbnail (default 1024 px longest edge, quality 85) carrying our magic
  marker `PHOTOSYNC_STUB_V1` and the cloud URL in the EXIF `UserComment` tag
  (`0x9286`).
- **Videos** are renamed to `<original>.preview.jpg` and the original is
  deleted — file explorers can't pretend a JPEG is a video, so changing the
  extension is honest. A representative frame is extracted with a bundled
  `ffmpeg` if present, otherwise a generic "Video" placeholder is drawn.
- `parse_stub(path)` returns the URL + original name for any of our stubs and
  `None` for everything else. The check reads only EXIF, not the whole file.

### `catalog.py`

Static HTML gallery generation. No JS, single `<style>` block, escapes all
user-controlled text. For each folder of stubs it writes an `index.html`
listing `<a href="cloud-url"><img src="thumb"></a>` cards in a responsive grid;
the source root gets a top-level `index.html` linking to every sub-folder's
gallery. Opening the HTML offline still shows the thumbnails; clicking a tile
opens the cloud URL in the browser, which gives you the full-resolution file.

### `providers/`

Each provider implements the `CloudProvider` interface (`setup_params()` +
`get_target_path_label()`). OAuth providers shell out to `rclone authorize`;
S3-compatible providers collect endpoint/keys/region/bucket with presets for
B2, R2, and Wasabi.

The wizard ships with Google Drive, Dropbox, OneDrive, and S3-compatible. Any
of rclone's [70+ backends](https://rclone.org/overview/) can be added in ~10
lines — see [CONTRIBUTING.md → Adding a cloud provider](CONTRIBUTING.md#adding-a-cloud-provider).

### `ui/` _(Phase 2)_

A four-screen wizard (provider → auth → target path → master password), a master
password prompt, and the main sync window (statistics, current file + progress
bar, start/stop).

## Sync flow

1. Prompt for the master password; set `RCLONE_CONFIG_PASS`.
2. Scan the drive into a file list.
3. Initialize the UI (totals, counters, progress).
4. Per file: cache lookup → hash if needed → `is_uploaded?` skip, else upload and
   record; count failures.
5. Show a summary. The "match percentage" shown to the user is
   `skipped / total * 100` — i.e. how much of the drive was already in the cloud.

## Security model

| Threat                                      | Mitigation                                                 |
| ------------------------------------------- | ---------------------------------------------------------- |
| Stolen drive → attacker reuses cloud tokens | rclone config is password-encrypted; won't open blind      |
| Drive plugged into another PC → auto-sync   | No auto-run; nothing happens without the password          |
| Master password brute force                 | rclone's obscure mechanism is weak; consider argon2 (v1.1) |
| `sync.db` leak (hashes + filenames exposed) | Accepted as low sensitivity; optional DB encryption later  |
| MITM                                        | rclone uses HTTPS with certificate validation              |
| Subprocess injection via rclone args        | All calls use `shell=False` + argument lists               |

**Deliberately not done:** OS keychain/credential storage (incompatible with a
portable drive) and auto-update (users download new releases manually).

## Development roadmap

| Phase | Scope                                                                     | Est.  |
| ----- | ------------------------------------------------------------------------- | ----- |
| 0     | Scaffolding: layout, tooling, `paths`/`config`/`db` + tests, rclone fetch | 1 wk  |
| 1     | Core sync (no UI): `scanner`, `hasher`, `rclone_client`; B2 end-to-end    | 2 wks |
| 2     | UI: CustomTkinter wizard, main window, master-password flow               | 3 wks |
| 3     | OAuth providers: Google Drive, Dropbox, OneDrive                          | 2 wks |
| 4     | Polish & build: PyInstaller for 3 OSes, CI, docs, v1.0 release            | 2 wks |

**All phases are complete.** The application is MVP-ready with 60 passing tests.

## Known pitfalls

1. rclone OAuth uses `localhost:53682`; handle the port-in-use failure and the
   `--auth-no-open-browser` fallback.
2. macOS Gatekeeper blocks unsigned binaries — document "open anyway" unless an
   Apple Developer certificate is purchased.
3. Windows SmartScreen shows "Unknown publisher" without code signing.
4. Windows 260-char path limit / unicode names — normalize long paths.
5. HEIC needs `pillow-heif` to _decode_, but we only hash bytes, so it's a non-issue.
6. `rclone copyto --progress` parsing is fragile — pin the rclone version and
   ship it in `bin/`; revisit parsing on version bumps.
7. Cheap USB drives have slow random writes — `PRAGMA synchronous = NORMAL`, never
   `FULL`.
8. FAT32 has a 4 GB file-size limit — recommend exFAT in the README for big videos.
