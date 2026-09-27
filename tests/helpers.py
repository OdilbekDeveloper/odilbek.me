"""Synthetic files and fictional records for tests. Nothing here is real: images are generated,
names are 'Example ...', addresses are at example.com."""

import io
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageCms
from PIL.TiffImagePlugin import IFDRational

from apps.career.models import (
    ContactChannel,
    Education,
    Experience,
    Project,
    Service,
    Skill,
    SkillCategory,
)
from apps.profiles.models import Profile

# ---------------------------------------------------------------------------
# Synthetic files
# ---------------------------------------------------------------------------

FAKE_CAMERA = "ExampleCam 3000"


def gradient(size=(2000, 1000), mode="RGB"):
    across = Image.linear_gradient("L").rotate(90).resize(size)
    down = Image.linear_gradient("L").resize(size)
    image = Image.merge("RGB", (across, down, Image.new("L", size, 120)))
    return image.convert(mode) if mode != "RGB" else image


def gps_exif(orientation=None):
    """EXIF with a fake camera and fake GPS coordinates: exactly what must never survive."""
    exif = Image.Exif()
    exif[0x010F] = FAKE_CAMERA  # Make
    exif[0x0110] = "Example Model"  # Model
    if orientation:
        exif[0x0112] = orientation
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (IFDRational(37, 1), IFDRational(33, 1), IFDRational(36, 1))
    gps[3] = "E"
    gps[4] = (IFDRational(126, 1), IFDRational(58, 1), IFDRational(41, 1))
    return exif


def image_bytes(fmt="JPEG", size=(2000, 1000), mode="RGB", **save_kwargs):
    buffer = io.BytesIO()
    gradient(size, mode).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def jpeg_with_gps(size=(2000, 1000), orientation=None):
    return image_bytes("JPEG", size, exif=gps_exif(orientation).tobytes())


def jpeg_with_srgb_profile(size=(800, 400)):
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return image_bytes("JPEG", size, icc_profile=icc)


def animated_webp():
    frames = [gradient((200, 100)), gradient((200, 100)).rotate(180)]
    buffer = io.BytesIO()
    frames[0].save(buffer, "WEBP", save_all=True, append_images=frames[1:], duration=100)
    return buffer.getvalue()


def pdf_bytes(extra=b""):
    return (
        b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        + extra
        + b"\ntrailer << /Root 1 0 R >>\n%%EOF\n"
    )


def upload(name, data, content_type=""):
    return SimpleUploadedFile(name, data, content_type=content_type)


# ---------------------------------------------------------------------------
# Fictional records
# ---------------------------------------------------------------------------


def category(slug="example-backend", kind="technical", **fields):
    fields.setdefault("name_en", "Example Backend")
    return SkillCategory.objects.create(slug=slug, kind=kind, **fields)


def language_category():
    return category("example-languages", "language", name_en="Example Languages")


def skill(slug="example-skill", category_obj=None, **fields):
    fields.setdefault("name_en", "Example Skill")
    return Skill.objects.create(slug=slug, category=category_obj or category(), **fields)


def project(slug="example-project", **fields):
    fields.setdefault("title_en", "Example Project")
    fields.setdefault("summary_en", "A fictional project.")
    return Project.objects.create(slug=slug, **fields)


def experience(**fields):
    fields.setdefault("role_en", "Example Engineer")
    fields.setdefault("organization_en", "Fictional Company")
    fields.setdefault("started_on", date(2020, 1, 1))
    return Experience.objects.create(**fields)


def education(**fields):
    fields.setdefault("institution_en", "Example University")
    return Education.objects.create(**fields)


def service(slug="example-service", **fields):
    fields.setdefault("title_en", "Example Service")
    return Service.objects.create(slug=slug, **fields)


def channel(**fields):
    fields.setdefault("kind", "email")
    fields.setdefault("label_en", "Email")
    fields.setdefault("handle", "someone@example.com")
    return ContactChannel.objects.create(**fields)


def profile(slug="example-developer", kind="role", **fields):
    fields.setdefault("name_en", "Example Developer")
    fields.setdefault("headline_en", "A fictional headline")
    return Profile.objects.create(slug=slug, kind=kind, **fields)
