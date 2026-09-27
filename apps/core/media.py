"""The media pipeline: the only way a file becomes a MediaAsset (docs/SECURITY.md, "Uploads").

Every upload is hostile until proven otherwise:

1. Size is checked before anything is read, and reading stops at the limit.
2. The type comes from the file's magic bytes. The extension must be allowlisted and must agree
   with them; the browser's declared content type must not contradict them.
3. Images must contain no active content (HTML, script, SVG, PHP, an embedded PDF) anywhere, and
   their container must end where the image ends (no smuggled trailing payload).
4. Pillow must fully decode the image, under a pixel limit (decompression bombs).
5. The stored image is rebuilt from pixels alone, after applying the EXIF orientation and
   converting to sRGB: no EXIF, GPS, XMP or ICC data survives.
6. AVIF and WebP variants are resized, never cropped or upscaled.
7. Every stored name is server-chosen (a random token); the uploaded name is never used.

`prepare()` does 1-6 in memory without side effects, so a form can show errors before anything is
written. `store()` writes the files and the row. `ingest()` does both.
"""

import hashlib
import io
import posixpath
import uuid
import warnings
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from apps.core.models import MediaAsset, MediaKind

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PDF_BYTES = 5 * 1024 * 1024
# Above what a 50-megapixel phone camera produces; decoding stays within a small container.
MAX_IMAGE_PIXELS = 50_000_000

VARIANT_WIDTHS = (480, 960, 1440, 1920)
VARIANT_FORMATS = {
    "avif": ("AVIF", {"quality": 60, "speed": 6}),
    "webp": ("WEBP", {"quality": 80, "method": 6}),
}

# Detected type -> allowed extensions, Pillow format, declared content types that agree.
FILE_TYPES = {
    # MPO: multi-picture JPEGs some cameras write; the first picture is the photo.
    "jpeg": ((".jpg", ".jpeg"), {"JPEG", "MPO"}, {"image/jpeg", "image/pjpeg", "image/jpg"}),
    "png": ((".png",), {"PNG"}, {"image/png"}),
    "webp": ((".webp",), {"WEBP"}, {"image/webp"}),
    "avif": ((".avif",), {"AVIF"}, {"image/avif"}),
    "pdf": ((".pdf",), set(), {"application/pdf", "application/x-pdf"}),
}
ALLOWED_EXTENSIONS = {ext for exts, _fmt, _types in FILE_TYPES.values() for ext in exts}
GENERIC_CONTENT_TYPES = {"", "application/octet-stream"}

# The stored master keeps its format family.
MASTER_SAVE = {
    "jpeg": ("JPEG", "jpg", {"quality": 90, "optimize": True, "progressive": True}),
    "png": ("PNG", "png", {"optimize": True}),
    "webp": ("WEBP", "webp", {"quality": 90, "method": 6}),
    "avif": ("AVIF", "avif", {"quality": 80, "speed": 6}),
}

# Markers of content a browser or interpreter would act on. Long enough that random image bytes
# match them with negligible probability.
ACTIVE_CONTENT_MARKERS = (
    b"<script",
    b"<?php",
    b"<html",
    b"<!doctype",
    b"<svg",
    b"<iframe",
    b"javascript:",
    b"%pdf-",
)
PDF_FORBIDDEN_TOKENS = (b"/javascript", b"/launch", b"/embeddedfile", b"/richmedia", b"/xfa")
# Signatures of an archive, executable or document smuggled after the end of a JPEG.
JPEG_TRAILER_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"Rar!", b"7z\xbc\xaf", b"MZ", b"\x7fELF")


def _reject(message):
    raise ValidationError(message, code="invalid_upload")


@dataclass
class PreparedUpload:
    kind: str
    sha256: str
    size: int
    master: bytes
    master_ext: str
    width: int | None = None
    height: int | None = None
    # {"avif": {480: b"..."}, "webp": {480: b"..."}}
    variants: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare(upload, *, content_type=""):
    """Validate and process an upload in memory. Raises ValidationError; writes nothing."""
    name = posixpath.basename((getattr(upload, "name", "") or "").replace("\\", "/"))
    extension = posixpath.splitext(name)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        _reject("Unsupported file type. Upload a JPEG, PNG, WebP or AVIF image, or a PDF.")

    limit = MAX_PDF_BYTES if extension == ".pdf" else MAX_IMAGE_BYTES
    declared_size = getattr(upload, "size", None)
    if declared_size is not None and declared_size > limit:
        _reject(f"The file is larger than the {limit // (1024 * 1024)} MB limit.")
    data = _read_bounded(upload, limit)
    if not data:
        _reject("The file is empty.")

    kind = _sniff(data)
    if kind is None:
        _reject("The file's contents are not a supported image or PDF.")
    extensions, _pillow_format, content_types = FILE_TYPES[kind]
    if extension not in extensions:
        _reject("The file extension does not match the file's contents.")
    declared = (content_type or getattr(upload, "content_type", "") or "").lower()
    if declared not in GENERIC_CONTENT_TYPES and declared not in content_types:
        _reject("The declared content type does not match the file's contents.")

    digest = hashlib.sha256(data).hexdigest()
    if kind == "pdf":
        _check_pdf(data)
        return PreparedUpload("pdf", digest, len(data), master=data, master_ext="pdf")
    return _prepare_image(kind, data, digest)


