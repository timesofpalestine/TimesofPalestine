# story-archive/ — the permalink-permanence ledger

**Do not delete this directory or its files.** (Owner order 2026-08-09.)

Every story page the build publishes is persisted here as one small JSON
record per story and language (`<lang>/<pid>.json`), committed back to the
repo by the workflow's post-deploy persist step. On every future build,
records whose stories are no longer in the live feeds are re-rendered at
their original URLs — so links already shared to the Telegram channel,
by readers, or indexed by search engines keep resolving forever, while the
front page stays fully live.

Rules:

- Archived stories never re-enter the front page, feeds, sitemaps or
  delivery outboxes. They keep their page, their bare-pid share stub, a
  section-archive card and a search-index entry. Nothing squats.
- Retractions win: a pid in `RETRACTED_PIDS` (build.py) is never
  re-rendered, even if its record remains here.
- Corrections win: `editorial/corrections.json` entries are re-attached on
  every render, so archived pages carry late corrections too.
- To take a single archived story down permanently, add its pid to
  `RETRACTED_PIDS` (preferred, survives everything) — deleting the JSON
  alone also works but leaves no record of the takedown.
- Records are written by `story_archive.py` via `build.py`; agents don't
  hand-edit them except to correct a factual field, and never re-add a
  record for a retracted story.
