"""Load a draft manifest into unpublished records (`manage.py draft_content`).

Drafting (reading CVs and project READMEs and writing down only the facts they establish)
produces a JSON manifest in the git-ignored content-import/ folder, where every record names its
source. This module validates the manifest strictly, then loads it:

- every record it creates is unpublished; publication fields in the manifest are an error
- a record without a cited source is an error
- a fact the sources do not establish becomes a `TODO(odilbek): ...` note, never a guess:
  a year-only date or a missing end date is flagged rather than presented as known
- published records are never modified; drafts deleted since an import are not recreated
- nothing is written anywhere but the local database and media storage

Any error aborts before anything is written. docs/CONTENT_IMPORT.md describes the format.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction

from apps.career.models import (
    ChannelKind,
    ContactChannel,
    Education,
    EducationKind,
    EmploymentType,
    Experience,
    LanguageMode,
    LanguagePair,
    Project,
    ProjectStatus,
    Service,
    Skill,
    SkillCategory,
    SkillCategoryKind,
)
from apps.core import media
from apps.core.constraints import HTTP_URL_PATTERN, SLUG_PATTERN
from apps.core.content import TODO_MARKER, language_codes, todo_fields
from apps.core.models import ImportedRecord, MediaAsset, SiteSettings
from apps.profiles import services
from apps.profiles.models import (
    ContactFormVariant,
    HeroVariant,
    PrimaryCTA,
    Profile,
    ProfileKind,
    SectionType,
)

SCHEMA_VERSION = 1
DEFAULT_ROOT = Path(settings.BASE_DIR) / "content-import"
PRESENT = "present"

# Where each kind of record keeps its TODO(odilbek) notes.
TODO_FIELD = {
    "site": "tagline",
    "media": "caption",
    "skills": "description",
    "projects": "description",
    "experience": "summary",
    "education": "description",
    "services": "description",
    "language_pairs": "note",
    "profiles": "intro",
}


class ManifestError(Exception):
    def __init__(self, messages):
        super().__init__("\n".join(messages))
        self.messages = messages


@dataclass
class Entry:
    section: str
    key: str
    fields: dict
    todos: list
    refs: dict = field(default_factory=dict)
    path: str = ""


@dataclass
class Report:
    rows: list = field(default_factory=list)  # (section, key, outcome)
    todo_records: list = field(default_factory=list)  # (section, key, count)

    def add(self, section, key, outcome):
        self.rows.append((section, key, outcome))

    def summary(self):
        counts = {}
        for section, _key, outcome in self.rows:
            counts.setdefault(section, {}).setdefault(outcome, 0)
            counts[section][outcome] += 1
        return counts


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class Reader:
    """Typed, validated access to one manifest record; errors carry the record's path."""

    def __init__(self, loader, raw, path, allowed):
        self.loader = loader
        self.path = path
        self.todos = []
        if not isinstance(raw, dict):
            loader.error(path, "must be an object")
            raw = {}
        self.raw = raw
        publication = {"is_published", "published_at"}
        for name in sorted(publication & set(raw)):
            loader.error(
                f"{path}.{name}", "imports never set publication; every draft is unpublished"
            )
        for name in sorted(set(raw) - set(allowed) - {"sources", "todo"} - publication):
            loader.error(f"{path}.{name}", "unknown field")
        self.sources()
        for note in self._list("todo", str):
            self.todos.append(note)

    def _list(self, name, item_type):
        value = self.raw.get(name, [])
        if not isinstance(value, list) or not all(isinstance(v, item_type) for v in value):
            self.loader.error(f"{self.path}.{name}", "must be a list")
            return []
        return value

    def sources(self):
        cited = self._list("sources", str)
        if not cited:
            self.loader.error(f"{self.path}.sources", "every record must cite at least one source")
        for key in cited:
            if key not in self.loader.sources:
                self.loader.error(f"{self.path}.sources", f"'{key}' is not a declared source")
        return cited

    def text(self, name, required=False):
        value = self.raw.get(name)
        if value is None:
            if required:
                self.loader.error(f"{self.path}.{name}", "is required")
            return ""
        if not isinstance(value, str):
            self.loader.error(f"{self.path}.{name}", "must be a string")
            return ""
        return value.strip()

    def tr(self, name, required=False):
        """A translated value: {"en": "...", "ko": "..."}. Only site languages are allowed."""
        value = self.raw.get(name)
        if value is None:
            if required:
                self.loader.error(f"{self.path}.{name}.en", "is required")
            return {}
        if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
            self.loader.error(f"{self.path}.{name}", 'must be an object like {"en": "..."}')
            return {}
        unknown = set(value) - set(language_codes())
        if unknown:
            self.loader.error(f"{self.path}.{name}", f"unknown languages {sorted(unknown)}")
        if required and not value.get("en", "").strip():
            self.loader.error(f"{self.path}.{name}.en", "is required")
        return {code: text.strip() for code, text in value.items() if code in language_codes()}

    def choice(self, name, enum, required=False):
        value = self.text(name, required)
        if value and value not in enum.values:
            self.loader.error(f"{self.path}.{name}", f"must be one of {enum.values}")
        return value

    def slug(self, name="slug"):
        value = self.text(name, required=True)
        if value and not re.fullmatch(SLUG_PATTERN, value):
            self.loader.error(f"{self.path}.{name}", "must be a lowercase-hyphenated slug")
        return value

    def slugs(self, name):
        return [s for s in self._list(name, str) if s]

    def url(self, name):
        value = self.text(name)
        if value and not re.match(HTTP_URL_PATTERN, value):
            self.loader.error(f"{self.path}.{name}", "must be an http(s) URL")
        return value

    def boolean(self, name, default):
        value = self.raw.get(name, default)
        if not isinstance(value, bool):
            self.loader.error(f"{self.path}.{name}", "must be true or false")
            return default
        return value

    def date(self, name, allow_present=False):
        """'YYYY-MM-DD', 'YYYY-MM' (month precision) or 'YYYY'. A year alone is stored as
        January 1st and flagged, because the month is not known."""
        value = self.raw.get(name)
        if value is None:
            return None
        if allow_present and value == PRESENT:
            return PRESENT
        match = isinstance(value, str) and re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", value)
        if not match:
            self.loader.error(f"{self.path}.{name}", "must be 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD'")
            return None
        year, month, day = match.groups()
        try:
            parsed = date(int(year), int(month or 1), int(day or 1))
        except ValueError:
            self.loader.error(f"{self.path}.{name}", "is not a real date")
            return None
        if month is None:
            self.todos.append(f"the sources give only the year for {name} ({year}); confirm it")
        return parsed