def store(prepared, *, instance=None, **fields):
    """Write a prepared upload's files and create its MediaAsset.

    `fields` sets the editable fields: alt_text_en, alt_text_ko, caption_en, focal_x, ...
    `instance` is an unsaved MediaAsset already carrying them (the admin's form object).
    Returns (asset, created). An identical file uploaded before returns the existing asset.
    """
    existing = MediaAsset.objects.filter(sha256=prepared.sha256).first()
    if existing:
        return existing, False

    kind = MediaKind.PDF if prepared.kind == "pdf" else MediaKind.IMAGE
    asset = instance if instance is not None else MediaAsset()
    for name, value in fields.items():
        setattr(asset, name, value)
    asset.kind = kind
    asset.width = prepared.width
    asset.height = prepared.height
    asset.bytes = prepared.size
    asset.sha256 = prepared.sha256
    if kind == MediaKind.IMAGE and not (asset.alt_text_en or "").strip():
        raise ValidationError({"alt_text_en": "Images need English alt text."})
    asset.full_clean(exclude=["file", "variants"])

    token = uuid.uuid4().hex
    folder = "documents" if kind == MediaKind.PDF else "images"
    written = []
    try:
        master_name = _save(f"{folder}/{token}.{prepared.master_ext}", prepared.master, written)
        variants = {
            fmt: {
                str(width): _save(f"{folder}/{token}/{width}.{fmt}", data, written)
                for width, data in by_width.items()
            }
            for fmt, by_width in prepared.variants.items()
        }
        asset.file.name = master_name
        asset.variants = variants
        with transaction.atomic():
            asset.save()
    except IntegrityError:
        # The same file was stored concurrently; keep that one.
        _delete_names(written)
        return MediaAsset.objects.get(sha256=prepared.sha256), False
    except Exception:
        _delete_names(written)
        raise
    return asset, True


def ingest(upload, *, content_type="", **fields):
    """prepare() then store(). Returns (asset, created)."""
    return store(prepare(upload, content_type=content_type), **fields)


def asset_file_names(asset):
    """Every stored file belonging to an asset: the master and all variants."""
    names = [asset.file.name] if asset.file else []
    for by_width in (asset.variants or {}).values():
        names.extend(by_width.values())
    return names


# ---------------------------------------------------------------------------
# Reading and identification
# ---------------------------------------------------------------------------


def _read_bounded(upload, limit):
    buffer = bytearray()
    if hasattr(upload, "seek"):
        upload.seek(0)
    chunks = upload.chunks() if hasattr(upload, "chunks") else iter(lambda: upload.read(65536), b"")
    for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > limit:
            _reject(f"The file is larger than the {limit // (1024 * 1024)} MB limit.")
    return bytes(buffer)


