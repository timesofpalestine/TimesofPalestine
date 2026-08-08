# Photo-conversion queue

The charter's covers-are-photographs order (2026-08-03) works through this
queue: stories running on a house-SVG or category-cover stopgap that should
get a rights-cleared photo. The daily editor cycle takes items from the top;
every conversion needs a media-rights.json entry (asset, rightsBasis,
credit, licenseUrl). Remove an entry when the photo ships. Franchise covers
(TOP 100, the scholarship map) are brand art and exempt.

## Priority 0 — standing override

| Story / pid | Current stopgap | What's needed |
| --- | --- | --- |
| pid 287efd3ca4 (image-overrides.json, 2026-08-03: "runs until a better photo is chosen") | branded Gaza cover | rights-cleared frame of the same event without faces of mourners |

## Priority A — chart/timeline/figures-board covers (direct violations of the covers-are-photographs order)

These covers are infographics; the order says infographics belong in the
body and the cover must be a photo. Convert first. Identified slugs:

| Slug | Current cover |
| --- | --- |
| chile-palestinian-friendship-day-bill-2026 | timeline SVG |
| france-pause-gaza-scholars-artists-court-2026 | timeline SVG |
| gaza-prosthetics-pipeline-2026-08-01-12 | pipeline chart SVG |
| madrid-palestinian-culture-pact-accountability-2026 | figures/flow SVG |
| pa-litigation-docket-2026 | docket board SVG |
| palestinian-table-reems-california-2026 | franchise card SVG (Commons/press-kit photo of Reem's Jack London Square or a mana'oushe) |
| west-bank-displacement-ledger-2026-08-08-05 | OCHA figures ledger SVG |
| gaza-ceasefire-day294-report-2026 | by-the-numbers board SVG |
| settlement-budget-34-outposts-2026-08-08-12 | budget figures SVG |
| arab-support-monitor-2026 | ledger board SVG |
| east-asia-palestine-development-projects-2026 | projects board SVG |
| palestine-top-companies-2026 | market-value board SVG |
| palestine-embassies-directory-2026 | directory board SVG |
| pa-prime-ministers-record-2026 | timeline SVG (Commons frame of a PA cabinet sitting or the Muqata'a) |
| palestine-banks-owners-2026 | clearing diagram SVG (bank branch photo, Commons) |
| paltel-ooredoo-spectrum-2026 | spectrum diagram SVG (Jawwal/Ooredoo storefront or tower, Commons) |

## Priority B — photoless stories on generic category-cover fallback

No `image:` header at all; these run on the branded category covers.
Each needs a rights-cleared photo (or, failing that, a house subject SVG
as interim). Slugs (non-israelipress): agora-palestine-bitcoin-aid-fund,
dedevelopment-to-depopulation, donor-aid-what-reaches-the-treasury,
financial-freedom, gaza-clay-house-model-rebuild-2026-08-07,
gaza-dialysis-chronic-care-2026-08-04-12, gaza-money-toll,
gaza-population-transfer-proposals, joe-kent-israel-debate-2026,
menaa-workshop, pa-budget-line-by-line, palestinian-4g-rollout-2027-gaza-2g,
settler-attacks-week-westbank-2026-08-07,
turkey-indonesia-palestinian-student-funds-2026,
west-bank-camp-displacement-machinery-2026, westbank-annexation-machinery,
who-profits-palestinian-economy-2026-07-30-05.

The **israelipress section (37 slugs as of 2026-08-08)** now carries the
reusable section SVG (`/media/times-of-palestine-israeli-press.svg`) in
every item's `image:` header — no longer bare category fallback, but the
items still need real photos: front-page thumbnails where fair-dealing
quotation applies, else per-story rights-cleared art.

## Priority C — house-SVG subject illustrations (sanctioned stopgap, lowest priority)

Subject illustrations are the charter's approved interim visual; upgrade
opportunistically:

| Story | What's needed |
| --- | --- |
| shabjdeed-kufr-aqab-arab-rap-2026-08-07 | rights-cleared performance photo (BLTNM press kit / Commons) |
| washington-brief franchise | rotate per-edition subject portraits from Commons as briefs change subject (Mladenov Commons portrait currently healthy) |
| tomorrows-youth-organization-nablus-2026 | rights-cleared photo of the TYO centre or a program session — ask the organization's press contact, or Commons; manifest entry required |
| masri-britain-owes-palestine-2026 | upgrade: the family's own Downing Street photo (grandfather and grandson at the gates), rights-cleared from Munib al-Masri or the BOP campaign (OGL Downing Street photo currently healthy) |
| tareq-abbas-businessman-2026 / tarek-aggad-apic-2026 | rights-cleared portraits (Commons or press-kit) for both profiles, with manifest entries |
| sherry-sabbagh-dearborn-cook-2026 | rights-cleared portrait or kitchen photo — her Instagram (@sherryhour) and Food Network promo shots are copyrighted; ask her directly or the Food Network press room, or an owner-supplied photo, with manifest entry |
| azza-hamid-gaza-business-award-2026, mustafa-abuelhija-comedy-2026, nasrallah-neustadt-laureate-2026, her-story-palestinian-women-2026, bitchat and the remaining subject-SVG covers | rights-cleared subject photos with manifest entries as they surface |
