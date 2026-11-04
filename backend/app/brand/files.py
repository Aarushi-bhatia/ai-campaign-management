"""Storing a brand's files: which files count, what kind each is, and where it lives on disk."""

import fnmatch
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DOCUMENT_SUFFIXES = {".md", ".markdown", ".txt"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
DATA_SUFFIXES = {".json", ".csv", ".yaml", ".yml"}


class UnsafePath(ValueError):
    pass


@dataclass(frozen=True)
class IncomingFile:
    path: str
    """Relative to the brand folder, with forward slashes."""
    content: bytes


def kind_of(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in DATA_SUFFIXES:
        return "data"
    return "other"


def clean_path(raw: str) -> str:
    """Normalizes an uploaded path and refuses anything that could escape the brand folder."""
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise UnsafePath(raw)
    return str(path)


def is_hidden(path: str) -> bool:
    return any(part.startswith(".") for part in PurePosixPath(path).parts)


def is_excluded(path: str, patterns: list[str]) -> bool:
    """True when the path, or any folder above it, matches one of the patterns."""
    parts = PurePosixPath(path).parts
    candidates = [path, *("/".join(parts[: i + 1]) for i in range(len(parts) - 1))]
    return any(fnmatch.fnmatch(candidate, pattern) for pattern in patterns for candidate in candidates)


def strip_common_root(files: list[IncomingFile]) -> list[IncomingFile]:
    """A browser folder upload prefixes every path with the chosen folder's name. Drop it."""
    roots = {PurePosixPath(f.path).parts[0] for f in files if len(PurePosixPath(f.path).parts) > 1}
    if len(roots) != 1 or any(len(PurePosixPath(f.path).parts) == 1 for f in files):
        return files
    return [IncomingFile(str(PurePosixPath(*PurePosixPath(f.path).parts[1:])), f.content) for f in files]


def read_folder(folder: Path) -> list[IncomingFile]:
    return [
        IncomingFile(str(path.relative_to(folder).as_posix()), path.read_bytes())
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    ]


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def storage_path(data_dir: Path, brand_id: int, path: str) -> Path:
    return data_dir / "brands" / str(brand_id) / path