def _sniff(data):
    """Identify a file by its magic bytes alone."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        box_size = int.from_bytes(data[0:4], "big")
        brands = {data[8:12]} | {
            data[i : i + 4] for i in range(16, min(box_size, len(data)) - 3, 4)
        }
        if brands & {b"avif", b"avis"}:
            return "avif"
        return None
    if data.startswith(b"%PDF-"):
        return "pdf"
    return None


# ---------------------------------------------------------------------------
# Structural checks: where does the image really end?
# ---------------------------------------------------------------------------


def _check_active_content(data):
    lowered = data.lower()
    if any(marker in lowered for marker in ACTIVE_CONTENT_MARKERS):
        _reject("The file contains embedded scripting or markup and was rejected.")


def _check_container(kind, data):
    if kind == "png":
        end = _png_end(data)
        if end is None:
            _reject("The PNG file is malformed.")
        if end != len(data):
            _reject("The PNG file has data after its end and was rejected.")
    elif kind == "jpeg":
        end = _jpeg_end(data)
        if end is None:
            _reject("The JPEG file is malformed.")
        trailer = data[end:]
        # Some phones append a motion clip after the image; re-encoding discards it. An archive,
        # executable or document hidden there is a polyglot and is refused outright.
        if trailer.startswith(JPEG_TRAILER_SIGNATURES) or b"PK\x05\x06" in data[-65557:]:
            _reject("The JPEG file carries an embedded archive or executable and was rejected.")
    elif kind == "webp":
        riff_size = int.from_bytes(data[4:8], "little")
        if riff_size + 8 != len(data):
            _reject("The WebP file's length does not match its header.")
    elif kind == "avif":
        if not _boxes_cover(data):
            _reject("The AVIF file is malformed or has data after its end.")


def _png_end(data):
    """Walk PNG chunks; return the offset just past IEND, or None if the structure is broken."""
    position = 8
    while position + 12 <= len(data):
        length = int.from_bytes(data[position : position + 4], "big")
        chunk_type = data[position + 4 : position + 8]
        position += 12 + length
        if position > len(data):
            return None
        if chunk_type == b"IEND":
            return position
    return None


def _jpeg_end(data):
    """Walk JPEG segments and scans; return the offset just past EOI, or None if malformed."""
    size = len(data)
    position = 2  # after SOI
    while position < size:
        if data[position] != 0xFF:
            return None
        while position < size and data[position] == 0xFF:  # fill bytes
            position += 1
        if position >= size:
            return None
        marker = data[position]
        position += 1
        if marker == 0xD9:  # EOI
            return position
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # standalone markers
            continue
        if position + 2 > size:
            return None
        length = int.from_bytes(data[position : position + 2], "big")
        if length < 2:
            return None
        position += length
        if marker == 0xDA:  # SOS: entropy-coded data runs until the next real marker
            while True:
                position = data.find(b"\xff", position)
                if position == -1 or position + 1 >= size:
                    return None
                following = data[position + 1]
                if following == 0x00 or 0xD0 <= following <= 0xD7:
                    position += 2  # stuffed byte or restart marker: still inside the scan
                elif following == 0xFF:
                    position += 1
                else:
                    break
    return None


def _boxes_cover(data):
    """ISO-BMFF (AVIF): top-level boxes must tile the file exactly."""
    position = 0
    size = len(data)
    while position < size:
        if position + 8 > size:
            return False
        box_size = int.from_bytes(data[position : position + 4], "big")
        if box_size == 1:
            if position + 16 > size:
                return False
            box_size = int.from_bytes(data[position + 8 : position + 16], "big")
        elif box_size == 0:
            box_size = size - position
        if box_size < 8:
            return False
        position += box_size
    return position == size


def _check_pdf(data):
    if b"%%EOF" not in data[-1024:]:
        _reject("The PDF file is incomplete or malformed.")
    lowered = data.lower()
    if any(token in lowered for token in PDF_FORBIDDEN_TOKENS):
        _reject("The PDF contains scripts, launch actions or embedded files and was rejected.")
    if any(marker in lowered for marker in ACTIVE_CONTENT_MARKERS[:-1]):
        _reject("The PDF contains embedded markup and was rejected.")


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------


def _prepare_image(kind, data, digest):
    _check_active_content(data)
    _check_container(kind, data)
    _extensions, pillow_formats, _types = FILE_TYPES[kind]

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            image = Image.open(io.BytesIO(data))
            if image.format not in pillow_formats:
                _reject("The file's contents do not match its image format.")
            if image.format != "MPO" and getattr(image, "n_frames", 1) > 1:
                _reject("Animated images are not supported.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                _reject("The image has too many pixels.")
            image.load()
        except ValidationError:
            raise
        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            SyntaxError,
            ValueError,
        ):
            _reject("The image could not be decoded; it may be corrupt or truncated.")

    clean = _sanitised_pixels(image)
    save_format, extension, options = MASTER_SAVE[kind]
    if save_format == "JPEG" and clean.mode != "RGB":
        clean = clean.convert("RGB")
    master = _encode(clean, save_format, options)

    width, height = clean.size
    variants = {}
    for fmt, (variant_format, variant_options) in VARIANT_FORMATS.items():
        variants[fmt] = {
            target: _encode(_resized(clean, target), variant_format, variant_options)
            for target in variant_widths(width)
        }
    return PreparedUpload(
        kind=kind,
        sha256=digest,
        size=len(data),
        master=master,
        master_ext=extension,
        width=width,
        height=height,
        variants=variants,
    )


def variant_widths(source_width):
    """Standard widths that do not exceed the source; a smaller image keeps its own width."""
    widths = [w for w in VARIANT_WIDTHS if w <= source_width]
    return widths or [source_width]


def _sanitised_pixels(image):
    """Display-oriented sRGB pixels in a brand-new image that carries no metadata at all."""
    image = ImageOps.exif_transpose(image)
    icc = image.info.get("icc_profile")
    if icc and image.mode in ("RGB", "RGBA", "CMYK"):
        output_mode = "RGBA" if image.mode == "RGBA" else "RGB"
        try:
            image = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                ImageCms.createProfile("sRGB"),
                outputMode=output_mode,
            )
        except (ImageCms.PyCMSError, OSError):
            pass  # an unusable profile: keep the pixels as they are

    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    target_mode = "RGBA" if has_alpha else "RGB"
    if image.mode != target_mode:
        try:
            image = image.convert(target_mode)
        except ValueError:
            _reject("The image's colour mode is not supported.")

    clean = Image.new(target_mode, image.size)
    clean.paste(image)
    return clean


def _resized(image, width):
    if width == image.width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _encode(image, fmt, options):
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _save(name, data, written):
    stored = default_storage.save(name, ContentFile(data))
    written.append(stored)
    return stored


def _delete_names(names):
    for name in names:
        try:
            default_storage.delete(name)
        except OSError:
            pass
