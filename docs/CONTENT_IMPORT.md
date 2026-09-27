# CONTENT IMPORT

How Odilbek's real career content gets into the database for the first time (D-039). It never
enters git.

```
private sources (CVs, portraits, project READMEs)
      ↓  drafting: only the facts the sources establish, each citing its source
content-import/draft.json          git-ignored manifest
      ↓  manage.py draft_content   strict validation, then load
unpublished draft records          local database and media storage only
      ↓  review in the admin: fix, resolve every TODO(odilbek), publish item by item
```

## The folder

`content-import/` is git-ignored (a test fails if it stops being ignored). It holds:

- the source files: CVs (EN, and KO if one exists), 2–4 portraits (at least one formal), anything
  else the drafts cite
- `draft.json`, the manifest

Project READMEs may stay where they are; the manifest cites them by absolute path.

## Rules

- **Nothing is invented.** A fact the sources don't establish is left out, or written as
  `TODO(odilbek): <what is missing>`. A record containing the marker cannot be published: the
  database refuses (D-035).
- **Every record cites a source.** A record without one, or citing an undeclared or missing file,
  rejects the whole manifest.
- **Everything is unpublished.** `is_published` / `published_at` in the manifest are errors.
- **Dates:** `"YYYY-MM-DD"` or `"YYYY-MM"`. A year alone (`"2019"`) is stored as January and
  flagged with a TODO. For experience, `"ended_on": "present"` means current; leaving it out means
  *unknown* and is flagged, because an empty end date would otherwise read as "current".
- **Re-running is safe.**
  - Existing drafts are left as edited in the admin; `--update` refreshes them from the manifest.
  - Published records are never touched.
  - A draft deleted in the admin is not recreated. To allow that, delete its row under
    *Imported records*.
- **Any error aborts the run** before anything is written.

## Commands

```
uv run python manage.py draft_content --dry-run    validate, show what would happen
uv run python manage.py draft_content              create the drafts
uv run python manage.py draft_content --update     also refresh unpublished drafts from the manifest
```

`--root <folder>` reads the sources from another folder instead, which must be outside the
repository, and `--manifest <name>` picks another file name. The report lists every record that
still contains a TODO.

## Manifest format (schema 1)

Translated values are objects keyed by language: `{"en": "...", "ko": "..."}`. Only `en` is ever
required. Unknown fields are errors, so typos never pass silently.

