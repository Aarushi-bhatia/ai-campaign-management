"""Preloading a brand folder on start. Group 4 of the design review (#5)."""

from pathlib import Path
from types import SimpleNamespace

from app.brand.startup import _preload


class Brands:
    def __init__(self, sources: dict[str, str]) -> None:
        self.sources, self.created = sources, []

    def find_by_source(self, source: str):
        return self.sources.get(source)

    def create(self, name, files, exclude, source=None):
        self.created.append((name, source))


def _settings(folder: Path, source: str, name: str = "") -> SimpleNamespace:
    return SimpleNamespace(brand_dir=folder, brand_source=source, brand_name=name, brand_exclude_patterns=[])


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "preload-brand"  # Docker mounts every BRAND_DIR here
    folder.mkdir()
    (folder / "guide.md").write_text("# Guide\n\nWrite short sentences.\n")
    return folder


def test_a_different_brand_folder_is_preloaded_as_a_new_brand(tmp_path: Path):
    """Inside Docker the folder is always at the same place, so a second BRAND_DIR was taken for the first."""
    folder = _folder(tmp_path)
    brands = Brands({"folder:../acme-brand": "Acme"})

    _preload(brands, _settings(folder, "../wickhold-brand"))

    assert brands.created == [("wickhold-brand", "folder:../wickhold-brand")]  # was skipped, and named "preload-brand"


def test_the_same_folder_is_not_preloaded_twice(tmp_path: Path):
    folder = _folder(tmp_path)
    brands = Brands({"folder:../acme-brand": "Acme"})

    _preload(brands, _settings(folder, "../acme-brand"))

    assert brands.created == []


def test_a_brand_preloaded_before_folders_were_told_apart_is_not_read_again(tmp_path: Path):
    """Its source is the mount, so it can't be matched to a folder; reading it again unasked would cost a full read."""
    folder = _folder(tmp_path)
    brands = Brands({str(folder.resolve()): "Acme"})

    _preload(brands, _settings(folder, "../acme-brand"))

    assert brands.created == []
