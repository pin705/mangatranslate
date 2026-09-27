"""Fast checks that need no models, database or network."""

import io
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

WORKER = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(WORKER), str(WORKER.parent / "api")]

import ingest  # noqa: E402


def test_translation_validation():
    from ai import validate

    batch = {"a": "你好，师姐", "b": "谢谢", "c": "{name}来了", "d": "走吧"}
    reply = {"translations": {"a": "Chào sư tỷ", "b": "谢谢", "c": "Hắn tới rồi", "x": "extra", "d": "Đi thôi" * 30}}
    ok, retry, flagged = validate(batch, reply, "Vietnamese")
    assert ok == {"a": "Chào sư tỷ", "c": "Hắn tới rồi", "d": "Đi thôi" * 30}
    assert retry == {"b"}  # left untranslated
    assert flagged == {"c", "d"}  # lost placeholder, suspiciously long
    assert validate(batch, {"oops": 1}, "Vietnamese")[1] == set(batch)
    assert validate({"a": "x"}, {"translations": {"a": "bad�"}}, "English")[1] == {"a"}


def _png(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_archive_natural_order_and_junk_skipped():
    pages = ingest.pages_from_upload("c.cbz", _zip({"p10.png": _png(), "p2.png": _png(), "__MACOSX/p1.png": b"x",
                                                    "ComicInfo.xml": b"<x/>"}), 10**7, 100)
    assert [p.name for p in pages] == ["p2.png", "p10.png"]


@pytest.mark.parametrize("data", [
    _zip({"../evil.png": _png()}),                         # path traversal
    _zip({"/abs.png": _png()}),                            # absolute path
    _zip({"bomb.png": b"\0" * (50 * 1024 * 1024)}),        # compression ratio bomb
    _zip({"fake.png": b"<html>not an image</html>"}),       # extension lies
    b"GIF89a" + b"\0" * 64,                                # unsupported type
    b"\x89PNG\r\n\x1a\n" + b"\0" * 64,                     # truncated image
])
def test_rejects_malicious_uploads(data):
    with pytest.raises(ingest.InvalidUpload):
        ingest.pages_from_upload("x", data, 10**7, 100)


def test_pixel_and_page_caps():
    with pytest.raises(ingest.InvalidUpload):
        ingest.check_image("big.png", _png((5000, 5000)), 10**7)
    with pytest.raises(ingest.InvalidUpload):
        ingest.pages_from_upload("c.zip", _zip({f"{i}.png": _png() for i in range(5)}), 10**7, 3)


def test_learned_terms_are_grounded_and_new():
    from ai import new_terms

    lines = {"a": "师姐，快走！", "b": "青云宗的弟子"}
    reply = {"terms": [{"source": "师姐", "target": "sư tỷ"}, {"source": "青云宗", "target": "Thanh Vân Tông"},
                       {"source": "天帝", "target": "Thiên Đế"},          # not in the chapter: hallucinated
                       {"source": "弟子", "target": "弟子"},              # left untranslated
                       "junk"]}
    got = new_terms(reply, lines, [{"source": "师姐", "target": "sư tỷ"}], "Vietnamese")
    assert got == [{"source": "青云宗", "target": "Thanh Vân Tông", "auto": True}]
