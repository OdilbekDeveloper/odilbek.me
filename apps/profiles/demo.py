"""The fictional demo dataset (`manage.py seed_demo`).

Everything it creates is invented: the persona "Alex Demo", the organizations, projects, dates
and figures, and the generated images. It is never Odilbek's content. demo_data/brief.md
describes the universe; docs/CONTENT_IMPORT.md, "Demo content", describes the workflow.

The dataset takes the same path as real content:

1. demo_data/manifest.json is an ordinary draft manifest. The images it names are generated into
   a temporary folder, then the draft-import Loader validates and loads everything: the media
   pipeline, unpublished records, provenance (ImportedRecord with origin=demo).
2. demo_data/review.json is what a reviewer then does in the admin: per-profile wording, project
   galleries, SEO text, availability, and publishing everything except the records it keeps as
   drafts (they exercise the visibility rules).

A re-run changes nothing: a record that already exists, edited or not, is left alone. `reset()`
removes exactly the records the provenance marks as demo. The demo never shares a database with
other content: `seed()` refuses a database holding other career content, and draft_content
refuses one holding the demo.
"""

import io
import json
import math
import random
import shutil
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from PIL import Image, ImageColor, ImageDraw, ImageFont
from PIL.TiffImagePlugin import IFDRational

from apps.career.models import (
    ContactChannel,
    Education,
    Experience,
    LanguagePair,
    Project,
    ProjectMedia,
    Service,
    Skill,
    SkillCategory,
)
from apps.core.models import ImportedRecord, ImportOrigin, MediaAsset, SiteSettings
from apps.core.services import publish
from apps.profiles import services
from apps.profiles.drafting import SECTION_MODELS, Loader, ManifestError
from apps.profiles.models import Profile

DATA_DIR = Path(__file__).resolve().parent / "demo_data"
DEMO = ImportOrigin.DEMO

# Every kind of record the demo creates, in an order deletion can follow: nothing is deleted
# while another demo record still protects it (a language pair its skills, a skill its category,
# a gallery row its image).
RESET_ORDER = (
    Profile,
    LanguagePair,
    Project,
    Experience,
    Education,
    Service,
    ContactChannel,
    Skill,
    SkillCategory,
    SiteSettings,
    MediaAsset,
)

# Publishing follows dependencies: a profile checks the text it displays from linked records.
PUBLISH_ORDER = (
    "skills",
    "projects",
    "experience",
    "education",
    "services",
    "contact_channels",
    "profiles",
)


class DemoError(ManifestError):
    """The demo dataset could not be loaded or removed; nothing was changed."""


def load_data():
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads((DATA_DIR / "review.json").read_text(encoding="utf-8"))
    return manifest, review


def demo_record(model, key):
    """The record the demo created for this manifest key, if it still exists."""
    record = ImportedRecord.objects.filter(
        origin=DEMO, model_label=model._meta.label_lower, key=key
    ).first()
    return model.objects.filter(pk=record.object_id).first() if record else None


def _translated(field, values):
    return {f"{field}_{code}": text for code, text in values.items()}


# ---------------------------------------------------------------------------
# Loading and removing
# ---------------------------------------------------------------------------


def foreign_content(limit=3):
    """What this database holds that the demo did not create, described for a person."""
    found = []
    if ImportedRecord.objects.exclude(origin=DEMO).exists():
        found.append("drafts imported by draft_content")
    tracked = ImportedRecord.objects.filter(origin=DEMO)
    for model in RESET_ORDER:
        if model is SiteSettings:
            continue
        ids = tracked.filter(model_label=model._meta.label_lower).values("object_id")
        for obj in model.objects.exclude(pk__in=ids)[:limit]:
            found.append(f"{model._meta.verbose_name} “{obj}”")
    site = SiteSettings.objects.filter(pk=1).first()
    if site and site.owner_name_en and not tracked.filter(model_label="core.sitesettings").exists():
        found.append("filled-in site settings")
    return found


