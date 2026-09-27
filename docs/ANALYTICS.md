# ANALYTICS

Privacy-friendly, first-party, aggregated analytics with a reusable referral/campaign system
(D-016). Built in Phase 9.

## 1. Principles

- **Cookieless.** No analytics cookies, local storage identifiers or fingerprinting beyond the
  daily hash below. There is no consent banner because nothing requires one.
- **Aggregated, never individual.** There are no visitor profiles, no session replay and no
  cross-day identity.
- **Never stored:** IP addresses, full user agents, or anything that links a visitor across days.
- **Excluded:** Odilbek's own visits (staff sessions) and recognisable bots.
- **Honest about limits** (section 9).

## 2. Events

| Event | Emitted by | Carries |
|---|---|---|
| `page_view` | JS beacon, on pages that are not profiles or projects | path |
| `profile_view` | JS beacon, on profile pages (including home and about) | profile |
| `project_view` | JS beacon, on project pages | project |
| `channel_click` | JS delegated listener on links with `data-track-channel` | channel kind |
| `resume_download` | **server-side**, in the PDF view (so direct links from Upwork etc. still count) | resume, profile, language |
| `contact_submit` | **server-side**, in the contact view | profile, form variant |

Each page emits exactly one view event; its name is chosen by the page type. "Page views" in
reports means all three view events.

Clicks on channels such as `github_click`, `telegram_click`, `whatsapp_click`, `linkedin_click`
and `upwork_click` are all **`channel_click` with a `channel` value** (`github`, `telegram`, …).
Adding a new channel in the dashboard (e.g. KakaoTalk) therefore needs no code.

## 3. What each event records

| Field | Source | Notes |
|---|---|---|
| `occurred_at` | server clock | UTC |
| `name`, `path` | beacon / view | name from an allowlist; path length-capped |
| `profile`, `project`, `resume`, `channel` | page data attributes / view | foreign keys `SET_NULL` on delete |
| `campaign`, `ref_code` | `?ref=` | raw `ref_code` is kept even when no campaign matches |
| `utm_source`, `utm_medium`, `utm_campaign` | query string | length-capped |
| `source_key` | classified referrer or campaign | e.g. `linkedin`, `google`, `naver`, `direct` |
| `referrer_host` | `document.referrer` | **host only**, never the full URL |
| `language` | site language of the page | `en` / `ko` / `uz` |
| `country` | `CF-IPCountry` header | 2 letters; nothing finer |
| `device` | derived from the UA | `mobile` / `tablet` / `desktop`; the UA itself is discarded |
| `visitor_hash` | section 5 | 16 hex chars; null under Global Privacy Control |

## 4. Data flow

1. **The page** renders `data-event`, `data-profile` and `data-project` on `<body>`.
2. **`track.js`** (about 1 KB) reads them together with `ref` and `utm_*` from the URL and
   `document.referrer`. It sends them with `navigator.sendBeacon('/e/')`, falling back to
   `fetch(…, {keepalive: true})`. It then removes `ref` and `utm_*` from the address bar with
   `history.replaceState`, so a shared link never carries someone else's attribution.
3. **`/e/`** processes each beacon in order:
   1. POST only; `Origin` must be the site's own origin; body ≤ 2 KB; event name on the allowlist
   2. drop known bot user agents; apply a rate limit per IP; skip staff sessions
   3. compute `visitor_hash` (section 5)
   4. classify the referrer host into a `Source` using `Source.referrer_domains`
   5. resolve attribution (section 6)
   6. insert the `Event` and return `204`
4. **Server-side events** (`resume_download`, `contact_submit`) go through the same hashing and
   attribution service inside their views.

## 5. Visitor hash and salts

```
visitor_hash = sha256(today's salt ‖ client IP ‖ user agent ‖ host)[:16]
```

- `DailySalt` holds one **random** 32-byte salt per day. It is not derived from `SECRET_KEY`,
  so nobody, including the site owner, can recompute it.
- Past salts are deleted by the daily maintenance job. Once a salt is gone, hashes from that day
  cannot be linked to any IP or to any other day.
- The client IP comes from `CF-Connecting-IP` only when the origin lock verifies (`SECURITY.md`).
- **Global Privacy Control:** when `Sec-GPC: 1` is present, the event is recorded with
  `visitor_hash = null`. It counts as a page view but not as a unique visitor or funnel step.

## 6. Referral and campaign attribution

**Campaigns** are a reusable system; no source is hard-coded.
- **`Source`** is a channel such as `upwork`, `linkedin`, `telegram`, `google`, `naver`,
  `yandex`, `kakao`, `github`, `email` or `direct`. Each has a list of referrer domains for
  automatic classification. Sources are seeded and editable in the dashboard.
- **`Campaign`** is a specific effort with a `ref_code` (e.g. `upwork-sept-2026`), a source, an
  optional landing profile, notes and dates.
- **Link builder:** in the dashboard, pick a profile and a campaign and copy
  `https://odilbek.me/<profile>/?ref=<ref_code>`. Links work on any page, e.g. `/?ref=…` or
  `/ko/translator/?ref=…`.

**Precedence** for each event, first match wins:

| # | Signal | Result |
|---|---|---|
| 1 | `ref` matches a `Campaign.ref_code` | that campaign and its source |
| 2 | `ref` present but unknown | raw `ref_code` stored (listed in the dashboard as "unregistered ref → create campaign"); the source is still resolved by rows 3–6 |
| 3 | `utm_source` present | source from UTM |
| 4 | an earlier event **today** with the same `visitor_hash` has attribution | inherit it |
| 5 | referrer host matches a `Source` | that source |
| 6 | otherwise | `direct` |

`ContactMessage` copies the attribution of its submission, so a lead always shows where it came
from, even beyond the one-day window.

## 7. Retention

- **Salts:** deleted once their day has passed.
- **Events:** deleted after `ANALYTICS_RETENTION_DAYS` (default 395, about 13 months, which keeps
  year-over-year comparisons).
- **Rollups:** daily rollup tables are added **only if** report queries become slow, which is
  unlikely at personal-site volume. Until then, reports aggregate raw events.

## 8. Reports (dashboard)

Reports are built with ORM aggregation and server-rendered SVG/CSS charts; no chart library at first.

| Report | Definition |
|---|---|
| Visitors | distinct `visitor_hash` per day, labelled "daily visitors". Over a range, summed as "visitor-days" |
| Page / profile / project views | event counts |
| CV downloads | `resume_download` by profile and language |
| Contact interactions | `channel_click` by channel, plus `contact_submit` |
| Traffic sources | view events grouped by `source_key` and campaign |
| Popular projects | `project_view` counts |
| **Funnel** (per campaign or source) | distinct same-day `visitor_hash` values reaching: visit → `profile_view` → `project_view` → `resume_download` → `channel_click` or `contact_submit` |

## 9. Known limitations (accepted)

- **Same-day funnels only.** A visitor who arrives from Upwork on Monday and downloads the CV on
  Tuesday appears as two visitors. The funnel undercounts multi-day journeys, while contact
  messages keep their attribution.
- **Visitor-days, not people,** when uniques are summed over a range.
- **Visitors behind the same network and browser** on the same day share a hash (e.g. an office).
- **Visitors blocking JavaScript beacons** are not counted in views. Downloads and contact
  submissions are still counted server-side.

## 10. Transparency

`/privacy/` states in plain language what is collected, what isn't, how long it is kept, and how
GPC is honoured. It must be updated whenever this document changes.
