# DATA MODEL

The schema. **core, career and profiles exist** (Phase 2, ✅), as does `accounts.User` (Phase 1).
Contact (Phase 7), resumes (Phase 8), analytics (Phase 9) and blog (Phase 13) are still plans.
Changes during implementation are logged in `DECISIONS.md` (Phase 2: D-033 to D-042).

## Conventions

| Mark | Meaning |
|---|---|
| `*` | translated field (django-modeltranslation: `_en`, `_ko`, `_uz` columns; English required wherever the field is required, at the database level too) |
| `md` | Markdown source, rendered through the shared sanitizing renderer (Phase 4) |
| `⇄` | many-to-many |
| `→` | foreign key |
| `[ ]` | PostgreSQL array (D-036) |

**Abstract bases (in `core`):**
- `TimeStamped(created_at, updated_at)`, applied to every model
- `Ordered(order)`: a positive integer, indexed; lists sort by `order, id`
- `Publishable(is_published, published_at)`: neither is editable in forms; records are published
  only through `apps.core.services.publish()` (D-035). `QuerySet.public()` and
  `visible(include_drafts)` implement the visibility rules below.
- `SEOFields(seo_title*, seo_description*, og_image→MediaAsset)`
- `ProfileLink`: the shared base of the profile link tables (`order`, timestamps). Each table adds
  its item, its unique `(profile, item)` pair and its override fields. (`ResumeLink`: Phase 8.)

**Other conventions:**
- Slugs are ASCII lowercase words joined by single hyphens (`^[a-z0-9]+(-[a-z0-9]+)*$`), unique per
  model, and **never translated**. The database enforces the format.
- Dates of work and study are `DateField`s; display precision is month/year.
- Choices are `TextChoices` enums in code **and** checked by the database. Blank means "not stated"
  where a field allows it; nothing defaults to a claim.
- Links (`*_url`) are empty or `http(s)://`, in forms and in the database.
- **`TODO(odilbek): …`** marks a fact the sources did not establish. A record containing it cannot
  be published (see "Publication integrity").

## Visibility semantics

`QuerySet.public()` implements these; public selectors (`apps/*/selectors.py`) are built on it.

| Rule | Applies to | Meaning |
|---|---|---|
| `is_published` | every Publishable model | False means the item is invisible to the public everywhere |
| `is_listed` | Project | False means **unlisted**: reachable at its own URL, never listed (including on profiles), `noindex`, not in the sitemap |
| Profile selection | items shown on a profile | An item appears on a profile only if a link row exists for that profile **and** the item is public |
| Both languages public | LanguagePair (not publishable itself) | A pair is public when its source and target skills both are |
| Section `is_enabled` | ProfileSection | A disabled section is never returned, preview or not |
| Profile `languages` | Profile | A language version is offered only if listed; otherwise 302 to English (Phase 4) |
| Draft preview | all | `include_drafts=True`, passed only after a staff check (Phase 4); it never reveals disabled sections |

## core ✅

```
SiteSettings (singleton: id = 1, enforced)
  owner_name*, tagline*, location*, timezone (IANA name, validated), public_email,
  availability (available | limited | unavailable | blank = not stated),
  availability_note*, response_time_note*,
  portrait → MediaAsset (images)   default hero / about photo
  seo_title*, seo_description*, default_og_image → MediaAsset

MediaAsset                         created only through apps/core/media.py (D-034)
  file (server-chosen name), kind (image | pdf), alt_text* (English required for images),
  caption*, width, height (images only), bytes, sha256 (of the upload; unique → dedupe),
  focal_x, focal_y (0–1)           keeps the subject in frame across crops
  variants (JSON)                  {"avif": {"480": path, ...}, "webp": {...}}; widths 480/960/1440/1920
                                   not exceeding the source; a narrower image keeps its own width

ImportedRecord                     import provenance: model_label, key, object_id,
                                   origin (draft = draft_content | demo = seed_demo) (D-039, D-042)
```

## accounts ✅

```
User(AbstractUser)                 email required; unique regardless of case
                                   (UniqueConstraint on Lower("email"))
```

## career: master data ✅