def seed():
    """Load the demo dataset. Returns (import report, review); raises DemoError or
    ManifestError, in which case nothing was written."""
    if found := foreign_content():
        raise DemoError(
            [
                "This database holds content that is not the demo's: "
                + "; ".join(found)
                + ". Demo and real content never mix: run seed_demo against a separate "
                "database (README, “Demo data”)."
            ]
        )
    manifest, data = load_data()
    with tempfile.TemporaryDirectory(prefix="odilbek-demo-") as tmp:
        root = Path(tmp)
        shutil.copyfile(DATA_DIR / "brief.md", root / "brief.md")
        render_images(root, [item["file"] for item in manifest.get("media", [])])
        loader = Loader(root, manifest, origin=DEMO)
        review = Review(data, loader)
        report = loader.apply(then=review.apply)
    return report, review


def reset():
    """Delete every record the provenance marks as demo, then the provenance itself.
    Nothing else is touched. Returns {record type: number removed}."""
    tracked = ImportedRecord.objects.filter(origin=DEMO)
    removed = {}
    with transaction.atomic():
        for model in RESET_ORDER:
            ids = list(
                tracked.filter(model_label=model._meta.label_lower).values_list(
                    "object_id", flat=True
                )
            )
            if not ids:
                continue
            try:
                _total, per_model = model.objects.filter(pk__in=ids).delete()
            except ProtectedError as exc:
                blockers = ", ".join(sorted({str(obj) for obj in exc.protected_objects})[:3])
                raise DemoError(
                    [f"Records that are not demo content still use demo records: {blockers}."]
                ) from exc
            removed[str(model._meta.verbose_name_plural)] = per_model.get(model._meta.label, 0)
        tracked.delete()
    return removed


# ---------------------------------------------------------------------------
# The review step
# ---------------------------------------------------------------------------


