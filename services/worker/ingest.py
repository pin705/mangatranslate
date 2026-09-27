"""Untrusted upload handling. Nothing here trusts filenames, extensions or client MIME types.

- file type from magic bytes only (PNG, JPEG, WebP, ZIP/CBZ)
- archives are read in memory (entry names never touch the filesystem → no Zip Slip); entries with absolute
  paths or '..' are rejected anyway, and entry count, per-entry size, total size and compression ratio are capped
  (zip bombs)
- images are fully decoded with a pixel cap before acceptance (decompression bombs, truncated files)
"""

import io
import re
import zipfile
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_ENTRIES = 2000
MAX_ENTRY_BYTES = 60 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_RATIO = 100  # uncompressed / compressed, per entry
IMAGE_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


class InvalidUpload(Exception):
    """User-caused, not retryable."""


@dataclass
class PageImage:
    name: str
    data: bytes
    kind: str  # png | jpeg | webp
    width: int
    height: int


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    return None


def check_image(name: str, data: bytes, max_pixels: int) -> PageImage:
    kind = sniff(data)
    if kind not in IMAGE_TYPES:
        raise InvalidUpload(f"{name}: not a PNG/JPEG/WebP image")
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if w * h > max_pixels or w < 16 or h < 16:
                raise InvalidUpload(f"{name}: image dimensions {w}x{h} are not allowed")
            im.load()  # full decode catches truncated/corrupt files
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as e:
        raise InvalidUpload(f"{name}: unreadable image") from e
    return PageImage(name=name, data=data, kind=kind, width=w, height=h)


def _natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def extract_archive(name: str, data: bytes, max_pixels: int, max_pages: int) -> list[PageImage]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise InvalidUpload(f"{name}: corrupt archive") from e
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise InvalidUpload(f"{name}: too many files in archive")
    total = 0
    pages = []
    for info in sorted(infos, key=lambda i: _natural(i.filename)):
        fname = info.filename.replace("\\", "/")
        base = fname.rsplit("/", 1)[-1]
        if info.is_dir() or fname.startswith("__MACOSX/") or base.startswith("."):
            continue
        if fname.startswith("/") or ".." in fname.split("/") or re.match(r"^[a-zA-Z]:", fname):
            raise InvalidUpload(f"{name}: unsafe path in archive")
        if info.flag_bits & 0x1:
            raise InvalidUpload(f"{name}: encrypted archives are not supported")
        if info.file_size > MAX_ENTRY_BYTES or info.file_size > MAX_RATIO * max(info.compress_size, 1):
            raise InvalidUpload(f"{name}: archive entry too large")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise InvalidUpload(f"{name}: archive too large when extracted")
        if not re.search(r"\.(png|jpe?g|webp)$", base, re.I):
            continue  # ComicInfo.xml, thumbs, etc.
        with zf.open(info) as f:
            content = f.read(MAX_ENTRY_BYTES + 1)  # never trust the header's declared size
        if len(content) > MAX_ENTRY_BYTES:
            raise InvalidUpload(f"{name}: archive entry too large")
        pages.append(check_image(base, content, max_pixels))
        if len(pages) > max_pages:
            raise InvalidUpload("too many pages")
    return pages


def pages_from_upload(name: str, data: bytes, max_pixels: int, max_pages: int) -> list[PageImage]:
    if sniff(data) == "zip":
        return extract_archive(name, data, max_pixels, max_pages)
    return [check_image(name, data, max_pixels)]

