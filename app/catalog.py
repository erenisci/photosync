"""HTML catalog generation for catalog-mode syncs.

Each folder under the source directory gets an ``index.html`` listing the
thumbnails inside it as a clickable gallery — each thumbnail links to the
original's URL in the cloud. The source root also gets a top-level
``index.html`` that links to every sub-folder.

The HTML is intentionally dependency-free (no JS, single ``<style>``) so it
works offline in any browser and renders fine on slow machines.
"""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.paths import atomic_write_text

logger = logging.getLogger(__name__)

INDEX_FILENAME = "index.html"


@dataclass(frozen=True)
class CatalogEntry:
    """One row in the catalog: a thumbnail file pointing at a cloud URL."""

    thumbnail_path: Path  # absolute path to the on-drive thumbnail
    cloud_url: str  # where clicking the thumbnail should take the user
    original_name: str  # display name (e.g. "IMG_0001.jpg")


_PAGE_STYLE = """
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
       Roboto, sans-serif; background: #111; color: #eee; }
header { padding: 18px 24px; border-bottom: 1px solid #222; }
header h1 { margin: 0; font-size: 20px; font-weight: 600; }
header p { margin: 4px 0 0; color: #888; font-size: 13px; }
.gallery { display: grid; gap: 8px; padding: 16px;
           grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }
.gallery a { display: block; aspect-ratio: 1; overflow: hidden;
             background: #222; border-radius: 6px; position: relative; }
.gallery img { width: 100%; height: 100%; object-fit: cover; display: block;
               transition: transform .2s; }
.gallery a:hover img { transform: scale(1.05); }
.gallery .name { position: absolute; bottom: 0; left: 0; right: 0;
                 padding: 6px 8px; font-size: 11px; background: rgba(0,0,0,.6);
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.folders { padding: 16px; }
.folders a { display: block; padding: 12px 16px; margin: 6px 0;
             background: #1a1a1a; color: #eee; text-decoration: none;
             border-radius: 6px; }
.folders a:hover { background: #222; }
.empty { padding: 32px; color: #666; text-align: center; }
"""


def _page(title: str, subtitle: str, body: str) -> str:
    """Wrap ``body`` in the shared page chrome."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{_PAGE_STYLE}</style>\n"
        "</head>\n<body>\n"
        "<header>\n"
        f"  <h1>{html.escape(title)}</h1>\n"
        f"  <p>{html.escape(subtitle)}</p>\n"
        "</header>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def write_folder_index(folder: Path, entries: list[CatalogEntry]) -> Path:
    """Write an ``index.html`` gallery for ``folder``.

    Returns the path of the written file. Entries are sorted by original name
    so the gallery order matches the original on-disk order.
    """
    sorted_entries = sorted(entries, key=lambda e: e.original_name.lower())
    title = f"PhotoSync — {folder.name or 'Library'}"
    subtitle = (
        f"{len(sorted_entries)} item(s) in this folder. "
        "Click a thumbnail to open the original from the cloud."
    )

    if not sorted_entries:
        body = '<div class="empty">No catalogued files in this folder yet.</div>'
    else:
        rows = []
        for entry in sorted_entries:
            try:
                rel = entry.thumbnail_path.relative_to(folder).as_posix()
            except ValueError:
                rel = entry.thumbnail_path.name
            url = html.escape(entry.cloud_url, quote=True)
            src = html.escape(rel, quote=True)
            # quote=True so a filename containing `"` can't break out of the
            # title="…" / alt="…" attributes and inject HTML.
            name = html.escape(entry.original_name, quote=True)
            rows.append(
                f'<a href="{url}" target="_blank" rel="noopener" title="{name}">'
                f'<img src="{src}" alt="{name}" loading="lazy">'
                f'<span class="name">{name}</span>'
                "</a>"
            )
        body = '<div class="gallery">\n' + "\n".join(rows) + "\n</div>"

    index_path = folder / INDEX_FILENAME
    atomic_write_text(index_path, _page(title, subtitle, body))
    return index_path


def write_root_index(root: Path, folders: list[Path]) -> Path:
    """Write a top-level ``index.html`` linking to every sub-folder's index."""
    sorted_folders = sorted({f for f in folders if f != root}, key=lambda p: p.name.lower())
    title = "PhotoSync Catalog"
    subtitle = f"{len(sorted_folders)} folder(s). Open a folder to browse its files."

    if not sorted_folders:
        body = '<div class="empty">No catalogued folders yet — run a sync to populate this.</div>'
    else:
        rows = []
        for sub in sorted_folders:
            try:
                rel = (sub / INDEX_FILENAME).relative_to(root).as_posix()
            except ValueError:
                rel = f"{sub.name}/{INDEX_FILENAME}"
            rows.append(
                f'<a href="{html.escape(rel, quote=True)}">'
                f"📁 {html.escape(sub.name, quote=True)}</a>"
            )
        body = '<div class="folders">\n' + "\n".join(rows) + "\n</div>"

    index_path = root / INDEX_FILENAME
    atomic_write_text(index_path, _page(title, subtitle, body))
    return index_path


def group_entries_by_folder(entries: list[CatalogEntry]) -> dict[Path, list[CatalogEntry]]:
    """Group entries by the folder their thumbnail lives in."""
    grouped: dict[Path, list[CatalogEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.thumbnail_path.parent].append(entry)
    return dict(grouped)


def regenerate(root: Path, entries: list[CatalogEntry]) -> list[Path]:
    """Regenerate every ``index.html`` under ``root`` for the given entries.

    Returns the list of paths written.
    """
    written: list[Path] = []
    grouped = group_entries_by_folder(entries)
    for folder, folder_entries in grouped.items():
        try:
            written.append(write_folder_index(folder, folder_entries))
        except OSError as exc:
            logger.warning("Failed to write %s/index.html: %s", folder, exc)
    try:
        written.append(write_root_index(root, list(grouped.keys())))
    except OSError as exc:
        logger.warning("Failed to write root index.html: %s", exc)
    return written