class Review:
    """Applies review.json after the import, as a reviewer would in the admin.

    Only records created by this run are reviewed and published, so a re-run leaves every
    existing record exactly as it is. Validation happens before anything is written.
    """

    SECTIONS = {"keep_unpublished", "site", "projects", "profiles", "links"}
    SITE_FIELDS = {
        "availability",
        "availability_note",
        "response_time_note",
        "seo_title",
        "seo_description",
        "default_og_image",
    }
    PROJECT_FIELDS = {"is_featured", "seo_title", "seo_description", "og_image", "gallery"}
    PROFILE_FIELDS = {"seo_title", "seo_description", "og_image"}
    LINK_FIELDS = {"summary_override", "highlights_override"}
    TRANSLATED = {
        "availability_note",
        "response_time_note",
        "seo_title",
        "seo_description",
        "summary_override",
        "highlights_override",
    }

    def __init__(self, data, loader):
        self.data = data
        self.errors = []
        self.published = []
        self.kept = []
        self.keys = {
            section: {e.key for e in entries} for section, entries in loader.entries.items()
        }
        self.profile_refs = {e.key: e.refs for e in loader.entries.get("profiles", [])}
        self._validate()
        if self.errors:
            raise DemoError(self.errors)

    # -- validation ------------------------------------------------------------

    def _check(self, path, allowed, fields):
        prefix = f"review.{path}." if path else "review."
        for name in sorted(set(fields) - allowed):
            self.errors.append(f"{prefix}{name}: unknown field")

    def _known(self, path, section, key):
        if key not in self.keys.get(section, set()):
            self.errors.append(f"review.{path}: '{key}' is not in the manifest's {section}")

    def _validate(self):
        data = self.data
        self._check("", self.SECTIONS, data)
        for section, keys in data.get("keep_unpublished", {}).items():
            if section not in PUBLISH_ORDER:
                self.errors.append(f"review.keep_unpublished.{section}: not publishable")
            for key in keys:
                self._known(f"keep_unpublished.{section}", section, key)
        site = data.get("site", {})
        self._check("site", self.SITE_FIELDS, site)
        if "default_og_image" in site:
            self._known("site.default_og_image", "media", site["default_og_image"])
        for slug, fields in data.get("projects", {}).items():
            self._known(f"projects.{slug}", "projects", slug)
            self._check(f"projects.{slug}", self.PROJECT_FIELDS, fields)
            if "og_image" in fields:
                self._known(f"projects.{slug}.og_image", "media", fields["og_image"])
            for i, item in enumerate(fields.get("gallery", [])):
                self._check(f"projects.{slug}.gallery[{i}]", {"media", "caption"}, item)
                self._known(f"projects.{slug}.gallery[{i}]", "media", item.get("media"))
        for slug, fields in data.get("profiles", {}).items():
            self._known(f"profiles.{slug}", "profiles", slug)
            self._check(f"profiles.{slug}", self.PROFILE_FIELDS, fields)
            if "og_image" in fields:
                self._known(f"profiles.{slug}.og_image", "media", fields["og_image"])
        for i, link in enumerate(data.get("links", [])):
            self._validate_link(f"links[{i}]", link)

    def _validate_link(self, path, link):
        self._check(path, {"profile", "project", "experience"} | self.LINK_FIELDS, link)
        refs = self.profile_refs.get(link.get("profile"))
        if refs is None:
            self.errors.append(f"review.{path}: '{link.get('profile')}' is not a manifest profile")
            return
        if "project" in link:
            linked = {item.get("slug") for item in refs["projects"]}
            item = link["project"]
        else:
            linked, item = set(refs["experience"]), link.get("experience")
        if item not in linked:
            self.errors.append(
                f"review.{path}: the manifest does not link '{item}' to '{link['profile']}'; "
                "the review only rewords existing links"
            )

    # -- applying --------------------------------------------------------------

    def apply(self, report):
        created = {(section, key) for section, key, outcome in report.rows if outcome == "created"}
        if ("site", "site", "updated") in report.rows:
            self._site()
        for slug, fields in self.data.get("projects", {}).items():
            if ("projects", slug) in created:
                self._project(demo_record(Project, slug), fields)
        for slug, fields in self.data.get("profiles", {}).items():
            if ("profiles", slug) in created:
                profile = demo_record(Profile, slug)
                self._seo(profile, fields)
                self._save(profile, f"profile '{slug}'")
        for link in self.data.get("links", []):
            if ("profiles", link["profile"]) in created:
                self._link(link)
        self._publish(report)

    def _save(self, obj, what):
        try:
            obj.full_clean()
        except ValidationError as exc:
            raise DemoError([f"{what}: {'; '.join(exc.messages)}"]) from exc
        obj.save()

    def _site(self):
        site = SiteSettings.load()
        for name, value in self.data.get("site", {}).items():
            if name in self.TRANSLATED:
                for column, text in _translated(name, value).items():
                    setattr(site, column, text)
            elif name == "default_og_image":
                site.default_og_image = demo_record(MediaAsset, value)
            else:
                setattr(site, name, value)
        self._save(site, "site settings")
        ImportedRecord.objects.get_or_create(
            model_label="core.sitesettings",
            key="site",
            defaults={"object_id": site.pk, "origin": DEMO},
        )

    def _seo(self, obj, fields):
        for name in ("seo_title", "seo_description"):
            for column, text in _translated(name, fields.get(name, {})).items():
                setattr(obj, column, text)
        if "og_image" in fields:
            obj.og_image = demo_record(MediaAsset, fields["og_image"])

    def _project(self, project, fields):
        self._seo(project, fields)
        project.is_featured = fields.get("is_featured", project.is_featured)
        self._save(project, f"project '{project.slug}'")
        for order, item in enumerate(fields.get("gallery", []), start=1):
            row = ProjectMedia(
                project=project,
                asset=demo_record(MediaAsset, item["media"]),
                order=order,
                **_translated("caption", item.get("caption", {})),
            )
            self._save(row, f"gallery of '{project.slug}'")

    def _link(self, link):
        profile = demo_record(Profile, link["profile"])
        if "project" in link:
            item = demo_record(Project, link["project"])
        else:
            item = demo_record(Experience, link["experience"])
        fields = {}
        for name in self.LINK_FIELDS & set(link):
            fields.update(_translated(name, link[name]))
        try:
            services.link(profile, item, **fields)
        except ValidationError as exc:
            raise DemoError([f"link {profile} → {item}: {'; '.join(exc.messages)}"]) from exc

    def _publish(self, report):
        keep = self.data.get("keep_unpublished", {})
        created = [(s, k) for s, k, outcome in report.rows if outcome == "created"]
        for section in PUBLISH_ORDER:
            model = SECTION_MODELS[section]
            for key in [k for s, k in created if s == section]:
                if key in keep.get(section, []):
                    self.kept.append((section, key))
                    continue
                obj = demo_record(model, key)
                try:
                    publish(obj)
                except ValidationError as exc:
                    raise DemoError(
                        [f"{section} '{key}' could not be published: {' '.join(exc.messages)}"]
                    ) from exc
                self.published.append((section, key))


