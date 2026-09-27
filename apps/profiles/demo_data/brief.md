# The demo universe

A fictional career used to develop and test odilbek.me. **Nothing here is true of anyone.** It is
not Odilbek's biography and must never be presented as such. `manage.py seed_demo` loads it
(docs/CONTENT_IMPORT.md, "Demo content"). Every demo record cites this file as its source, the
way a real draft cites a CV.

- `manifest.json`: the dataset, in the same format as a real draft manifest.
- `review.json`: what a reviewer would then do in the admin (publish, per-profile wording,
  galleries, SEO, availability). The import format deliberately leaves these to review.
- The images are generated when the command runs (abstract shapes marked "DEMO"). None is a
  photograph, and none is committed.

All figures, organizations, dates and descriptions are invented. Every link and address uses the
reserved `example.com` / `example.org` domains.

## The persona

**Alex Demo** (알렉스 데모) is an invented backend developer and Korean–English technical
interpreter based in Seoul. English is Alex's first language; Korean is near-native.

## Timeline

| When | What | Where (all fictional) |
|---|---|---|
| 2014-03 to 2018-02 | BSc in Computer Science | Lindenhall University |
| 2016-03 to 2016-12 | Volunteer conversation tutor (a draft, never published) | Lantern Street Language Café |
| 2017-07 to 2017-12 | Backend developer intern | Brightkeel Systems |
| 2018-03 to 2018-12 | Professional interpreting program (Korean–English) | Saebyeol Institute of Interpretation and Translation |
| 2019-01 to 2020-02 | Korean–English technical interpreter (contract) | Hanbit–Meridian Joint Engineering Consortium for Smart Port Logistics |
| 2019-11 | Advanced Korean proficiency examination, level 6 of 6 | Hanmaru Language Assessment Board |
| 2020-03 to 2023-08 | Backend developer (full-time) | Northgale Systems |
| 2023-09 to now | Automation engineer (freelance) | Cobaltine Automation |

## Profiles

| Profile | Slug | Languages | Notes |
|---|---|---|---|
| Home | `home` | EN, KO | router, evidence strip, three featured projects |
| About | `about` | EN, KO | the whole person; a custom "How I work" section |
| Backend Developer | `developer` | EN, KO | the widest profile; its CV section is disabled until Phase 8 |
| Korean Translator and Interpreter | `translator` | EN, KO | its own hero image; one disabled section |
| AI and Automation | `ai-automation` | EN only | newer: in the switcher, not on the home router |
| Technical Writer | `technical-writer` | EN | an unpublished draft carrying TODO notes |

## Projects

The primary profile is listed first.

| Project | Status | Profiles |
|---|---|---|
| Atlas Workflow Engine | live | developer, home |
| RelayBot Operations Platform | live | ai-automation, developer, home |
| ContextDesk AI Assistant | in progress | ai-automation, developer, home |
| HanBridge Localization Hub | live | translator, developer, ai-automation, home |
| Beacon Operations Console | archived | developer |
| SignalFlow Data Pipeline | live | ai-automation |
| Northgale Clinic and Studio Booking Platform with Multilingual Reminders | live | developer, translator |
| PulseTrack Clinical Data Prototype | concept; **unpublished draft** | developer |
| QuickForm API | archived | developer |
| Smart Port Logistics Terminology Glossary | archived | translator |
| Ledgerline Invoice Reconciliation Service | archived; **unlisted** | developer |

## Deliberate test cases

- **Hidden records:**
  - unpublished drafts: the PulseTrack project, the Rust skill, the volunteer role, the subtitle
    service, the KakaoTalk channel and the Technical Writer profile
  - Ledgerline is published but unlisted
  - two sections are disabled
- **One record, several views:** HanBridge appears on three role profiles and Northgale's booking
  platform on two, as single records. A link override rewords HanBridge on AI and Automation and
  the booking platform on the translator profile. The Cobaltine role carries a different override
  on each role profile. Its translator override is English-only, so the Korean page shows the
  role's own Korean summary.
- **English fallback:** technical skill names (Python, Django, …), the Beacon description,
  SignalFlow's highlights, the LinkedIn label and the whole AI and Automation profile have no
  Korean text.
- **Layout stress:**
  - a long English project title (Northgale) and a long Korean one (the port glossary)
  - a long organization name (the consortium)
  - long Korean descriptions (Atlas, HanBridge, the About intro)
  - projects with nine skills (SignalFlow) and with two (QuickForm)
  - projects with and without covers; a cover narrower than the smallest variant (QuickForm)
  - current and finished roles; every employment type
- **The media pipeline:**
  - PNG, JPEG, WebP and AVIF sources
  - a portrait JPEG carrying a fake camera, fake GPS coordinates and a rotation flag; the
    pipeline must strip the metadata and apply the rotation
  - one cover large enough for every variant width
