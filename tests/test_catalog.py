"""Tests for app.catalog — HTML gallery generation."""

from __future__ import annotations

from pathlib import Path

from app import catalog
from app.catalog import CatalogEntry


def _entry(
    path: Path, url: str = "https://cloud.example/x.jpg", name: str = "x.jpg"
) -> CatalogEntry:
    return CatalogEntry(thumbnail_path=path, cloud_url=url, original_name=name)


def test_folder_index_lists_each_entry(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").touch()
    (tmp_path / "b.jpg").touch()
    entries = [
        _entry(tmp_path / "a.jpg", url="https://cloud/a.jpg", name="a.jpg"),
        _entry(tmp_path / "b.jpg", url="https://cloud/b.jpg", name="b.jpg"),
    ]
    out = catalog.write_folder_index(tmp_path, entries)
    html_text = out.read_text(encoding="utf-8")
    assert "https://cloud/a.jpg" in html_text
    assert "https://cloud/b.jpg" in html_text
    assert 'src="a.jpg"' in html_text
    assert 'src="b.jpg"' in html_text


def test_folder_index_escapes_html_in_filenames(tmp_path: Path) -> None:
    f = tmp_path / "evil.jpg"
    f.touch()
    entries = [_entry(f, url="https://cloud/x", name='<script>alert("xss")</script>.jpg')]
    out = catalog.write_folder_index(tmp_path, entries)
    text = out.read_text(encoding="utf-8")
    assert "<script>" not in text  # Must be escaped, not raw.
    assert "&lt;script&gt;" in text


def test_folder_index_empty(tmp_path: Path) -> None:
    out = catalog.write_folder_index(tmp_path, [])
    text = out.read_text(encoding="utf-8")
    assert "No catalogued files" in text


def test_root_index_lists_subfolders(tmp_path: Path) -> None:
    (tmp_path / "trip").mkdir()
    (tmp_path / "wedding").mkdir()
    out = catalog.write_root_index(tmp_path, [tmp_path / "trip", tmp_path / "wedding"])
    text = out.read_text(encoding="utf-8")
    assert "trip/index.html" in text
    assert "wedding/index.html" in text


def test_group_entries_by_folder(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    entries = [
        _entry(tmp_path / "a" / "1.jpg"),
        _entry(tmp_path / "a" / "2.jpg"),
        _entry(tmp_path / "b" / "3.jpg"),
    ]
    grouped = catalog.group_entries_by_folder(entries)
    assert len(grouped[tmp_path / "a"]) == 2
    assert len(grouped[tmp_path / "b"]) == 1


def test_regenerate_writes_root_and_per_folder(tmp_path: Path) -> None:
    sub = tmp_path / "album"
    sub.mkdir()
    (sub / "x.jpg").touch()
    entries = [_entry(sub / "x.jpg", url="https://cloud/x.jpg", name="x.jpg")]

    written = catalog.regenerate(tmp_path, entries)
    written_names = {p.name for p in written}
    assert written_names == {"index.html"}
    assert (sub / "index.html").is_file()
    assert (tmp_path / "index.html").is_file()