# ---------------------------------------------------------------------------
# Generated images: abstract placeholders, never photographs, never committed
# ---------------------------------------------------------------------------

PALETTES = {
    "warm": ("#9c4a2f", "#f4a261", "#fff4e6"),
    "coral": ("#264653", "#e76f51", "#fefae0"),
    "ocean": ("#1d3557", "#457b9d", "#f1faee"),
    "teal": ("#003d4d", "#2a9d8f", "#e9f5f2"),
    "violet": ("#3c096c", "#9d4edd", "#f3e8ff"),
    "forest": ("#1b4332", "#52b788", "#d8f3dc"),
    "sand": ("#6b4f2a", "#d4a373", "#faedcd"),
    "slate": ("#0f172a", "#334155", "#e2e8f0"),
}

# File -> (size, palette, motif). The sizes exercise the pipeline: one image wide enough for
# every variant width, one narrower than the smallest, landscape and portrait.
IMAGES = {
    "images/portrait.jpg": ((1200, 1500), "warm", "portrait"),
    "images/hero-translator.png": ((1600, 900), "coral", "bubbles"),
    "images/og-default.png": ((1200, 630), "slate", "card"),
    "images/atlas-cover.png": ((1920, 1080), "ocean", "nodes"),
    "images/atlas-queue.webp": ((1280, 800), "ocean", "cards"),
    "images/atlas-retries.png": ((1280, 800), "ocean", "bars"),
    "images/relaybot-cover.jpg": ((1200, 675), "teal", "bubbles"),
    "images/contextdesk-cover.avif": ((1200, 675), "violet", "cards"),
    "images/hanbridge-cover.png": ((1200, 675), "coral", "columns"),
    "images/hanbridge-review.webp": ((1200, 750), "coral", "columns"),
    "images/signalflow-cover.webp": ((1200, 675), "forest", "waves"),
    "images/northgale-cover.jpg": ((1200, 675), "sand", "calendar"),
    "images/quickform-cover.png": ((320, 320), "slate", "form"),
}

# The portrait arrives the way a phone photo does: rotated, with a camera and GPS position in its
# EXIF data. The pipeline must apply the rotation and strip the rest (tests/test_seed_demo.py).
PORTRAIT = "images/portrait.jpg"
FORMATS = {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".avif": "AVIF"}
SAVE_OPTIONS = {
    "JPEG": {"quality": 90},
    "PNG": {},
    "WEBP": {"quality": 90},
    "AVIF": {"quality": 70},
}


def render_images(root, names):
    """Write each named image under root. Raises DemoError for an image with no recipe."""
    missing = [name for name in names if name not in IMAGES]
    if missing:
        raise DemoError([f"No generated image for manifest media file(s): {', '.join(missing)}"])
    for name in names:
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes(name))


def image_bytes(name):
    """The encoded source file for one demo image, exactly as the importer will read it."""
    size, palette, motif = IMAGES[name]
    image = _render(size, palette, motif, seed=name)
    buffer = io.BytesIO()
    if name == PORTRAIT:
        # Stored turned on its side with Orientation 6 ("rotate 90° clockwise to display").
        rotated = image.transpose(Image.Transpose.ROTATE_90)
        rotated.save(buffer, "JPEG", quality=90, exif=_fake_camera_exif().tobytes())
    else:
        fmt = FORMATS[Path(name).suffix]
        image.save(buffer, fmt, **SAVE_OPTIONS[fmt])
    return buffer.getvalue()