class Loader:
    def __init__(self, root, manifest, *, update=False):
        self.root = Path(root).resolve()
        self.update = update
        self.errors = []
        self.report = Report()
        self.sources = {}
        self.entries = {}
        self._stored_files = []
        self._parse(manifest)

    def error(self, path, message):
        self.errors.append(f"{path}: {message}")

    # -- parsing -------------------------------------------------------------

    def _parse(self, manifest):
        if not isinstance(manifest, dict):
            raise ManifestError(["The manifest must be a JSON object."])
        if manifest.get("schema") != SCHEMA_VERSION:
            self.error("schema", f"must be {SCHEMA_VERSION}")
        known = {"schema", "sources", "site", *TODO_FIELD, "skill_categories", "contact_channels"}
        for name in sorted(set(manifest) - known):
            self.error(name, "unknown section")
        self._parse_sources(manifest.get("sources", {}))

        sections = (
            ("media", self._media),
            ("skill_categories", self._category),
            ("skills", self._skill),
            ("projects", self._project),
            ("experience", self._experience),
            ("education", self._education),
            ("services", self._service),
            ("language_pairs", self._language_pair),
            ("contact_channels", self._channel),
            ("profiles", self._profile),
        )
        for name, parse in sections:
            raw = manifest.get(name, [])
            if not isinstance(raw, list):
                self.error(name, "must be a list")
                continue
            self.entries[name] = []
            keys = set()
            for index, item in enumerate(raw):
                entry = parse(item, f"{name}[{index}]")
                if entry.key in keys:
                    self.error(f"{name}[{index}]", f"duplicate key '{entry.key}'")
                keys.add(entry.key)
                self.entries[name].append(entry)
        if "site" in manifest:
            self.entries["site"] = [self._site(manifest["site"], "site")]
        self._check_references()
        if self.errors:
            raise ManifestError(self.errors)

    def _parse_sources(self, sources):
        if not isinstance(sources, dict) or not sources:
            self.error("sources", "declare at least one source file")
            return
        for key, value in sources.items():
            path = Path(value) if isinstance(value, str) else None
            if path is None:
                self.error(f"sources.{key}", "must be a file path")
                continue
            resolved = path.resolve() if path.is_absolute() else (self.root / path).resolve()
            if not path.is_absolute() and not resolved.is_relative_to(self.root):
                self.error(f"sources.{key}", "must stay inside the content-import folder")
            elif not resolved.is_file():
                self.error(f"sources.{key}", f"file not found: {value}")
            self.sources[key] = resolved

    def _file_in_root(self, reader, name):
        value = reader.text(name, required=True)
        resolved = (self.root / value).resolve()
        if not resolved.is_relative_to(self.root):
            self.error(f"{reader.path}.{name}", "must stay inside the content-import folder")
        elif value and not resolved.is_file():
            self.error(f"{reader.path}.{name}", f"file not found: {value}")
        return resolved

    @staticmethod
    def _tr(field_name, values):
        return {f"{field_name}_{code}": text for code, text in values.items() if text}

    def _media(self, raw, path):
        r = Reader(self, raw, path, {"key", "file", "alt_text", "caption", "focal"})
        focal = raw.get("focal", [0.5, 0.5]) if isinstance(raw, dict) else [0.5, 0.5]
        valid_focal = (
            isinstance(focal, list)
            and len(focal) == 2
            and all(isinstance(v, int | float) and 0 <= v <= 1 for v in focal)
        )
        if not valid_focal:
            self.error(f"{path}.focal", "must be [x, y] with values between 0 and 1")
            focal = [0.5, 0.5]
        fields = {
            **self._tr("alt_text", r.tr("alt_text", required=True)),
            **self._tr("caption", r.tr("caption")),
            "focal_x": focal[0],
            "focal_y": focal[1],
        }
        refs = {"file": self._file_in_root(r, "file")}
        return Entry("media", r.text("key", required=True), fields, r.todos, refs, path)

    def _site(self, raw, path):
        r = Reader(
            self,
            raw,
            path,
            {"owner_name", "tagline", "location", "timezone", "public_email", "portrait"},
        )
        fields = {
            **self._tr("owner_name", r.tr("owner_name")),
            **self._tr("tagline", r.tr("tagline")),
            **self._tr("location", r.tr("location")),
            "public_email": r.text("public_email"),
        }
        if r.text("timezone"):
            fields["timezone"] = r.text("timezone")
        return Entry("site", "site", fields, r.todos, {"portrait": r.text("portrait")}, path)

    def _category(self, raw, path):
        r = Reader(self, raw, path, {"slug", "kind", "name"})
        fields = {
            "kind": r.choice("kind", SkillCategoryKind, required=True),
            **self._tr("name", r.tr("name", required=True)),
        }
        return Entry("skill_categories", r.slug(), fields, r.todos, {}, path)

    def _skill(self, raw, path):
        r = Reader(self, raw, path, {"slug", "category", "name", "description", "level_label"})
        fields = {
            **self._tr("name", r.tr("name", required=True)),
            **self._tr("description", r.tr("description")),
            **self._tr("level_label", r.tr("level_label")),
        }
        refs = {"category": r.text("category", required=True)}
        return Entry("skills", r.slug(), fields, r.todos, refs, path)

    def _project(self, raw, path):
        allowed = {
            "slug",
            "title",
            "summary",
            "context",
            "description",
            "highlights",
            "role",
            "project_status",
            "started_on",
            "ended_on",
            "github_url",
            "demo_url",
            "is_listed",
            "skills",
            "cover",
        }
        r = Reader(self, raw, path, allowed)
        summary = r.tr("summary")
        if not summary.get("en"):
            summary["en"] = f"{TODO_MARKER}): write a one-line summary"
        fields = {
            **self._tr("title", r.tr("title", required=True)),
            **self._tr("summary", summary),
            **self._tr("context", r.tr("context")),
            **self._tr("description", r.tr("description")),
            **self._tr("highlights", r.tr("highlights")),
            **self._tr("role", r.tr("role")),
            "project_status": r.choice("project_status", ProjectStatus),
            "started_on": r.date("started_on"),
            "ended_on": r.date("ended_on"),
            "github_url": r.url("github_url"),
            "demo_url": r.url("demo_url"),
            "is_listed": r.boolean("is_listed", True),
        }
        refs = {"skills": r.slugs("skills"), "cover": r.text("cover")}
        return Entry("projects", r.slug(), fields, r.todos, refs, path)

    def _experience(self, raw, path):
        allowed = {
            "key",
            "role",
            "organization",
            "organization_url",
            "location",
            "employment_type",
            "started_on",
            "ended_on",
            "summary",
            "highlights",
            "skills",
            "projects",
        }
        r = Reader(self, raw, path, allowed)
        started = r.date("started_on")
        ended = r.date("ended_on", allow_present=True)
        if started is None:
            r.todos.append("the sources do not give a start date")
        if ended is None:
            r.todos.append(
                "the sources do not give an end date; an empty end date reads as 'present'"
            )
        fields = {
            **self._tr("role", r.tr("role", required=True)),
            **self._tr("organization", r.tr("organization", required=True)),
            **self._tr("location", r.tr("location")),
            **self._tr("summary", r.tr("summary")),
            **self._tr("highlights", r.tr("highlights")),
            "organization_url": r.url("organization_url"),
            "employment_type": r.choice("employment_type", EmploymentType),
            "started_on": started,
            "ended_on": None if ended == PRESENT else ended,
        }
        refs = {"skills": r.slugs("skills"), "projects": r.slugs("projects")}
        return Entry("experience", r.text("key", required=True), fields, r.todos, refs, path)

    def _education(self, raw, path):
        allowed = {
            "key",
            "institution",
            "credential",
            "field",
            "kind",
            "started_on",
            "ended_on",
            "result",
            "description",
            "credential_url",
            "skills",
        }
        r = Reader(self, raw, path, allowed)
        fields = {
            **self._tr("institution", r.tr("institution", required=True)),
            **self._tr("credential", r.tr("credential")),
            **self._tr("field", r.tr("field")),
            **self._tr("result", r.tr("result")),
            **self._tr("description", r.tr("description")),
            "kind": r.choice("kind", EducationKind),
            "started_on": r.date("started_on"),
            "ended_on": r.date("ended_on"),
            "credential_url": r.url("credential_url"),
        }
        refs = {"skills": r.slugs("skills")}
        return Entry("education", r.text("key", required=True), fields, r.todos, refs, path)

    def _service(self, raw, path):
        allowed = {"slug", "title", "summary", "description", "pricing_note", "skills"}
        r = Reader(self, raw, path, allowed)
        fields = {
            **self._tr("title", r.tr("title", required=True)),
            **self._tr("summary", r.tr("summary")),
            **self._tr("description", r.tr("description")),
            **self._tr("pricing_note", r.tr("pricing_note")),
        }
        return Entry("services", r.slug(), fields, r.todos, {"skills": r.slugs("skills")}, path)

    def _language_pair(self, raw, path):
        r = Reader(self, raw, path, {"source", "target", "modes", "domains", "note"})
        modes = r.slugs("modes")
        if not modes:
            self.error(f"{path}.modes", "name at least one mode")
        for mode in modes:
            if mode not in LanguageMode.values:
                self.error(f"{path}.modes", f"'{mode}' is not one of {LanguageMode.values}")
        source, target = r.text("source", required=True), r.text("target", required=True)
        fields = {
            "modes": modes,
            **self._tr("domains", r.tr("domains")),
            **self._tr("note", r.tr("note")),
        }
        refs = {"source": source, "target": target}
        return Entry("language_pairs", f"{source}>{target}", fields, r.todos, refs, path)

    def _channel(self, raw, path):
        r = Reader(self, raw, path, {"key", "kind", "label", "url", "handle"})
        fields = {
            "kind": r.choice("kind", ChannelKind, required=True),
            **self._tr("label", r.tr("label", required=True)),
            "url": r.url("url"),
            "handle": r.text("handle"),
        }
        if not fields["url"] and not fields["handle"]:
            self.error(path, "give a url or a handle")
        return Entry("contact_channels", r.text("key", required=True), fields, r.todos, {}, path)

    def _profile(self, raw, path):
        translated = (
            "name",
            "switcher_label",
            "headline",
            "subheadline",
            "intro",
            "router_prompt",
            "router_blurb",
            "primary_cta_label",
        )
        links = ("sections", "projects", "experience", "skills", "education", "services")
        allowed = {
            "slug",
            "kind",
            *translated,
            "hero_variant",
            "hero_image",
            "languages",
            "primary_cta",
            "contact_form_variant",
            "show_in_switcher",
            "show_in_router",
            *links,
            "contact_channels",
        }
        r = Reader(self, raw, path, allowed)
        values = {name: r.tr(name, required=name == "name") for name in translated}
        if not values["headline"].get("en"):
            values["headline"]["en"] = f"{TODO_MARKER}): write the headline"
        languages = r.slugs("languages") or ["en"]
        for code in languages:
            if code not in language_codes():
                self.error(f"{path}.languages", f"'{code}' is not a site language")
        fields = {
            "kind": r.choice("kind", ProfileKind, required=True),
            "hero_variant": r.choice("hero_variant", HeroVariant) or HeroVariant.PORTRAIT,
            "primary_cta": r.choice("primary_cta", PrimaryCTA) or PrimaryCTA.CONTACT,
            "contact_form_variant": (
                r.choice("contact_form_variant", ContactFormVariant) or ContactFormVariant.GENERAL
            ),
            "show_in_switcher": r.boolean("show_in_switcher", True),
            "show_in_router": r.boolean("show_in_router", True),
            "languages": [code for code in language_codes() if code in {*languages, "en"}],
        }
        for name, value in values.items():
            fields.update(self._tr(name, value))
        refs = {"hero_image": r.text("hero_image")}
        refs["sections"] = [
            self._section(item, f"{path}.sections[{i}]")
            for i, item in enumerate(r._list("sections", dict))
        ]
        refs["projects"] = [
            self._link(item, f"{path}.projects[{i}]", ("slug", "is_featured", "is_primary"))
            for i, item in enumerate(r._list("projects", dict))
        ]
        refs["skills"] = [
            self._link(item, f"{path}.skills[{i}]", ("slug", "is_primary"))
            for i, item in enumerate(r._list("skills", dict))
        ]
        refs["contact_channels"] = [
            self._link(item, f"{path}.contact_channels[{i}]", ("key", "is_primary"))
            for i, item in enumerate(r._list("contact_channels", dict))
        ]
        for name in ("experience", "education", "services"):
            refs[name] = r.slugs(name)
        return Entry("profiles", r.slug(), fields, r.todos, refs, path)

    def _section(self, raw, path):
        allowed = {"type", "heading", "intro", "body", "item_limit", "anchor", "is_enabled"}
        unknown = set(raw) - allowed
        for name in sorted(unknown):
            self.error(f"{path}.{name}", "unknown field")
        section_type = raw.get("type")
        if section_type not in SectionType.values:
            self.error(f"{path}.type", f"must be one of {SectionType.values}")
        fields = {"item_limit": raw.get("item_limit"), "anchor": raw.get("anchor", "")}
        for name in ("heading", "intro", "body"):
            value = raw.get(name, {})
            if not isinstance(value, dict):
                self.error(f"{path}.{name}", 'must be an object like {"en": "..."}')
                continue
            fields.update(self._tr(name, value))
        # A section still carrying a TODO cannot be enabled (the database refuses it).
        has_todo = any(TODO_MARKER in str(value) for value in fields.values())
        fields["is_enabled"] = bool(raw.get("is_enabled", True)) and not has_todo
        return {"type": section_type, "fields": fields}

    def _link(self, raw, path, allowed):
        for name in sorted(set(raw) - set(allowed)):
            self.error(f"{path}.{name}", "unknown field")
        key_name = allowed[0]
        if not isinstance(raw.get(key_name), str):
            self.error(f"{path}.{key_name}", "is required")
        return raw

    def _check_references(self):
        def declared(section):
            return {entry.key for entry in self.entries.get(section, [])}

        skills = declared("skills") | set(Skill.objects.values_list("slug", flat=True))
        categories = declared("skill_categories") | set(
            SkillCategory.objects.values_list("slug", flat=True)
        )
        projects = declared("projects") | set(Project.objects.values_list("slug", flat=True))
        media_keys = declared("media")

        def check(path, value, known, what):
            if value and value not in known:
                self.error(path, f"unknown {what} '{value}'")

        for entry in self.entries.get("skills", []):
            check(f"{entry.path}.category", entry.refs["category"], categories, "skill category")
        for section in ("projects", "experience", "education", "services"):
            for entry in self.entries.get(section, []):
                for slug in entry.refs.get("skills", []):
                    check(f"{entry.path}.skills", slug, skills, "skill")
                for slug in entry.refs.get("projects", []):
                    check(f"{entry.path}.projects", slug, projects, "project")
                check(f"{entry.path}.cover", entry.refs.get("cover"), media_keys, "media key")
        for entry in self.entries.get("language_pairs", []):
            for side in ("source", "target"):
                check(f"{entry.path}.{side}", entry.refs[side], skills, "skill")
        for entry in self.entries.get("site", []):
            check(f"{entry.path}.portrait", entry.refs.get("portrait"), media_keys, "media key")
        for entry in self.entries.get("profiles", []):
            check(f"{entry.path}.hero_image", entry.refs["hero_image"], media_keys, "media key")
            for link in entry.refs["projects"]:
                check(f"{entry.path}.projects", link.get("slug"), projects, "project")
            for link in entry.refs["skills"]:
                check(f"{entry.path}.skills", link.get("slug"), skills, "skill")
            for link in entry.refs["contact_channels"]:
                check(
                    f"{entry.path}.contact_channels",
                    link.get("key"),
                    declared("contact_channels"),
                    "channel key",
                )
            for key in entry.refs["experience"]:
                check(f"{entry.path}.experience", key, declared("experience"), "experience key")
            for key in entry.refs["education"]:
                check(f"{entry.path}.education", key, declared("education"), "education key")
            for slug in entry.refs["services"]:
                check(f"{entry.path}.services", slug, declared("services"), "service")

    # -- applying ------------------------------------------------------------

    def validate_media(self):
        """Run every media file through the pipeline's validation (no writes)."""
        for entry in self.entries.get("media", []):
            with open(entry.refs["file"], "rb") as handle:
                try:
                    media.prepare(File(handle, name=entry.refs["file"].name))
                except ValidationError as exc:
                    self.error(f"{entry.path}.file", " ".join(exc.messages))
        if self.errors:
            raise ManifestError(self.errors)

    def plan(self):
        """What apply() would do, computed read-only (for --dry-run)."""
        self.validate_media()
        for section, entries in self.entries.items():
            for entry in entries:
                model = SECTION_MODELS.get(section)
                if model is None:
                    self.report.add(section, entry.key, "would update if empty")
                    continue
                record = ImportedRecord.objects.filter(
                    model_label=model._meta.label_lower, key=entry.key
                ).first()
                if record is None:
                    outcome = "would create"
                elif model.objects.filter(pk=record.object_id).exists():
                    outcome = "would update" if self.update else "exists: would leave untouched"
                else:
                    outcome = "deleted since import: would not recreate"
                self.report.add(section, entry.key, outcome)
        return self.report

    def apply(self):
        self.validate_media()
        try:
            with transaction.atomic():
                self._apply_all()
        except ValidationError as exc:
            media._delete_names(self._stored_files)
            details = (
                [f"{field}: {' '.join(msgs)}" for field, msgs in exc.message_dict.items()]
                if hasattr(exc, "error_dict")
                else exc.messages
            )
            raise ManifestError([f"{self._current}: {'; '.join(details)}"]) from exc
        except Exception:
            media._delete_names(self._stored_files)
            raise
        self._collect_todos()
        return self.report

    _current = ""

    def _resolve(self, model, key, natural=None):
        """('new' | 'imported' | 'deleted', obj). A record created by hand before the import is
        recognised by its natural key (e.g. slug) and adopted rather than duplicated."""
        label = model._meta.label_lower
        record = ImportedRecord.objects.filter(model_label=label, key=key).first()
        if record:
            obj = model.objects.filter(pk=record.object_id).first()
            return ("deleted", None) if obj is None else ("imported", obj)
        if natural:
            obj = model.objects.filter(**natural).first()
            if obj:
                ImportedRecord.objects.create(model_label=label, key=key, object_id=obj.pk)
                return "imported", obj
        return "new", None

    def _upsert(self, entry, model, natural=None):
        """Create the record, update it (--update, unpublished only), or leave it alone.
        Returns (obj, outcome) with outcome 'created', 'updated' or None (left alone)."""
        self._current = entry.path
        status, obj = self._resolve(model, entry.key, natural)
        if status == "deleted":
            self.report.add(entry.section, entry.key, "deleted since import: not recreated")
            return None, None
        if obj is not None:
            if getattr(obj, "is_published", False):
                self.report.add(entry.section, entry.key, "published: left untouched")
                return obj, None
            if not self.update:
                self.report.add(entry.section, entry.key, "exists: left untouched")
                return obj, None
        if obj is None:
            obj = model()
            if any(f.name == "slug" for f in model._meta.concrete_fields):
                obj.slug = entry.key  # slugged records are keyed by their slug
        for name, value in entry.fields.items():
            setattr(obj, name, value)
        self._add_todos(entry, obj)
        obj.full_clean()
        obj.save()
        outcome = "created" if status == "new" else "updated"
        if status == "new":
            ImportedRecord.objects.create(
                model_label=model._meta.label_lower, key=entry.key, object_id=obj.pk
            )
        self.report.add(entry.section, entry.key, outcome)
        return obj, outcome

    def _add_todos(self, entry, obj):
        if not entry.todos:
            return
        column = f"{TODO_FIELD[entry.section]}_en"
        notes = "\n".join(f"{TODO_MARKER}): {note}" for note in entry.todos)
        existing = getattr(obj, column) or ""
        if notes not in existing:
            setattr(obj, column, f"{existing}\n\n{notes}".strip())

    def _apply_media(self):
        assets = {}
        for entry in self.entries.get("media", []):
            self._current = entry.path
            status, obj = self._resolve(MediaAsset, entry.key)
            if status == "deleted":
                self.report.add("media", entry.key, "deleted since import: not recreated")
                continue
            if obj is not None:
                self.report.add("media", entry.key, "exists: left untouched")
            else:
                with open(entry.refs["file"], "rb") as handle:
                    obj, created = media.ingest(
                        File(handle, name=entry.refs["file"].name), **entry.fields
                    )
                ImportedRecord.objects.create(
                    model_label="core.mediaasset", key=entry.key, object_id=obj.pk
                )
                if created:
                    self._stored_files.extend(media.asset_file_names(obj))
                    self._add_todos(entry, obj)
                    obj.full_clean()
                    obj.save()
                    self.report.add("media", entry.key, "created")
                else:
                    # The same file was uploaded before (perhaps by hand): never modify it.
                    self.report.add("media", entry.key, "already stored: left untouched")
            assets[entry.key] = obj
        return assets

    def _apply_all(self):
        assets = self._apply_media()

        for entry in self.entries.get("site", []):
            self._current = entry.path
            site = SiteSettings.load()
            if site.owner_name_en and not self.update:
                self.report.add("site", "site", "exists: left untouched")
            else:
                for name, value in entry.fields.items():
                    setattr(site, name, value)
                if entry.refs.get("portrait"):
                    site.portrait = assets.get(entry.refs["portrait"])
                self._add_todos(entry, site)
                site.full_clean()
                site.save()
                self.report.add("site", "site", "updated")

        for entry in self.entries.get("skill_categories", []):
            self._upsert(entry, SkillCategory, natural={"slug": entry.key})

        for entry in self.entries.get("skills", []):
            entry.fields["category"] = SkillCategory.objects.get(slug=entry.refs["category"])
            self._upsert(entry, Skill, natural={"slug": entry.key})

        for entry in self.entries.get("projects", []):
            if entry.refs.get("cover"):
                entry.fields["cover"] = assets.get(entry.refs["cover"])
            project, outcome = self._upsert(entry, Project, natural={"slug": entry.key})
            if outcome:
                project.skills.set(Skill.objects.filter(slug__in=entry.refs["skills"]))

        for section, model in (("experience", Experience), ("education", Education)):
            for entry in self.entries.get(section, []):
                obj, outcome = self._upsert(entry, model)
                if outcome:
                    obj.skills.set(Skill.objects.filter(slug__in=entry.refs["skills"]))
                    if section == "experience":
                        obj.projects.set(Project.objects.filter(slug__in=entry.refs["projects"]))

        for entry in self.entries.get("services", []):
            service, outcome = self._upsert(entry, Service, natural={"slug": entry.key})
            if outcome:
                service.skills.set(Skill.objects.filter(slug__in=entry.refs["skills"]))

        for entry in self.entries.get("language_pairs", []):
            source = Skill.objects.get(slug=entry.refs["source"])
            target = Skill.objects.get(slug=entry.refs["target"])
            entry.fields.update(source=source, target=target)
            self._upsert(entry, LanguagePair, natural={"source": source, "target": target})

        for entry in self.entries.get("contact_channels", []):
            self._upsert(entry, ContactChannel)

        for entry in self.entries.get("profiles", []):
            if entry.refs.get("hero_image"):
                entry.fields["hero_image"] = assets.get(entry.refs["hero_image"])
            profile, outcome = self._upsert(entry, Profile, natural={"slug": entry.key})
            if outcome:
                self._current = entry.path
                self._compose(profile, entry, created=outcome == "created")

    def _imported(self, model, key):
        record = ImportedRecord.objects.filter(model_label=model._meta.label_lower, key=key).first()
        return model.objects.filter(pk=record.object_id).first() if record else None

    def _compose(self, profile, entry, created):
        """Sections and links. On update, missing standard sections are added and the
        manifest's links ensured; nothing edited or added in the admin is removed."""
        existing = set(profile.sections.values_list("section_type", flat=True))
        for section in entry.refs["sections"]:
            repeatable = section["type"] == SectionType.CUSTOM_MARKDOWN
            if (created and repeatable) or section["type"] not in existing:
                services.add_section(profile, section["type"], **section["fields"])
        for link in entry.refs["projects"]:
            project = Project.objects.get(slug=link["slug"])
            services.link(profile, project, is_featured=link.get("is_featured", False))
            if link.get("is_primary"):
                services.set_primary_profile(project, profile)
        for link in entry.refs["skills"]:
            skill = Skill.objects.get(slug=link["slug"])
            services.link(profile, skill, is_primary=link.get("is_primary", False))
        for key in entry.refs["experience"]:
            if item := self._imported(Experience, key):
                services.link(profile, item)
        for key in entry.refs["education"]:
            if item := self._imported(Education, key):
                services.link(profile, item)
        for slug in entry.refs["services"]:
            services.link(profile, Service.objects.get(slug=slug))
        for link in entry.refs["contact_channels"]:
            if channel := self._imported(ContactChannel, link["key"]):
                services.link(profile, channel, is_primary=link.get("is_primary", False))

    def _collect_todos(self):
        """Which imported records still contain TODO markers, as they stand in the database."""
        for record in ImportedRecord.objects.all():
            model = apps.get_model(record.model_label)
            obj = model.objects.filter(pk=record.object_id).first()
            if obj is not None and (fields := todo_fields(obj)):
                self.report.todo_records.append((record.model_label, record.key, len(fields)))
        site = SiteSettings.objects.filter(pk=1).first()
        if site and (fields := todo_fields(site)):
            self.report.todo_records.append(("core.sitesettings", "site", len(fields)))


# Manifest section -> model, for planning.
SECTION_MODELS = {
    "media": MediaAsset,
    "skill_categories": SkillCategory,
    "skills": Skill,
    "projects": Project,
    "experience": Experience,
    "education": Education,
    "services": Service,
    "language_pairs": LanguagePair,
    "contact_channels": ContactChannel,
    "profiles": Profile,
}


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def check_root(root):
    """Private material must live in the git-ignored content-import/ folder, or outside the
    repository altogether (tests use a temporary folder)."""
    root = Path(root).resolve()
    base = Path(settings.BASE_DIR).resolve()
    if root.is_relative_to(base) and root != DEFAULT_ROOT.resolve():
        raise ManifestError(
            [f"{root} is inside the repository but is not the git-ignored content-import/ folder."]
        )
    return root


def load_manifest(root, name="draft.json"):
    path = check_root(root) / name
    if not path.is_file():
        raise ManifestError([f"No manifest at {path}."])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError([f"{path} is not valid JSON: {exc}"]) from exc