```
SkillCategory     name*, slug, kind (technical | language | domain | tool), order

Skill             name*, slug, category → SkillCategory, description*,
                  level_label* ("Native", "TOPIK Level 6": entered by Odilbek, never inferred),
                  Publishable, Ordered

Project           title*, slug, summary* (required to publish), context*, description* md,
                  highlights* md, role*,
                  project_status (live | in_progress | archived | concept | blank),
                  started_on, ended_on, github_url, demo_url, cover → MediaAsset,
                  is_featured, is_listed, skills ⇄ Skill,
                  Publishable, SEOFields, Ordered

ProjectMedia      project → Project, asset → MediaAsset (PROTECT), caption*, order

Experience        role*, organization*, organization_url, location*,
                  employment_type (full_time | freelance | contract | internship | volunteer | blank),
                  started_on (required to publish), ended_on (null = current),
                  summary*, highlights* md, skills ⇄ Skill, projects ⇄ Project, Publishable, Ordered

Education         institution*, credential*, field*,
                  kind (degree | course | certification | language_test | blank),
                  started_on, ended_on, result* ("TOPIK Level 6"), description*, credential_url,
                  skills ⇄ Skill, Publishable, Ordered

Service           title*, slug, summary*, description* md, pricing_note*,
                  skills ⇄ Skill, Publishable, Ordered

LanguagePair      source → Skill, target → Skill   (both in a category of kind=language),
                  modes [document | consecutive | simultaneous | localization | review],
                  domains*, note*, Ordered

ContactChannel    kind (email | telegram | whatsapp | linkedin | upwork | github | kakaotalk | other),
                  label*, url, handle (a URL or a handle is required), Publishable, Ordered
```

Spoken languages are Skills in a category of kind `language`; there is no separate Language model.
`project_status` describes the project's life, not its publication state (`is_published`).

## profiles: curated website views ✅

```
Profile           kind (home | about | role), slug (unique; reserved slugs refused for roles),
                  name*, switcher_label*, headline* (required to publish), subheadline*, intro* md,
                  hero_variant (portrait | split | bilingual | statement),
                  accent (token name; `default` until the Phase 3 token set),
                  hero_image → MediaAsset (null → SiteSettings.portrait),
                  router_prompt*, router_blurb*, show_in_switcher, show_in_router,
                  languages [site language codes; always includes en],
                  primary_cta (contact | resume | projects), primary_cta_label*,
                  contact_form_variant (general | project_inquiry | language_request),
                  Publishable, SEOFields, Ordered
                  (default_resume → Resume arrives with Resume in Phase 8)

ProfileSection    profile → Profile, section_type, heading*, intro*, body* md (custom text only),
                  layout_variant (`default` until Phase 4), item_limit (list sections only, ≥ 1),
                  anchor (slug-like, unique per profile), is_enabled, order

ProfileProject         profile, project,    order, is_featured, is_primary, summary_override*
ProfileExperience      profile, experience, order, summary_override*, highlights_override*
ProfileSkill           profile, skill,      order, is_primary (emphasised)
ProfileEducation       profile, education,  order
ProfileService         profile, service,    order
ProfileContactChannel  profile, channel,    order, is_primary (at most one per profile)
```

**Overrides** change a link row's wording for one profile only. They do not fall back across
languages: an empty Korean override shows the item's own Korean text (`effective_summary`), not the
English override.

**Section types** (one template partial each, Phase 4):

| Type | Notes |
|---|---|
| `about`, `custom_markdown` | text; only `custom_markdown` has a body, and only it may repeat |
| `evidence_strip` | computed facts (counts, year ranges); never self-rated |
| `skills`, `projects`, `experience`, `education`, `services`, `language_pairs` | the profile's linked items; may set `item_limit` |
| `resume_cta`, `contact` | calls to action and channels |
| `profile_router` | **home only** |
| `career_map`, `blog_posts` | added in Phase 11 and Phase 13 |

The **hero is not a section**: it is always first and is configured on the Profile.

## resumes: curated paper views (Phase 8)

```
Resume            profile → Profile, name, source (uploaded | generated),
                  template (classic | compact), paper (A4 | Letter),
                  headline_override*, summary_override*, extra_markdown* md,
                  show_photo, is_default, Publishable

ResumeProject / ResumeExperience / ResumeSkill / ResumeEducation
                  resume, item, order, title_override*, bullets_override* md

ResumeFile        resume → Resume, language, origin (uploaded | generated), file, bytes,
                  data_hash, is_current
```

## analytics (Phase 9)

