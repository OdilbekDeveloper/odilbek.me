# DATA MODEL

The planned schema. **Only `accounts.User` exists so far** (Phase 1). The rest is built in
Phase 2, except contact (Phase 7), resumes (Phase 8), analytics (Phase 9) and blog (Phase 13). Changes to this document
during implementation are logged in `DECISIONS.md`.

## Conventions

| Mark | Meaning |
|---|---|
| `*` | translated field (django-modeltranslation: `_en`, `_ko`, `_uz`; only `_en` required) |
| `md` | Markdown source, rendered through the shared sanitizing renderer |
| `⇄` | many-to-many |
| `→` | foreign key |

**Abstract bases (in `core`):**
- `TimeStamped(created_at, updated_at)`, applied to every model
- `Ordered(order)`: a positive integer, indexed; lists sort by `order, id`
- `Publishable(is_published, published_at)`
- `SEOFields(seo_title*, seo_description*, og_image→MediaAsset)`
- `ProfileLink` / `ResumeLink`: the shared base for link tables (`order`, a unique pair, the
  override fields defined per table)

**Other conventions:**
- Slugs are ASCII, unique per model, and **never translated**.
- Dates of work and study are `DateField`s; display precision is month/year.
- Choices are `TextChoices` enums in code, never free text.

## Visibility semantics

These rules are what `QuerySet.public()` implements. Public selectors must use them.

| Rule | Applies to | Meaning |
|---|---|---|
| `is_published` | every Publishable model | False means the item is invisible to the public everywhere |
| `is_listed` | Project | False means **unlisted**: reachable at its own URL, never listed, `noindex`, not in the sitemap |
| Profile selection | items shown on a profile | An item appears on a profile only if a link row exists for that profile **and** the item is public |
| Section `is_enabled` | ProfileSection | A disabled section is not rendered |
| Profile `languages` | Profile | A language version is offered only if listed; otherwise 302 to English |
| Draft preview | all | Staff with `?preview=1` see unpublished content, with `Cache-Control: no-store` |

## core

```
SiteSettings (singleton, pk=1)
  owner_name*, tagline*, location*, timezone, public_email,
  availability (available | limited | unavailable), availability_note*, response_time_note*,
  portrait → MediaAsset            default hero / about photo
  seo_title*, seo_description*, default_og_image → MediaAsset

MediaAsset
  file, kind (image | pdf), alt_text* (required for images), caption*,
  width, height, bytes, sha256 (unique → dedupe),
  focal_x, focal_y (0–1)           keeps the subject in frame across crops
  variants (JSON)                  {format: {width: path}}, AVIF/WebP at 480/960/1440/1920, never upscaled
```

## accounts

```
User(AbstractUser)                 email required; unique regardless of case
                                   (UniqueConstraint on Lower("email"))          ✅ Phase 1
```

## career: master data

```
SkillCategory     name*, slug, kind (technical | language | domain | tool), order

Skill             name*, slug, category → SkillCategory, description*,
                  level_label* ("Native", "TOPIK Level 6" — entered by Odilbek, never inferred),
                  Publishable, Ordered

Project           title*, slug, summary*, context*, description* md, highlights* md, role*,
                  project_status (live | in_progress | archived | concept),
                  started_on, ended_on, github_url, demo_url, cover → MediaAsset,
                  is_featured, is_listed, primary_profile → Profile (null),
                  skills ⇄ Skill, Publishable, SEOFields, Ordered

ProjectMedia      project → Project, asset → MediaAsset, caption*, order

Experience        role*, organization*, organization_url, location*,
                  employment_type (full_time | freelance | contract | internship | volunteer),
                  started_on, ended_on (null = present), summary*, highlights* md,
                  skills ⇄ Skill, projects ⇄ Project, Publishable, Ordered

Education         institution*, credential*, field*,
                  kind (degree | course | certification | language_test),
                  started_on, ended_on, result* ("TOPIK Level 6"), description*, credential_url,
                  skills ⇄ Skill, Publishable, Ordered

Service           title*, slug, summary*, description* md, pricing_note*,
                  skills ⇄ Skill, Publishable, Ordered

LanguagePair      source → Skill, target → Skill   (both in a category of kind=language),
                  modes (multi: document | consecutive | simultaneous | localization | review),
                  domains*, note*, Ordered

ContactChannel    kind (email | telegram | whatsapp | linkedin | upwork | github | kakaotalk | other),
                  label*, url, handle, Publishable, Ordered
```

