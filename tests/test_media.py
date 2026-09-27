"""The media pipeline treats every upload as hostile (docs/SECURITY.md, "Uploads").

All fixtures are synthetic: generated gradients with fake camera and GPS metadata, and
hand-written malicious files. No real photo or document is used.
"""

import io
import re
import zipfile

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from PIL import Image

from apps.core import media
from apps.core.models import MediaAsset
from tests import helpers as h

pytestmark = pytest.mark.django_db

ALT = {"alt_text_en": "A generated test gradient"}


def ingest(name, data, content_type="", **fields):
    return media.ingest(h.upload(name, data, content_type), **{**ALT, **fields})


def rejected(name, data, content_type="", match=None):
    with pytest.raises(ValidationError) as excinfo:
        ingest(name, data, content_type)
    if match:
        assert re.search(match, " ".join(excinfo.value.messages), re.IGNORECASE)
    assert MediaAsset.objects.count() == 0


def stored_image(name):
    with default_storage.open(name) as handle:
        image = Image.open(io.BytesIO(handle.read()))
        image.load()
        return image


# ---------------------------------------------------------------------------
# Accepted formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "fmt"),
    [("photo.jpg", "JPEG"), ("photo.jpeg", "JPEG"), ("art.png", "PNG"), ("x.webp", "WEBP")],
)
def test_supported_images_are_accepted(name, fmt):
    asset, created = ingest(name, h.image_bytes(fmt, (1000, 500)))
    assert created
    assert asset.kind == "image"
    assert (asset.width, asset.height) == (1000, 500)


def test_avif_is_accepted():
    asset, _ = ingest("x.avif", h.image_bytes("AVIF", (600, 300), quality=60))
    assert asset.kind == "image"


def test_pdf_is_accepted_and_stored_as_is():
    asset, _ = media.ingest(h.upload("cv.pdf", h.pdf_bytes()))
    assert asset.kind == "pdf"
    assert asset.width is None and asset.variants == {}
    with default_storage.open(asset.file.name) as handle:
        assert handle.read() == h.pdf_bytes()


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["tool.exe", "photo.gif", "page.html", "noextension", "x.heic"])
def test_extensions_outside_the_allowlist_are_rejected(name):
    rejected(name, h.image_bytes(), match="unsupported file type")


def test_svg_is_rejected_by_extension_and_by_content():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    rejected("logo.svg", svg, match="unsupported file type")
    rejected("logo.png", svg, match="not a supported image")


def test_wrong_magic_bytes_are_rejected():
    rejected("photo.jpg", b"definitely not an image, just text", match="not a supported image")


def test_extension_must_match_content():
    rejected("photo.jpg", h.image_bytes("PNG"), match="extension does not match")


def test_declared_content_type_must_not_contradict_content():
    rejected("photo.jpg", h.image_bytes(), content_type="image/svg+xml", match="content type")


def test_oversize_files_are_rejected(monkeypatch):
    monkeypatch.setattr(media, "MAX_IMAGE_BYTES", 10_000)
    rejected("photo.jpg", h.image_bytes(), match="larger than")


def test_script_appended_to_an_image_is_rejected():
    rejected("photo.jpg", h.image_bytes() + b"<script>alert(1)</script>", match="scripting")


def test_html_disguised_as_png_is_rejected():
    rejected("x.png", h.image_bytes("PNG") + b"<html><body>hi</body></html>")


def test_zip_polyglot_jpeg_is_rejected():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("payload.txt", "pretend this is dangerous")
    rejected("photo.jpg", h.image_bytes() + archive.getvalue(), match="archive or executable")


def test_png_with_trailing_data_is_rejected():
    rejected("x.png", h.image_bytes("PNG") + b"\x00trailing", match="after its end")