```
Source            key (slug), name, referrer_domains (JSON list), order
Campaign          ref_code (slug, unique, lowercase), name, source → Source,
                  landing_profile → Profile (null), notes, starts_on, ends_on, is_active
DailySalt         day (unique), salt (32 random bytes)   past days are deleted
Event             id (BigAuto), occurred_at, name, path,
                  profile → (SET_NULL), project → (SET_NULL), resume → (SET_NULL),
                  channel (kind, null), campaign → (SET_NULL), ref_code (raw), source_key,
                  referrer_host, utm_source, utm_medium, utm_campaign,
                  language, country (2 letters), device (mobile | tablet | desktop),
                  visitor_hash (char 16, null)
```

Field semantics, allowed event names and retention are in `ANALYTICS.md`.

## contact (Phase 7)

```
ContactMessage    profile → Profile (null), variant, name, email, message, details (JSON),
                  language, status (new | read | replied | archived | spam), spam_reasons (JSON),
                  campaign → (null), source_key, visitor_hash,
                  notified_at, notify_attempts, notify_error
```

## blog (Phase 13)

```
Tag               name*, slug
Post              title, slug, language, translation_group (UUID), excerpt, body md,
                  cover → MediaAsset, tags ⇄ Tag, profiles ⇄ Profile, Publishable, SEOFields
```

Posts are **not** field-translated: each post row is one language (D-015).

## Constraints

**In the database.** A rule shared by many models, such as the slug format, is built by shared
code (`apps/core/constraints.py`) and tested on a representative model rather than on each table.
The model-specific rules are tested directly, except two simple ones that have no test of their
own yet: MediaAsset `bytes ≥ 1` and the ProjectMedia pair.

| Model | Constraint |
|---|---|
| every slugged model | slug format; unique |
| every Publishable model | `published_at` set when published; **no TODO marker when published** |
| every translated model | English filled (not NULL, not blank) for each required field |
| every model with links | `http(s)://` or empty |
| every model with dates | `ended_on ≥ started_on` |
| every choice field | value in the enum (or blank where "not stated" is allowed) |
| SiteSettings | a single row, id 1 |
| MediaAsset | kind valid; sha256 is 64 hex; bytes ≥ 1; images have width and height (NULL-safe), PDFs none; English alt text for images; focal point in 0–1 |
| ImportedRecord | unique `(model_label, key)`; origin valid |
| Project | summary required to publish |
| ProjectMedia | unique `(project, asset)` |
| Experience | start date required to publish |
| LanguagePair | `source ≠ target`; unique pair; modes non-empty and known |
| ContactChannel | a URL or a handle |
| Profile | at most one `home` and one `about`; role slugs not reserved; languages include `en` and are site languages; headline required to publish |
| ProfileSection | type valid; layout valid for type; one per `(profile, type)` except `custom_markdown`; body only for `custom_markdown`; `item_limit` only on list sections and ≥ 1; anchor format and unique per profile; **no TODO marker when enabled** |
| every link table | unique `(profile, item)` |
| ProfileProject | at most one `is_primary` per project |
| ProfileContactChannel | at most one `is_primary` per profile |

**In the application** (they need another table, which a CHECK constraint cannot read):

| Rule | Where |
|---|---|
| `profile_router` sections on home profiles only; a home with one cannot change kind | `ProfileSection.clean()`, `Profile.clean()`, `profiles.services.add_section()` |
| a role slug may not be the environment's admin path | `Profile.clean()` (`apps.core.slugs.validate_not_reserved`) |
| language-pair skills are spoken languages | `LanguagePair.clean()`, admin choices |
| related text a record displays is TODO-free before publishing | `apps.core.services.publish()` via `publication_blockers()` |
| a primary profile must show the project | `profiles.services.set_primary_profile()` |

## Relationships

```
SkillCategory ──< Skill ⇄ Project, Experience, Education, Service
                  Skill ──< LanguagePair (source, target)
Experience ⇄ Project
Project ──< ProjectMedia >── MediaAsset
Profile ──< ProfileSection
Profile ──< Profile{Project,Experience,Skill,Education,Service,ContactChannel} >── master item
Profile ──< Resume ──< Resume{Project,Experience,Skill,Education} >── master item   (Phase 8)
                   └──< ResumeFile (per language, uploaded | generated)
Event ──> Profile / Project / Resume / Campaign (SET_NULL)     Campaign ──> Source   (Phase 9)
ContactMessage ──> Profile, Campaign                                              (Phase 7)
```

## Resolved questions (Phase 2)

1. **`Project.primary_profile`** → `ProfileProject.is_primary` (D-033).
2. **Layout variants per section type** → a code-level map enforced by the database, with one
   `default` layout per type until Phase 4 designs the variants (D-037).