`project_status` describes the project's life (live, archived…). It is **not** publication
state; that is `is_published`.

## profiles: curated website views

```
Profile           kind (home | about | role), slug (unique, reserved-slug validator),
                  name*, switcher_label*, headline*, subheadline*, intro* md,
                  hero_variant (portrait | split | bilingual | statement),
                  accent (token name from a fixed set),
                  hero_image → MediaAsset (null → SiteSettings.portrait),
                  router_prompt*, router_blurb*, show_in_switcher, show_in_router,
                  languages (JSON list ⊆ settings.LANGUAGES),
                  primary_cta (contact | resume | projects), primary_cta_label*,
                  contact_form_variant (general | project_inquiry | language_request),
                  default_resume → Resume (null),
                  Publishable, SEOFields, Ordered

ProfileSection    profile → Profile, section_type, heading*, intro*, body* md (custom_markdown only),
                  layout_variant, item_limit (null), anchor, is_enabled, order

ProfileProject         profile, project,    order, is_featured, summary_override*
ProfileExperience      profile, experience, order, summary_override*, highlights_override*
ProfileSkill           profile, skill,      order, is_primary
ProfileEducation       profile, education,  order
ProfileService         profile, service,    order
ProfileContactChannel  profile, channel,    order, is_primary
```

**Section types** (one template partial each):

| Type | Notes |
|---|---|
| `about`, `custom_markdown` | text |
| `evidence_strip` | computed facts (counts, year ranges); never self-rated |
| `skills`, `projects`, `experience`, `education`, `services`, `language_pairs` | render the profile's linked items |
| `resume_cta`, `contact` | calls to action and channels |
| `profile_router` | **home only**: the "where should we start?" routes |
| `career_map` | Phase 11 |
| `blog_posts` | Phase 13 |

The **hero is not a section**: it is always first and is configured on the Profile. Layout
variants per section type are defined in Phase 4, as a code-level map validated on save.

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

| Model | Constraint |
|---|---|
| Profile | exactly one `kind=home`; at most one `kind=about`; slug not reserved |
| ProfileSection | unique `(profile, section_type)` except `custom_markdown`; `section_type` allowed for `profile.kind`; `layout_variant` valid for `section_type` |
| every link table | unique `(parent, item)` |
| Resume | at most one `is_default` per profile |
| ResumeFile | at most one `is_current` per `(resume, language, origin)` |
| LanguagePair | `source ≠ target`; both skills belong to a `kind=language` category |
| Campaign | `ref_code` lowercase, unique |
| MediaAsset | `sha256` unique; `alt_text_en` required when `kind=image` |

## Relationships

```
SkillCategory ──< Skill ⇄ Project, Experience, Education, Service
                  Skill ──< LanguagePair (source, target)
Experience ⇄ Project
Profile ──< ProfileSection
Profile ──< Profile{Project,Experience,Skill,Education,Service,ContactChannel} >── master item
Profile ──< Resume ──< Resume{Project,Experience,Skill,Education} >── master item
                   └──< ResumeFile (per language, uploaded | generated)
Event ──> Profile / Project / Resume / Campaign (SET_NULL)     Campaign ──> Source
ContactMessage ──> Profile, Campaign
```

## Open questions for Phase 2 planning

1. **`Project.primary_profile`** makes `career` depend on `profiles`, against the one-way
   dependency rule in `ARCHITECTURE.md`. The alternative is `ProfileProject.is_primary` (at most
   one per project), which keeps `career` independent. Decide in Phase 2 planning and log it.
2. **Layout variants per section type**: the exact list is a Phase 4 design question. Phase 2
   only needs the field and a validation hook.