def test_truncated_image_is_rejected():
    data = h.image_bytes()
    rejected("photo.jpg", data[: len(data) * 2 // 3])


def test_decompression_bomb_is_rejected():
    buffer = io.BytesIO()
    Image.new("1", (10_000, 6_000)).save(buffer, "PNG")  # 60 MP in a small file
    rejected("bomb.png", buffer.getvalue(), match="too many pixels")


def test_animated_images_are_rejected():
    rejected("anim.webp", h.animated_webp(), match="animated")


def test_pdf_with_javascript_is_rejected():
    rejected("cv.pdf", h.pdf_bytes(b"3 0 obj << /S /JavaScript /JS (app.alert(1)) >> endobj"))


def test_incomplete_pdf_is_rejected():
    rejected("cv.pdf", h.pdf_bytes().replace(b"%%EOF", b""), match="incomplete")


def test_images_require_english_alt_text():
    with pytest.raises(ValidationError):
        media.ingest(h.upload("photo.jpg", h.image_bytes()))
    assert MediaAsset.objects.count() == 0


def test_a_rejected_upload_leaves_no_files(isolated_media):
    rejected("photo.jpg", h.image_bytes() + b"<?php system($_GET['c']); ?>")
    written = (
        [p for p in isolated_media.rglob("*") if p.is_file()] if isolated_media.exists() else []
    )
    assert written == []


# ---------------------------------------------------------------------------
# Sanitising
# ---------------------------------------------------------------------------


def test_exif_and_gps_are_stripped():
    source = h.jpeg_with_gps()
    # The fixture really carries a camera name and GPS coordinates...
    assert h.FAKE_CAMERA.encode() in source
    assert Image.open(io.BytesIO(source)).getexif().get_ifd(0x8825)
    asset, _ = ingest("photo.jpg", source)
    # ...and none of it survives, in the master or in any variant.

    for name in media.asset_file_names(asset):
        with default_storage.open(name) as handle:
            data = handle.read()
        assert h.FAKE_CAMERA.encode() not in data
        image = Image.open(io.BytesIO(data))
        exif = image.getexif()
        assert len(exif) == 0
        assert not exif.get_ifd(0x8825)  # no GPS
        assert "exif" not in image.info and "xmp" not in image.info


def test_exif_orientation_is_applied_before_stripping():
    asset, _ = ingest("photo.jpg", h.jpeg_with_gps((400, 200), orientation=6))
    assert (asset.width, asset.height) == (200, 400)
    assert stored_image(asset.file.name).size == (200, 400)


def test_colour_profiles_are_converted_and_dropped():
    asset, _ = ingest("photo.jpg", h.jpeg_with_srgb_profile())
    assert "icc_profile" not in stored_image(asset.file.name).info


def test_the_stored_file_is_re_encoded_not_the_upload():
    source = h.jpeg_with_gps((600, 300))
    asset, _ = ingest("photo.jpg", source)
    with default_storage.open(asset.file.name) as handle:
        assert handle.read() != source


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


def test_variants_at_every_standard_width_for_a_large_image():
    asset, _ = ingest("photo.jpg", h.image_bytes(size=(2400, 1200)))
    for fmt in ("avif", "webp"):
        assert asset.variant_widths(fmt) == [480, 960, 1440, 1920]
        for width in asset.variant_widths(fmt):
            image = stored_image(asset.variants[fmt][str(width)])
            assert image.format == fmt.upper()
            assert image.width == width
            assert image.height == round(1200 * width / 2400)  # aspect ratio kept


def test_no_variant_is_larger_than_the_source():
    asset, _ = ingest("photo.jpg", h.image_bytes(size=(1000, 500)))
    assert asset.variant_widths("webp") == [480, 960]
    assert asset.variant_widths("avif") == [480, 960]


def test_a_small_image_is_never_upscaled():
    asset, _ = ingest("photo.jpg", h.image_bytes(size=(300, 200)))
    assert asset.variant_widths("webp") == [300]
    assert stored_image(asset.variants["webp"]["300"]).size == (300, 200)


def test_focal_point_is_kept():
    asset, _ = ingest("photo.jpg", h.image_bytes(), focal_x=0.3, focal_y=0.2)
    asset.refresh_from_db()
    assert (asset.focal_x, asset.focal_y) == (0.3, 0.2)


def test_focal_point_outside_the_image_is_rejected():
    with pytest.raises(ValidationError):
        ingest("photo.jpg", h.image_bytes(), focal_x=1.5)


# ---------------------------------------------------------------------------
# Names, deduplication, deletion
# ---------------------------------------------------------------------------


def test_stored_names_are_server_chosen():
    asset, _ = ingest("../../../etc/passwd.jpg", h.image_bytes(size=(600, 300)))
    assert re.fullmatch(r"images/[0-9a-f]{32}\.jpg", asset.file.name)
    for name in media.asset_file_names(asset):
        assert "passwd" not in name and ".." not in name


def test_the_same_file_twice_is_one_asset():
    data = h.image_bytes(size=(600, 300))
    first, created = ingest("a.jpg", data)
    second, created_again = ingest("b.jpg", data)
    assert created and not created_again
    assert first.pk == second.pk
    assert MediaAsset.objects.count() == 1


def test_deleting_an_asset_removes_its_files(django_capture_on_commit_callbacks):
    asset, _ = ingest("photo.jpg", h.image_bytes(size=(1000, 500)))
    names = media.asset_file_names(asset)
    assert all(default_storage.exists(name) for name in names)
    with django_capture_on_commit_callbacks(execute=True):
        asset.delete()
    assert not any(default_storage.exists(name) for name in names)
