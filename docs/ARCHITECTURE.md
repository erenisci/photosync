# PhotoSync Architecture

PhotoSync is a portable application that runs from a USB flash drive and uploads
the drive's photos and videos to a chosen cloud provider, skipping anything that
has already been uploaded. File transfer is delegated to
[rclone](https://rclone.org/); PhotoSync orchestrates scanning, hashing,
deduplication, and the user interface.

## Goals & non-goals

**In scope**

- Scan photo/video files (extension whitelist + magic-byte check).
- Compute SHA-256 hashes with a local scan cache.
- Deduplicate against a local SQLite history and the remote.
- Support Google Drive, Dropbox, OneDrive, and S3-compatible stores (B2, R2, …).
- First-run setup wizard, per-file progress, master-password-encrypted creds.
- Cross-platform: Windows, macOS, Linux. Single binary (<50 MB).
- Resume after interrupted network transfers.

**Out of scope (at least for MVP)**

- iCloud (overly restrictive API).
- Perceptual / near-duplicate detection.
- Two-way sync or cloud → drive download.
- Fan-out to multiple clouds at once.

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
│   ├── main.py            # Entry point: wizard vs. password prompt vs. main window
│   ├── paths.py           # USB root / bundle resolution, rclone binary lookup
│   ├── config.py          # settings.json read/write
│   ├── db.py              # SQLite operations (uploads + scan_cache)
│   ├── hasher.py          # SHA-256 chunked hashing            [Phase 1]
│   ├── scanner.py         # Media file discovery               [Phase 1]
│   ├── rclone_client.py   # rclone subprocess wrapper          [Phase 1]
│   ├── sync_engine.py     # Core sync orchestrator             [Phase 1]
│   ├── providers/         # Per-provider setup (OAuth / S3)    [Phase 3]
│   └── ui/                # CustomTkinter wizard & main window [Phase 2]
├── bin/                   # Bundled rclone binaries (gitignored; fetched by script)
├── scripts/
│   ├── download_rclone.py # Fetch + checksum rclone binaries
│   └── build.py           # PyInstaller wrapper, per-OS build  [Phase 4]
├── tests/
└── docs/
```

## USB drive layout (deployment)

What the user copies onto the flash drive:

```
USB_DRIVE/
├── PhotoSync(.exe)        # PyInstaller bundle for the platform
├── bin/                   # rclone.exe / rclone-mac / rclone-linux
├── data/                  # created on first run
│   ├── rclone.conf        # written encrypted by rclone
│   ├── settings.json      # app settings (remote choice, target path)
│   └── sync.db            # SQLite upload history + scan cache
└── README.txt
```

`data/` is created on first run, so the release zip stays minimal.

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

### `sync_engine.py` _(Phase 1)_

For each scanned file: look up the cached hash (or compute + cache it), check
`uploads` — skip if present, otherwise `copyto` and record on success. MVP runs
serially; a worker pool is a v1.1 item.

### `providers/` _(Phase 3)_

Each provider implements a `CloudProvider` interface (`setup_interactive()`,
`get_target_path_label()`). OAuth providers shell out to `rclone authorize`;
S3-compatible providers collect endpoint/keys/region/bucket with presets for
B2, R2, and Wasabi.

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

**Phase 0 is complete.** Proceed one phase at a time, pausing for review at each
boundary.

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