```jsonc
{
  "schema": 1,
  "sources": {                                   // key → file in content-import/, or an absolute path
    "cv-en": "cv-en.pdf",
    "readme-x": "/path/to/project/README.md"
  },
  "site": {                                      // site settings; filled only while empty (or --update)
    "owner_name": {"en": "..."}, "tagline": {...}, "location": {...},
    "timezone": "Asia/Seoul", "public_email": "...", "portrait": "<media key>",
    "sources": ["cv-en"]
  },
  "media": [{"key": "portrait-formal", "file": "portraits/formal.jpg",
             "alt_text": {"en": "..."}, "caption": {...}, "focal": [0.5, 0.35], "sources": [...]}],
  "skill_categories": [{"slug": "...", "kind": "technical|language|domain|tool", "name": {...}, "sources": [...]}],
  "skills": [{"slug": "...", "category": "<category slug>", "name": {...},
              "description": {...}, "level_label": {...}, "sources": [...]}],
  "projects": [{"slug": "...", "title": {...}, "summary": {...}, "context": {...},
                "description": {...}, "highlights": {...}, "role": {...},
                "project_status": "live|in_progress|archived|concept",
                "started_on": "2021-03", "ended_on": null, "github_url": "https://...",
                "demo_url": "https://...", "is_listed": true, "skills": ["<skill slug>"],
                "cover": "<media key>", "todo": ["confirm the launch date"], "sources": [...]}],
  "experience": [{"key": "<unique label>", "role": {...}, "organization": {...},
                  "organization_url": "...", "location": {...},
                  "employment_type": "full_time|freelance|contract|internship|volunteer",
                  "started_on": "2020-01", "ended_on": "present", "summary": {...},
                  "highlights": {...}, "skills": [...], "projects": ["<project slug>"],
                  "todo": [...], "sources": [...]}],
  "education": [{"key": "...", "institution": {...}, "credential": {...}, "field": {...},
                 "kind": "degree|course|certification|language_test", "started_on": "...",
                 "ended_on": "...", "result": {...}, "description": {...},
                 "credential_url": "...", "skills": [...], "todo": [...], "sources": [...]}],
  "services": [{"slug": "...", "title": {...}, "summary": {...}, "description": {...},
                "pricing_note": {...}, "skills": [...], "sources": [...]}],
  "language_pairs": [{"source": "<skill slug>", "target": "<skill slug>",
                      "modes": ["document", "consecutive"], "domains": {...}, "note": {...},
                      "sources": [...]}],
  "contact_channels": [{"key": "...", "kind": "email|telegram|...", "label": {...},
                        "url": "https://...", "handle": "...", "sources": [...]}],
  "profiles": [{"slug": "...", "kind": "home|about|role", "name": {...}, "headline": {...},
                "subheadline": {...}, "intro": {...}, "switcher_label": {...},
                "router_prompt": {...}, "router_blurb": {...}, "primary_cta_label": {...},
                "hero_variant": "portrait|split|bilingual|statement", "hero_image": "<media key>",
                "languages": ["en", "ko"], "primary_cta": "contact|resume|projects",
                "contact_form_variant": "general|project_inquiry|language_request",
                "sections": [{"type": "about", "heading": {...}, "intro": {...}}],
                "projects": [{"slug": "...", "is_featured": true, "is_primary": true}],
                "experience": ["<experience key>"], "skills": [{"slug": "...", "is_primary": true}],
                "education": ["<education key>"], "services": ["<service slug>"],
                "contact_channels": [{"key": "...", "is_primary": true}],
                "todo": [...], "sources": [...]}]
}
```

`todo` notes are appended to one text field per record type: site → tagline, media → caption,
skill/project/education/service → description, experience → summary, language pair → note,
profile → intro. A project without a summary or a profile without a headline gets a TODO in that
field. A profile section whose text contains a TODO is imported disabled.

`apps/profiles/demo_data/manifest.json` is a complete, working example of this format (below).

## Demo content

`manage.py seed_demo` loads a complete **fictional** career. It gives later phases a realistic site
to design and test against before the real content exists (D-042).

It is not true of anyone:
- the persona is "Alex Demo", and every organization and figure is invented
- every link and address uses a reserved `example.*` domain
- the images are abstract shapes generated at run time and marked "DEMO"

It is not a draft of Odilbek's content and never becomes one.

It takes the same path as real content:

1. **Import.** `apps/profiles/demo_data/manifest.json` is an ordinary schema-1 manifest. The
   importer validates it, runs every image through the media pipeline, and creates the records
   unpublished.
2. **Review.** `review.json` does what a reviewer would then do in the admin:
   - per-profile wording
   - project galleries
   - SEO text
   - availability
   - publishing, except six records kept as unpublished drafts to exercise the visibility rules
3. **Provenance.** Every record it creates is listed under *Imported records* with origin `demo`.

`demo_data/brief.md` describes the universe:
- the timeline
- which project appears on which profile
- the deliberate test cases: hidden records, English fallback, layout stress and media edge cases

| Command | Effect |
|---|---|
| `seed_demo` | load the dataset. A re-run changes nothing and keeps edits made in the admin |
| `seed_demo --reset` | delete every record marked `demo`, its files and its provenance; nothing else |
| `seed_demo --reset`, then `seed_demo` | start again from the files, e.g. after they change |

Rules:
- **Never with real content.** `seed_demo` refuses a database holding content it did not create
  (any project, skill, profile, media asset or other career record, filled-in site settings, or
  real drafts), and `draft_content` refuses a database holding the demo. The demo lives in its own database
  (`README.md`, "Demo data").
- **Never in production.** Only the development and test settings allow seeding
  (`DEMO_CONTENT_ALLOWED`).
- **Real content does not overwrite it.** Real drafts are imported into the main database with
  `draft_content`. The demo database remains for development and tests, and can be reset or
  dropped at any time.