def _fake_camera_exif():
    exif = Image.Exif()
    exif[0x010F] = "DemoCam"  # Make
    exif[0x0110] = "Placeholder One"  # Model
    exif[0x0112] = 6  # Orientation
    gps = exif.get_ifd(0x8825)
    zero = (IFDRational(0, 1), IFDRational(0, 1), IFDRational(0, 1))
    gps[1], gps[2], gps[3], gps[4] = "N", zero, "E", zero  # 0°N 0°E: nowhere in particular
    return exif


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except (OSError, TypeError):  # a Pillow without FreeType: the small bitmap font
        return ImageFont.load_default()


def _render(size, palette, motif, seed):
    rng = random.Random(seed)
    dark, accent, light = (ImageColor.getrgb(color) for color in PALETTES[palette])
    mask = Image.linear_gradient("L").resize(size)
    image = Image.composite(Image.new("RGB", size, accent), Image.new("RGB", size, dark), mask)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    MOTIFS[motif](draw, size, light, rng)
    _demo_tag(draw, size, light)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _rgba(color, alpha):
    return (*color, alpha)


def _demo_tag(draw, size, light):
    unit = min(size)
    font = _font(max(12, unit // 18))
    pad = max(4, unit // 60)
    left, top, right, bottom = draw.textbbox((0, 0), "DEMO", font=font)
    box = (pad * 2, pad * 2, pad * 4 + right - left, pad * 4 + bottom - top)
    draw.rounded_rectangle(box, radius=pad, fill=_rgba(light, 210))
    draw.text((pad * 3 - left, pad * 3 - top), "DEMO", font=font, fill=(20, 20, 20, 255))


def _nodes(draw, size, light, rng):
    w, h = size
    points = [(rng.uniform(0.1, 0.9) * w, rng.uniform(0.2, 0.85) * h) for _ in range(9)]
    width = max(2, min(size) // 180)
    for a, b in zip(points, points[1:], strict=False):
        draw.line([a, b], fill=_rgba(light, 150), width=width)
    for _ in range(4):
        draw.line(rng.sample(points, 2), fill=_rgba(light, 90), width=width)
    radius = min(size) * 0.035
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=_rgba(light, 230))


def _cards(draw, size, light, rng):
    w, h = size
    cols, rows = 3, 2
    gap = w * 0.04
    card_w = (w - gap * (cols + 1)) / cols
    card_h = (h * 0.75 - gap * (rows + 1)) / rows
    highlighted = rng.randrange(cols * rows)
    for index in range(cols * rows):
        x = gap + (index % cols) * (card_w + gap)
        y = h * 0.2 + gap + (index // cols) * (card_h + gap)
        alpha = 220 if index == highlighted else 70
        draw.rounded_rectangle(
            (x, y, x + card_w, y + card_h), radius=gap / 3, fill=_rgba(light, alpha)
        )
        for line in range(3):
            length = card_w * rng.uniform(0.4, 0.8)
            ly = y + card_h * (0.25 + line * 0.22)
            draw.rounded_rectangle(
                (x + gap / 2, ly, x + gap / 2 + length, ly + card_h * 0.08),
                radius=card_h * 0.04,
                fill=_rgba((40, 40, 40), 90 if index == highlighted else 60),
            )


def _bars(draw, size, light, rng):
    w, h = size
    rows = 7
    bar_h = h * 0.06
    for row in range(rows):
        y = h * 0.22 + row * bar_h * 1.7
        start = w * rng.uniform(0.08, 0.3)
        end = start + w * rng.uniform(0.15, 0.6)
        draw.rounded_rectangle((start, y, end, y + bar_h), radius=bar_h / 2, fill=_rgba(light, 190))


def _bubbles(draw, size, light, rng):
    w, h = size
    y = h * 0.18
    for index in range(5):
        bubble_w = w * rng.uniform(0.3, 0.55)
        bubble_h = h * 0.12
        x = w * 0.08 if index % 2 == 0 else w * 0.92 - bubble_w
        alpha = 215 if index % 2 == 0 else 120
        draw.rounded_rectangle(
            (x, y, x + bubble_w, y + bubble_h), radius=bubble_h / 2, fill=_rgba(light, alpha)
        )
        y += bubble_h * 1.35


def _columns(draw, size, light, rng):
    w, h = size
    line_h = h * 0.045
    highlighted = rng.randrange(6)
    for side in (0, 1):
        x = w * (0.08 if side == 0 else 0.56)
        for row in range(6):
            y = h * 0.25 + row * line_h * 2
            length = w * rng.uniform(0.18, 0.34)
            alpha = 235 if row == highlighted else 150
            draw.rounded_rectangle(
                (x, y, x + length, y + line_h), radius=line_h / 2, fill=_rgba(light, alpha)
            )
    draw.arc(
        (w * 0.3, h * 0.08, w * 0.7, h * 0.5),
        start=200,
        end=340,
        fill=_rgba(light, 230),
        width=max(3, min(size) // 90),
    )


def _waves(draw, size, light, rng):
    w, h = size
    for stage in range(3):
        x = w * (0.2 + stage * 0.25)
        draw.rounded_rectangle(
            (x, h * 0.15, x + w * 0.12, h * 0.85), radius=w * 0.02, fill=_rgba(light, 45)
        )
    for wave in range(3):
        phase = rng.uniform(0, math.pi)
        amplitude = h * (0.12 - wave * 0.03)
        points = [
            (x, h * 0.5 + amplitude * math.sin(phase + x / w * math.pi * (3 + wave)))
            for x in range(0, w + 1, max(4, w // 150))
        ]
        draw.line(points, fill=_rgba(light, 220 - wave * 50), width=max(3, min(size) // 120))


def _calendar(draw, size, light, rng):
    w, h = size
    cols, rows = 7, 5
    cell = min(w * 0.8 / cols, h * 0.7 / rows)
    left = (w - cell * cols) / 2
    top = h * 0.2
    filled = set(rng.sample(range(cols * rows), 6))
    for index in range(cols * rows):
        x = left + (index % cols) * cell
        y = top + (index // cols) * cell
        box = (x + cell * 0.08, y + cell * 0.08, x + cell * 0.92, y + cell * 0.92)
        alpha = 230 if index in filled else 60
        draw.rounded_rectangle(box, radius=cell * 0.15, fill=_rgba(light, alpha))


def _form(draw, size, light, rng):
    w, h = size
    for row in range(3):
        y = h * (0.3 + row * 0.17)
        draw.rounded_rectangle(
            (w * 0.15, y, w * 0.85, y + h * 0.1), radius=h * 0.03, fill=_rgba(light, 200)
        )
    draw.rounded_rectangle(
        (w * 0.5, h * 0.82, w * 0.85, h * 0.92), radius=h * 0.03, fill=_rgba(light, 255)
    )


def _portrait(draw, size, light, rng):
    w, h = size
    for ring in range(6):
        radius = w * (0.42 - ring * 0.06)
        cx, cy = w * 0.5, h * (0.42 + ring * 0.01)
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius), fill=_rgba(light, 25 + ring * 18)
        )
    draw.rounded_rectangle(
        (w * 0.2, h * 0.78, w * 0.8, h * 1.1), radius=w * 0.2, fill=_rgba(light, 90)
    )


def _card(draw, size, light, rng):
    w, h = size
    for _ in range(12):
        x = w * rng.uniform(0, 1)
        draw.line([(x, 0), (x + w * 0.3, h)], fill=_rgba(light, 25), width=max(2, w // 300))
    font = _font(int(h * 0.3))
    left, top, right, bottom = draw.textbbox((0, 0), "DEMO", font=font)
    origin = ((w - (right - left)) / 2 - left, (h - (bottom - top)) / 2 - top)
    draw.text(origin, "DEMO", font=font, fill=_rgba(light, 240))


MOTIFS = {
    "nodes": _nodes,
    "cards": _cards,
    "bars": _bars,
    "bubbles": _bubbles,
    "columns": _columns,
    "waves": _waves,
    "calendar": _calendar,
    "form": _form,
    "portrait": _portrait,
    "card": _card,
}
