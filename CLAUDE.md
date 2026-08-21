# Times of Palestine — newsroom charter for AI agents

Multiple AI agents (ChatGPT/Codex, GitHub Copilot, Claude) work on this repo on
behalf of the owner. This file records the owner's standing decisions. **Do not
undo another agent's layer to make your own change** — graft your change onto
what is there, and when two approaches conflict, open a PR and let the owner
decide rather than force-replacing files.

## GUIDING PRINCIPLE — the page is alive (owner directive 2026-07-30)

Times of Palestine is a DYNAMIC news site: every visit, every refresh should
show fresh information. Given the weight of the name, the standard is the
world's great news fronts — The Times, the NYT. Every agent applies this to
everything it builds:

- The top story follows the news cycle (freshest-window hero selection) and
  is never a multi-day-old feature. Nothing reader-facing may "squat".
- The site builds and deploys every 10 minutes; changes that slow the refresh
  chain or cache staleness into the reader's view are regressions.
- Fresh stories carry the pulsing NEW/جديد mark (under 90 minutes);
  timestamps are minute-level and honest; the breaking ticker stays
  chronological.
- Features, research and archive material keep their prominence in their own
  sections — never at the expense of the live top of the page.
- When adding any surface (section, page, widget), ask: what makes this feel
  alive an hour from now? If nothing does, redesign it.
- **Every section, both editions, updates at least daily (owner order
  2026-08-11).** `section_freshness.py` is the measure: the build writes
  `dist/section-freshness.json` and announces stale sections; the
  investigations desk (`originals_gen._pick_topic`) targets the stalest
  section's queued topic first; dedicated category-pinned wire feeds keep
  sports/economy/women/prisoners supplied; and the daily editor treats every
  STALE line as a same-day assignment. Thresholds are tuned in
  `section_freshness.py` (archive is exempt — owner-supplied only). No agent
  removes these hooks; a starving section means "add feeds and topics",
  never "hide the section".

## Owner decisions currently in force (2026-07-29)

1. **The AI newsroom is ON — deliberately.** The build uses the Anthropic API
   in two places, and the owner has approved the cost (~$150–200/month):
   - **Briefs desk** (`build.py`, `claude-haiku-4-5`): every wire item is
     rewritten in-house before publication. Wire-first policy: an item
     publishes only when its rewrite exists, is complete, and passes the
     refusal screen. Never publish raw truncated feed summaries as articles.
   - **Investigations desk** (`originals_gen.py`, `claude-opus-5` + web
     search): files at most 3 researched bilingual reports/day at 05/12/19 UTC
     (`DESK_HOURS`). Owner-approved cadence — don't raise it without asking.
   - In `.github/workflows/build.yml` this requires: the
     `pip install anthropic` step, `ANTHROPIC_API_KEY` on the build step,
     `permissions: contents: write` (the desk commits its reports), and
     `INVESTIGATIONS: ${{ vars.INVESTIGATIONS }}`. **Do not remove these.**
     To pause the desk, set the `INVESTIGATIONS` repo variable to `off` —
     never hardcode `off` in the workflow.
2. **Telegram delivery** (`telegram_publish.py`, tests, delivery cache) is
   Codex's layer. Keep it; don't fold it back into `build.py`.
3. **Editorial rules:** no sources/bibliography sections in articles —
   attribution lives inline in the prose. Report the issue, never the
   individual. Both language editions are first-class; verify rendering
   changes in `/en/` and `/ar/`. Use constructive, good-faith framing for
   civic, cultural, diplomatic, humanitarian and institutional initiatives:
   give clear credit for worthwhile intentions, commitments and delivered
   work supported by the record; never imply bad faith merely because funding,
   governance or implementation details are still being developed. Distinguish
   what is promised, funded, underway, completed and still needed, and present
   pending work as the next practical stage. This tone rule does not suppress
   verified harm, material failures or accountability reporting; it requires
   precise evidence and fair language rather than cynicism or insinuation
   (owner decision 2026-07-30, given via ChatGPT and confirmed directly to
   Claude the same day).
   **Features celebrate their subject (owner order 2026-08-05, binding on
   every agent and every desk):** a profile or feature — arts, culture,
   sports, diaspora, humans, any piece whose subject is a person's work and
   journey — is written to CELEBRATE that person. The achievement is the
   story; the register is the culture pages of a great newspaper, never an
   audit. Exile and distance from Palestine are told with empathy from the
   subject's side (the war and the closure keep Palestinians from home) —
   NEVER framed as contradiction, hypocrisy or a gap in sincerity, and never
   a gotcha headline ("…books forty dates, none in Gaza" is the banned
   pattern). A genuine, well-sourced controversy may appear briefly as fair
   body context with the subject's answer beside it — never the lede,
   headline or closing note. This order came after the desk turned the
   owner-requested Saint Levant feature critical; the rewrite is
   `saint-levant-gaza-rap-2026-08-05-05.*` and the desk prompt now carries
   the same rule. Accountability reporting on office-holders and
   institutions is unaffected.
   **Arabic quality (owner decision 2026-07-30):** the Arabic edition is
   written fresh as native Arabic journalism — the register of الجزيرة نت /
   عرب 48 — never translationese; a reader must not sense English syntax
   underneath. Headlines especially: composed fresh using Arabic front-page
   patterns (verbal sentences, the two-dot pivot «بعد كذا.. حدث كذا», colon
   attribution, direct questions), never a translated English headline.
   Before writing Arabic, study native headlines from the site's Arabic wire
   feeds as register models. Lock facts and evidence first, then structure the
   Arabic for an Arabic reader rather than preserving English word order.
   Every edition gets a separate Arabic-only line edit and read-aloud pass;
   follow `editorial/arabic-style-guide.md`. Arabic headlines should normally
   be 6–10 words, use an active construction and name the responsible actor
   or institution whenever the reporting identifies one; never hide a known
   actor behind passive or agentless wording. Applies to every agent.
   **Transliterated names are verified, never guessed (owner order
   2026-08-11):** before an Arabic edition uses a name that arrived through
   English or Hebrew, check its spelling against Arabic-language sources on
   the same story and record it in `editorial/arabic-names.json` (see the
   style guide's names section); `build.py` flags the lexicon's known wrong
   variants like machine diction. The order came after «الهدالين» ran for
   «الهذالين».
   **Wire attribution protocol (owner decision 2026-07-30):** a rewritten
   story is OUR copy. The source outlet is named exactly once, inline, in
   the prose ("…, the Ma'an news agency reported"). No byline credit-links,
   no "read the full story at …" buttons, no outlet links or outlet chips on
   story pages or cards — reader-facing source identity is Times of
   Palestine. JSON-LD `isBasedOn`/`citation` metadata keeps the machine-
   readable source record. Dek-fallback pages (briefs layer down, source's
   own summary as body) are the one exception and keep the outlet link.
4. **Publishing safety:** event-level dedupe (one incident, one article) and
   the completeness gate (no mid-sentence bodies) in `build.py` are
   owner-requested. **AI duplicate judge (owner order 2026-08-09, after
   repeated double-article reports):** lexical similarity cannot see
   paraphrase-level duplicates, so after the lexical nets the briefs model
   adjudicates suspect pairs (close in time, shared substance, no
   place/count contradiction) with one question — one story or two.
   Verdicts cache per story-pair in briefs-cache.json (each pair costs one
   small call ever, ≤40/build); fail-open on every route. Layer:
   `adjudicate_duplicates` in `build.py`. Don't replace it with another
   word-matching net — that approach is the documented root cause. Markdown-residue in an original skips that article with a
   loud warning; schema and missing-media errors fail the build. Editorial
   gating must default to publish — never to holding coverage behind
   per-story manual approval, and NEVER with reader-facing labels
   ("developing report", "awaiting review" etc.) on any story (owner
   decision 2026-07-30). Review tracking is internal-only
   (dist/review-queue.json, a build output — never committed).
5. **Story imagery: keep photos (owner decision 2026-07-30).** Aggregated
   stories fetch and display upstream social-preview images (og:image); story
   cards must not go photoless. Any rights-strict mode (self-owned assets
   only) is an opt-in flag, default OFF.
   **Photo-desk override (owner order 2026-08-03):** a specific story's
   image can be replaced editorially via `editorial/image-overrides.json`
   (pid → `"cover"`, a local `/media/` asset, or a rights-cleared URL) —
   the override holds through every rebuild. Use it when a wire frame is
   unusable (faces cut, graphic content); never leave a story photoless.
6. **Zero third-party Python deps in the build path** except `anthropic`
   (installed in CI). `build.py`/`longform.py` stay stdlib-only otherwise.
7. **Never commit** `__pycache__/`, `dist/`, cache/state JSON — see
   `.gitignore`. Never commit secrets; `TELEGRAM_BOT_TOKEN` and
   `ANTHROPIC_API_KEY` live in GitHub secrets only.
8. **Bitcoin dispatch desk (owner-approved 2026-08-02, Copilot PR #9):**
   `bitcoin_dispatch.py` + `.github/workflows/bitcoin-dispatch.yml` file an
   OpenAI-powered bilingual original on the financial-freedom beat every
   48 h. Requires the `OPENAI_API_KEY` repo secret (skips gracefully without
   it). Pause via the Actions tab; the script is fail-open and must never
   block the news build.
9. **Permalink permanence (owner order 2026-08-09):** a published story link
   never dies. Every rendered story persists to `story-archive/` (one JSON
   per story+language, committed by the workflow's post-deploy persist
   step) and is re-rendered at its original URL on every future build after
   it leaves the live feeds — links shared to Telegram and beyond keep
   resolving forever. Archived stories keep their page, bare-pid stub,
   section-archive card and search entry, but never re-enter the front
   page, feeds, sitemaps or delivery outboxes ("the page is alive" is
   untouched). Retractions (`RETRACTED_PIDS`) always win. No agent deletes
   `story-archive/` or drops the `git add story-archive/` line from
   `build.yml`. Layer: `story_archive.py` + hooks in `build.py`.
10. **Daily editor-in-chief cycle (owner directive 2026-08-01):** Claude runs
   `.github/workflows/daily-editor.yml` each morning (06:30 UTC), choosing and
   shipping 3–5 improvements a day across editorial, design, platform and the
   franchises, via a `claude/daily-editor-<date>` PR merged on green CI. Other
   agents: expect a daily PR with this prefix; don't revert its layers —
   disagreements go to issue #6. To pause the cycle, disable the workflow in
   the Actions tab (don't delete the file).

## Division of labor (suggested, not exclusive)

- **Codex/ChatGPT:** Telegram delivery, workflow reliability, tests.
- **Copilot:** renderer/validator hardening via PRs (reviewed before merge).
- **Claude:** the AI newsroom layers (briefs, investigations desk), editorial
  pipeline, dedupe/completeness gates, the annual **TOP 100**
  (`originals/palestine-top100-<year>.*` — Times of Palestine's list of the
  100 most influential Palestinians worldwide, published each August; owner
  directive 2026-08-01; refresh the research sweep fully each edition, never
  recycle the prior year's blurbs), and the daily **Washington Brief**
  (`originals/washington-brief-*` + matching SVGs in `originals/media/`) —
  a scheduled deep-research report on DC's Iran/Israel/Mideast thinking for a
  Palestinian audience. Other agents: don't create files with that prefix or
  duplicate the DC-policy beat.

Improving each other's areas is welcome — via PR, with the existing layer kept
working.

## Yasser Abbas file (owner directive 2026-08-05)

Standing beat: track Yasser Abbas — the president's son — across every
financial and political file he enters: the mandate over PLO property sales
in Lebanon (and the Dabbour extradition case that grew from it), the West
Bank fuel sector (the al-Natsheh detention, the reported-but-unconfirmed
centralised fuel company), his Fatah Central Committee role, and any new
mandate, company or asset file that surfaces. Significant developments are
same-day coverage in both languages. Discipline is mandatory and
non-negotiable: this is professional accountability journalism, never
personal attack — every claim attributed to a named source or document,
established facts separated explicitly from reported-but-unconfirmed
accounts, denials and the family's side carried, and the absence of
oversight institutions named as the structural story. Launch report:
`originals/yasser-abbas-file-2026.*` (the two-decade record: Falcon
Holding, the USAID contracts, the 2012 congressional hearing, Abbas v.
Foreign Policy Group, the 2025-26 mandates). Related coverage:
`dabbour-arrest-yasser-abbas-2026.*`, `fatah-eighth-congress-2026.*`.
Claude's beat; other agents route developments via issue #6.

## PA litigation docket (owner directive 2026-08-02)

Standing beat: track lawsuits against the PA/PLO worldwide — the revived US
terror-judgment cases (Sokolow $655.5M, Fuld, PSJVTA suits), Israeli court
judgments enforced via clearance-revenue deductions, the prisoner-payments
audit that decides both, and any European enforcement or conditionality
proceedings. Launch report: `originals/pa-litigation-docket-2026.*`. The
daily editor cycle sweeps this docket; significant developments are covered
same-day in both languages. Claude's beat.

## Israeli election watch (owner directive 2026-08-02)

Standing beat through the 27 October 2026 Knesset election: the coalitions
forming and collapsing, who leads, who gains, who falls, and the names —
Eisenkot/Yashar, Netanyahu/Likud, Bennett–Lapid/Beyachad, Golan/Democrats,
Liberman, Gantz, Ben Gvir, Smotrich, Deri, and the Arab lists (Mansour
Abbas/Ra'am, Odeh–Tibi/Hadash-Ta'al) whose seats both blocs need and refuse.
Always frame the Palestinian stakes: annexation, Gaza policy, the kingmaker
paradox facing Palestinian citizens of Israel. Launch report:
`originals/israel-election-2026-*`. The daily editor cycle sweeps this beat;
significant poll shifts, mergers and coalition moves are covered same-day in
both languages, with numbers attributed to the specific pollster/outlet.
Claude's beat — other agents route election story ideas via issue #6.

## International justice watch (owner directive 2026-08-02)

Standing beat: the ICC and ICJ files on Palestine, with the arrest warrant
for Benjamin Netanyahu at the center. Track: the ICC warrants for Netanyahu
and Gallant (appeals, member-state compliance and travel, the US sanctions
campaign against the court's prosecutor, deputies and judges, Hungary-style
withdrawals); the ICJ's South Africa v. Israel genocide case (pleadings,
interventions, hearings), the occupation and aid advisory opinions, and
Nicaragua v. Germany. Keep the two courts distinct for readers (state
disputes at the ICJ, individual criminal liability at the ICC) and always
attribute filings and rulings to the specific chamber and date. The courts'
official channels (@CIJ_ICJ, @IntlCrimCourt) are Tier-1 watchlist accounts;
significant developments are covered same-day in both languages. Launch
report: `originals/icc-icj-netanyahu-warrant-2026.*`. Claude's beat — story
ideas from other agents route via issue #6.

## Scholarship guide (owner directive 2026-08-02)

Standing reader service: `originals/palestine-scholarships-guide-2026.*`
maps scholarship programs for Palestinian students worldwide (bachelor's
to PhD, all fields) and is pinned on the front page via the SPECIALS band.
The daily editor cycle keeps it current — new windows added, passed
deadlines retired, both languages, links verified. Deadlines are always
phrased as verify-at-source. Claude's beat; other agents may PR additions
with sources.

## SANAD — bitchat for medicine (owner north star, 2026-08-04)

The owner's guiding principle, verbatim in spirit: **SANAD is bitchat for
medicine — an app that works and runs purely for medical cases and helps
doctors and patients talk to each other worldwide to solve medical issues.
That is the problem we are in love with and the problem we want to solve.**
Every Sanad decision is measured against this sentence. War zone first:
hospitals and patients in Gaza, where internet and even phone service come
and go.

**STATUS — NOT READER-FACING (owner decision 2026-08-04 evening):** the
owner unpublished Sanad from the website pending better planning. The
`/sanad/` static-feature marker is removed (the page no longer deploys),
the front-page band/nav/specials presence and the launch report are gone,
and the fixture test asserts the absence. Development continues PRIVATELY
in-repo — `sanad/` (the board source), `sanad-app/` (the native app:
v0.1-0.3 built, mesh awaiting field test), `outbreak_watch.py` (dormant:
writes only if /sanad/ deploys) — tracked on issue #149. NO agent re-adds
any reader-facing Sanad surface until the owner green-lights redeployment.

Standing rules: trust is professional referral (owner decision 2026-08-04 —
NO licence-verification gate, ever); no names/IDs/faces ride a packet;
"not a medical service" on every screen; a missing key or feature must
never block advice — care outranks secrecy. Claude's beat; other agents
PR under charter rules, disagreements to issue #6.

## Bitchat watch (owner directive 2026-08-04)

Standing beat: cover bitchat news worldwide — releases, features, adoption,
mesh deployments in disasters and blackouts — to promote mesh communication
in Palestinian areas, where connectivity is a weapon used against the
population. Significant developments are covered same-day in both languages;
every piece carries the practical Palestinian angle (what this means when
Gaza's internet dies) and the official-download-only guidance: iPhone =
"bitchat mesh" on the App Store (id 6748219622, Permissionless Technology);
Android = the permissionlesstech GitHub releases APK; Google Play hosts
impostors — warn readers every time. The financial-freedom/ecash angle of
bitchat stays with ChatGPT's Financial Freedom section (the launch piece
`originals/bitchat.*` is that desk's layer — graft, don't rewrite).
The daily editor sweeps this beat; a researched worldwide adoption report
is queued in topics.json (`bitchat-mesh-adoption-2026`).

## HER STORY — Palestinian women's accounts (owner directive 2026-08-03)

Standing section, key `women` ("Her Story" / «حكايتها»), modelled on More
to Her Story: women and girls are the SUBJECT, not the illustration. It
covers what Palestinian women survived and what they carry — violence
against women (UN-documented sexual and gender-based violence in
detention, at checkpoints and by settlers), widowhood and female-headed
households, birth and maternal care under siege, detention of women and
girls, and the work women do to hold families and institutions together.
Wire items route in automatically (`WOMEN_RX`: a female subject plus a
her-story context, or a strong solo signal like أسيرة/femicide/midwife).

Section rules, binding on every agent:
- **Consent and safety first.** Never name a survivor of sexual violence
  without explicit consent; never publish an account in a form that could
  identify her against her wishes. An anonymous account still runs —
  silence protects only whoever caused the harm.
- **Report the issue, never the individual** (charter rule, enforced hard
  here): no spectacle, no grief as raw material. Her words lead; our
  summary follows.
- **Attribute every finding** to the specific UN body/report and date.
- Both editions always; Arabic is written fresh, never translated.
- Women journalists inside Palestine are invited to file; their bylines
  run on their own work. Launch report:
  `originals/her-story-palestinian-women-2026.*`. Claude's beat; open to
  all agents under these rules.

## Palestinians in Israel (owner directive 2026-08-21)

Standing daily section, key `pal48` ("Palestinians in Israel" /
«فلسطينيو الداخل») — the two million Palestinian citizens of Israel as a
first-class daily beat, third in the front-page section order after Gaza
and the West Bank. Covers: the crime wave and the state's non-enforcement
(numbers attributed to the Abraham Initiatives or the named outlet, with
the solve-rate gap stated), Naqab demolitions and the unrecognized
villages, speech prosecutions and workplace purges since October 7
(Adalah's documentation attributed), the Arab lists and the Follow-Up
Committee, the health-workforce file, and the community's civic and
cultural life — covered as news of the homeland, never as an "Israeli
domestic minority" story. Wire items route in automatically (`PAL48_RX`;
the arab48 feed plus `radar-pal48`/`radar-pal48-ar` pinned feeds supply
it); keeper topics in topics.json feed the desk when the wire runs
quiet; the daily editor treats a STALE line here as a same-day
assignment like every section. Discipline: attribute every count and
finding to the named institution and date; a 48-Palestinian prisoner
story keeps the prisoners file's routing, and a female subject keeps Her
Story's. Launch report: `originals/palestinians-48-file-2026.*`.
Claude's beat; other agents route story ideas via issue #6.

## Markets watch (owner directive 2026-08-11)

Standing beat: track the stock markets of both Palestine and Israel and
use them in the coverage. The Palestine Exchange (PEX, Nablus — the
Al-Quds index and the listed companies: Bank of Palestine, PADICO,
PALTEL and peers) and the Tel Aviv Stock Exchange (TA-35/TA-125, with
the shekel) ride the front page's numbers strip via the fail-open
fetchers in `gaza_panel.py` (`market_figures`, `shekel_rates`).
Coverage discipline: a significant move — an index swinging on war or
ceasefire news, a Palestinian listing's results, a TASE reaction that
prices Israeli politics — is an economy story the SAME DAY in both
languages, numbers always attributed to the exchange and dated;
market levels are facts, never advice, and no story recommends buying
or selling anything. The daily editor sweeps the beat; PEX publishes no
API, so `editorial/markets.json` carries the latest Al-Quds CLOSE with
its date as the strip's fallback — the daily editor refreshes it every
cycle from pex.ps / Investing.com PLE, and the cell renders the file's
date when live fetching fails (never a stale number undated, never a
blocked build).
Claude's beat; other agents route market story ideas via issue #6.

## Prisoners & Detainees (owner directive 2026-08-11)

Standing section, key `prisoners` ("Prisoners & Detainees" / «الأسرى») —
the أسرى file every Palestinian outlet carries as a first-class desk.
Wire items route in automatically (`PRISONERS_RX`: prisoner/detainee/
administrative detention/hunger strike, أسير/أسرى/معتقل, نادي الأسير,
هيئة شؤون الأسرى, تبادل أسرى). Covers: counts and conditions, administrative
detention, hunger strikes, releases and exchanges, the prisoners'
institutions, and the families. Discipline: numbers attributed to the
specific institution and date (نادي الأسير, هيئة شؤون الأسرى, the Prisoner
Studies centers); a female prisoner's account keeps its Her Story routing
(that section's consent-and-safety rules bind here too); report the issue,
never the individual. Open to all agents under charter rules.

## Arab support monitor (owner directive 2026-08-02)

Standing division: what Arab countries are doing to help Palestinians —
politically, economically, financially, in aid, education and culture.
Section key `arabaid` ("Arab Support" / «الإسناد العربي»), fed by dedicated
radar feeds (`radar-arab-support`, `radar-arab-support-ar`) and an
actor-plus-assistance categorization rule, so wire items land in the section
automatically. The daily editor cycle sweeps the beat: summit pledges and
whether they disburse, reconstruction financing, medical corridors and field
hospitals, scholarship programs for Gaza students, cultural initiatives —
covered in both languages with the charter's constructive-framing rule
(credit delivered work precisely; distinguish promised, funded, underway,
completed and still needed). Launch report:
`originals/arab-support-monitor-2026.*`. Open to all agents under charter
rules; keep pledges attributed and dated.

## The Palestinian Table — weekly restaurant feature (owner directive 2026-08-04)

Standing weekly franchise: every FRIDAY the daily editor cycle features one
famous Palestinian restaurant somewhere in the world — rotating US, European,
Arab and Latin American cities — from the researched queue in
`editorial/palestinian-table-queue.md` (write the next entry, move it to
Published, add a new candidate). Deep research; rights-cleared pictures
(Commons dish/venue photos with manifest entries, house recipe-card SVGs
in-body); the restaurant's story AND its most famous dishes WITH recipes —
traditional recipes written fresh as common heritage, chefs' signatures
described with attribution, never copied. Both languages, category
diaspora (or the city's fit); journalism, not advertising. Launch feature:
`originals/palestinian-table-tanoreen-2026.*`. Claude's beat; other agents
may PR candidates into the queue with sources.

## Israeli press review (owner directive 2026-08-06)

Standing daily desk: Times of Palestine reads the Hebrew and English
Israeli press (Haaretz, Yedioth/Ynet, Maariv, Israel Hayom, Times of
Israel, JPost, the think tanks) and publishes what matters to Palestinian
readers — each source article as its own bilingual original, plus a
front-pages roundup, all in the dedicated section `israelipress`
("Israeli Press" / «الصحافة الإسرائيلية», owner decision 2026-08-06). The workflow, source list, selection test and
binding rules live in `.claude/skills/israeli-press-review/SKILL.md`;
the daily editor cycle runs the sweep each morning. Opinion is always
attributed to its author; think tanks are labelled; owner-supplied
bulletins (al-Masdar) are source material whose underlying outlets are
credited — the bulletin's own translation text is never republished.
Launch batch: twelve items dated 2026-08-06. Claude's beat; other agents
route Israeli-press story ideas via issue #6.

## US press review (owner directive 2026-08-11)

Standing daily desk, sibling to the Israeli press review: Times of
Palestine reads the American papers (NYT, Washington Post, WSJ, Politico,
The Hill, Axios, Foreign Policy, The Atlantic, Foreign Affairs) and
Washington's think tanks (Brookings, Carnegie, CSIS, WINEP, Quincy, CFR,
FDD, MEI, the Arab Center DC) and publishes what matters to Palestinian
readers — each source piece as its own bilingual original, plus a
"what Washington is reading" roundup, all in the dedicated section
`uspress` ("US Press" / «الصحافة الأميركية»). The workflow, source list
(`editorial/us-press-feeds.json`), selection test and binding rules live
in `.claude/skills/us-press-review/SKILL.md`; the daily editor cycle runs
the sweep each morning beside the Israeli one. Opinion is always
attributed to its author; think tanks are labelled with their
institutional lean; the Washington Brief remains a separate synthesized
franchise, the Joe Kent watch keeps its own discipline, and
crypto/financial-freedom stays ChatGPT's. Claude's beat; other agents
route US-press story ideas via issue #6.

## Joe Kent watch (owner directive 2026-08-07)

Standing beat: track Joe Kent (@joekent16jan19) — the former National
Counterterrorism Center director who resigned in March 2026 blaming the
Iran war on "pressure from Israel and its powerful American lobby" — as an
important voice on Israel and its role in American policy. Cover his
significant statements same-day in both languages: his X posts, interviews
and campaigns (e.g. against NDAA Section 219 US-Israel military
integration). Discipline is mandatory: his statements are attributed
claims, quoted precisely, never adopted as the paper's voice; the
counter-voices (McConnell's antisemitism charge, mainstream rebuttals) are
carried beside them, and the antisemitism debate around his framing is
reported honestly. The beat's frame for Palestinian readers: how far
Washington's debate over Israel's role in US policy is opening, and what
that means for Gaza and the West Bank. Part of the DC-policy beat
(Washington Brief); Claude's beat, launch report
`originals/joe-kent-israel-debate-2026.*`. Other agents route Kent items
via issue #6.

## Amnesty rights-wire & the Qusra file (owner directive 2026-08-15)

Amnesty International is a RELIABLE SOURCE and standing wire service for this
newsroom. Its statements, findings and reports on Israel/OPT route in through
the `amnesty` / `amnesty-ar` RSS feeds (feeds.json, Palestine-filtered) and
the Tier-1 watchlist rows (@amnesty, @amnestyusa); significant items are
same-day coverage in both languages. Discipline: every finding is attributed
to the named Amnesty official with title and date; Amnesty's characterizations
(state-backed settler terror, apartheid, forcible transfer) are carried as the
organization's documented findings — quoted precisely, never adopted
unattributed as the paper's voice, and never softened either. Where Israel or
its army has answered a specific Amnesty finding, the answer is carried
beside it.

Running story: the QUSRA SIEGE file (three families besieged at Ras al-Ein
since 2026-08-09; coverage from `qusra-outpost-siege-2026-08-11.*` through
`amnesty-qusra-state-backed-siege-2026-08-15.*`) gets REGULAR UPDATES — every
significant development (siege lifted or extended, outpost cleared or rebuilt,
casualties, arrests, US/UN moves, home seizures) is same-day coverage in both
languages until the story resolves, and the daily editor checks the file's
freshness each cycle. Claude's beat; other agents route Qusra/Amnesty items
via issue #6.

## Dima Barakat release campaign (owner order 2026-08-19)

Times of Palestine campaigns for the release of Dr. Dima Muhammad Amin
Barakat — the 54-year-old Ramallah gynecological-oncology surgeon (Dunya
Specialized Center for Women's Cancer) whom Israeli forces seized from her
al-Tira home on 2026-08-18 with no charge announced. The campaign's form:
the case LEADS the front-page SPECIALS row (first card, `build.py
SPECIALS`, requires_original `dima-barakat-file-2026`) and keeps the
running-file hub `topic-dima-barakat` until she is released; every
development — hearing, detention extension, charge, statement by the army
or by the institutions demanding her freedom — is same-day coverage in
both languages. Discipline is mandatory: the campaign voice lives ONLY in
clearly-labelled campaign surfaces (the band card, the campaign SVG); the
news copy itself stays attributed wire-register journalism — witness
accounts attributed, the absence of an announced charge stated as the
central fact, any Israeli statement carried when one exists. The verified
Arabic spelling is «ديما بركات» (arabic-names.json). Related standing
context: the Mazen al-Rantisi case (same neighborhood, June arrest) rides
this file. When she is released, the pin comes down and the file closes
with a final report; NO agent removes the pin before that without the
owner's word. Claude's beat; other agents route developments via issue #6.

## Taqarob podcast wire (owner directive 2026-08-16)

The Taqarob podcast (بودكاست تقارب, host أحمد البيقاوي — Instagram
@taqarobpodcast, YouTube) is a STANDING SOURCE reported on as a wire
service: its long-form interviews with Palestinian decision-makers,
experts and witnesses regularly surface newsworthy first-person accounts
found nowhere else. Discipline, binding on every desk: a guest's claim is
an ATTRIBUTED ACCOUNT — named speaker, episode number, quoted precisely —
never the paper's voice; the documented record (court judgments, audits,
institutional filings) is checked and carried around it, and the subject
of an allegation gets their answer or documented position beside it.
Episode clips embed via the whitelisted Instagram-reel route. Launch
story: `taqarob-shuaibi-arafat-companies-2026-08-16.*` (Azmi Shuaibi on
the Arafat-era presidential companies, episode 230). The watchlist row
carries the sweep; the daily editor checks new episodes each cycle and
should wire the program's YouTube channel RSS into feeds.json once the
channel id is confirmed from CI (the feed-health net will verify it).
Claude's beat; other agents route Taqarob story ideas via issue #6.

## Breaking-news watchlist (owner directive 2026-08-01)

`editorial/x-watchlist.md` is the newsroom's tiered list of the X/Twitter
(and named Facebook/Instagram) accounts that break Palestine news first.
When the owner sends an X post link that the working sandbox cannot open
(x.com is egress-blocked there), dispatch the `x-fetch.yml` workflow with
the URL and read the post's text back from the job log (`x_fetch.py`,
owner request 2026-08-19) — never write coverage from a guessed post.
Every automated editorial run sweeps Tier 1 before other work; an uncovered
Tier-1 item from the last 24 hours is the day's first assignment. Posts are
claims, not facts — attribute, translate precisely, and say what remains
unconfirmed. Any agent may improve the list via PR.

## House design system (owner directive 2026-08-02)

`editorial/design-system.md` is the normative definition of the site's look
and layout for EVERY agent. Any reader-facing visual change follows it: use
the `:root` tokens (no new hex families without adding them to that file
first), keep RTL first-class via logical properties, follow the house SVG
style, and run its verification protocol (EN + AR, mobile, dark mode
screenshots) before the PR. A PR that introduces a new visual pattern
updates the design system in the same PR. Design disagreements go to
issue #6, never resolved by overwriting.

## Coordination & beats in motion (owner directive 2026-07-30)

- **Standing coordination thread: issue #6** — story ideas for each other,
  beat-cadence notes, cross-desk requests. The Washington Brief posts a
  daily cadence check and DC-sourced story ideas there. ChatGPT/Codex:
  keep a steady filing cadence on your beats and check #6 for ideas.
- **HEALTH beat (new):** `category: health`, section "Health & Healing" /
  «الصحة والتعافي». Owner directive: the Gaza war's damage to population
  health, covered with a solutions lens — prosthetics, cancer corridors,
  telemedicine, children's mental health, dialysis/chronic care, maternal
  care, vaccination recovery, rehabilitation. Eight topics queued in
  topics.json; Palestine Health Wire feed feeds the section. Open to all
  agents under the charter rules.

## Asking each other for help (owner directive 2026-07-30)

When an agent hits a problem it cannot solve — a bug outside its expertise,
a layer it doesn't own, a design question — it ASKS the others instead of
guessing or force-changing someone else's code:

- Open a GitHub issue titled `help: <short problem>` with the symptom, the
  exact error or repro, what was already tried, and which layer it touches.
- Mention `@copilot` to bring in Copilot (it responds to issue/PR mentions
  and can file a PR), or address Codex for its layers (Telegram delivery,
  workflow reliability, tests) — Codex reads this file and the repo issues.
- Claude runs the newsroom layers; issues touching briefs, dedupe, the
  desks or editorial gates should be labeled for Claude and left unmerged
  until reviewed.
- The owner reads the issues; disagreements between agents end there, with
  the owner deciding. Never resolve a disagreement by overwriting.
- **Codex is the standing first call (owner order 2026-08-19, binding on
  Claude and every agent):** whenever help is needed — a fix that didn't
  hold on the first try, a production failure outside the agent's own
  layer, a diagnosis the agent isn't sure of, or simply a second pair of
  eyes on a risky change — ASK CODEX rather than pushing on alone. The
  mechanics: open or reuse a `help:` issue (or post on the standing
  coordination thread #6) addressed to Codex with the symptom, repro and
  what was tried; Codex reads this file and the repo issues. Asking is
  never a failure and never optional when stuck: two failed attempts at
  the same problem means the next step is a help issue, not a third
  attempt. Urgent production breakage still gets an immediate mitigation
  first — then the ask.

## Palestine Times archive (rights on record)

The owner declared to Claude on 2026-07-30 that they FULLY OWN the rights to
the Palestine Times — the English-language Palestinian daily launched in
Ramallah on 2006-11-27 that ceased publication in 2007 (Library of Congress
item 2007330052) — including its title and archive. Times of Palestine is its
revival. Archive republication rules:
- Archive pieces use `category: archive` (section "From the Archive" /
  «من الأرشيف»), carry their ORIGINAL publication date in `date:`, a very
  large `maxAgeHours` (e.g. 999999), and never masquerade as new reporting.
- Never alter the original text beyond format cleanup; note the original
  byline inline where known ("By <name>, Palestine Times, <date>").
- Only the owner supplies archive source material (scans, PDFs, text). No
  agent scrapes third-party sites for it.

## How any agent publishes an article (the contract)

The site is fully cloud-automated: push a valid file to `originals/` on `main`
and the hourly GitHub Actions build validates, renders, deploys, and delivers
it to Telegram. No human machine involved. The contract:

1. File: `originals/<slug>.<en|ar>.txt` — publish BOTH languages as
   first-class editions. Header, then `---`, then body:
   `title:` / `category:` (one of: gaza westbank politics economy
   accountability research bitcoin diaspora arts sports social opinion news
   humans health archive arabaid women israelipress uspress prisoners pal48) / `date:` (ISO 8601 UTC, never future) /
   optional `maxAgeHours:`.
   **Headline rule (owner decision 2026-07-30, validator-enforced):** every
   title is ONE short complete sentence — aim for 9-10 words, hard cap 12,
   never a trailing ellipsis, never raw feed/post text as a title.
   **Titles carry the complete idea (owner order 2026-08-05):** a headline
   must leave no essential question hanging — "X accused Y" is not a title
   until it says accused OF WHAT; "court rules on Z" is not a title until it
   says ruled WHICH WAY. The key predicate and object belong in the title,
   in both languages ("Lebanon arrests envoy who accused Abbas's son of
   turning security on him", never "…who accused Abbas's son"). The
   briefs desk composes its own short headline for every wire story.
   **NO PASSIVE TITLES — EVER (owner decision 2026-07-30,
   validator-enforced, both languages):** every title is active voice and
   says precisely WHO did WHAT to WHOM — the actor the reporting identifies
   is the grammatical subject. Never passive ("was killed", «قُتل»,
   «استُهدف»), and never agentless hedges that hide a known actor ("changes
   hands", "comes under fire", "faces pressure"). "Israel registers West
   Bank land weekly", never "West Bank land changes hands through a weekly
   administrative routine". In Arabic: جملة فعلية بالمبني للمعلوم تسمّي
   الفاعل صراحةً. The validator skips originals and refuses briefs whose
   titles trip the passive/agentless net.
2. Body Markdown subset ONLY: `##` subheads, `**bold**`, `*italic*`,
   backtick code, `- ` bullets, `1. ` lists, pipe tables, `[text](url)`
   links, `> ` pull quotes / data callouts (consecutive `> ` lines form one
   quote; a second line renders as the smaller attribution — use for a
   survivor's words or a key statistic, sparingly, 1–2 per story),
   **Pacing (owner order 2026-08-03): paragraphs are 1–3 sentences, never
   past ~70 words — the renderer splits longer prose at sentence boundaries
   on every surface, originals included — and machine diction (the briefs
   desk's banned lists, «أسلم» for «سلّم», «قام بـ», «تم»+مصدر, "delve",
   "underscores"…) is flagged loudly at build for the daily editor.**
   `![caption](file.svg)` images (file must exist in
   `originals/media/`; a rights-cleared raster (.jpg/.png) with a
   `media-rights.json` entry is also accepted in-body). Anything else prints literally and the article is
   SKIPPED by the validator. No footnotes, no sources sections — attribution
   inline in prose. Never end mid-sentence. NEWSPAPER copy, never a briefing
   memo (owner decision 2026-07-30, validator-enforced): no "What is
   unresolved / Unanswered questions / Key takeaways / Conclusion / Bottom
   line"-style sections and never a list of questions — unknowns are
   reported as prose sentences in wire-service register. Internal editorial
   notes ("verify before publication") must never appear in a body.
3. Graphics: self-created SVGs in `originals/media/`, house dark style with
   bilingual labels (see existing `times-of-palestine-*.svg`). Never
   copyrighted images.
   **Lede visual protocol (owner decision 2026-07-30):** every original
   carries an `image:` header. Priority: (1) a rights-cleared REAL photo or
   screenshot of the subject (public domain, CC, official press kit,
   open-source assets) saved to `originals/media/` with a
   `media-rights.json` entry (asset, rightsBasis, credit, licenseUrl);
   (2) a house SVG illustration of the subject (`times-of-palestine-*.svg`,
   auto-owned, no manifest entry). An original's `image:` may also be a
   remote rights-cleared URL (e.g. a Wikimedia Commons
   `Special:FilePath/<name>?width=640` portrait) when that EXACT URL has a
   `media-rights.json` entry — it is verified live at build time, and an
   optional `imageFallback:` header (usually the report's house SVG) takes
   over if the remote image is dead, before the generic category cover.
   **Covers are photographs (owner order 2026-08-03):** a story's COVER must
   be a photo, centered and well-fitted — never a chart, timeline or
   figures board. Infographics belong IN the body (`![…](file.svg)`), where
   they are welcome. When no rights-cleared photo can be sourced, the house
   SVG stays as a stopgap and the report joins the photo-conversion queue
   that the daily editor cycle works through; franchise covers (TOP 100,
   the scholarship map) are brand art, not charts, and are exempt. An original's `image:` may also be a
   remote rights-cleared URL (e.g. a Wikimedia Commons
   `Special:FilePath/<name>?width=640` portrait) when that EXACT URL has a
   `media-rights.json` entry — it is verified live at build time, and an
   optional `imageFallback:` header (usually the report's house SVG) takes
   over if the remote image is dead, before the generic category cover. Text-only desk reports fall back to the
   branded category covers automatically — never the bare flag placeholder.
   **Visual-first (owner decision 2026-07-30): no article runs as dead
   text.** Every story ships a visual — real photo, subject illustration
   (the Bitchat-style house SVG is the model), or infographic. The
   investigations desk auto-generates a subject illustration per report;
   photoless wire items receive category covers; deep reports carry
   in-body infographics.
   **Video (embeds only, never hosted):** `!video[caption](url)` on its own
   line. Whitelisted hosts ONLY: YouTube watch/shorts/youtu.be URLs (renders
   as the privacy youtube-nocookie player), public Telegram post URLs
   (`https://t.me/<channel>/<id>`), public Instagram reels/posts
   (`https://www.instagram.com/reel/<id>/` — tracking params are stripped),
   or a direct https `.mp4`. Any other host
   falls through as literal text and the validator SKIPS the article.
   Telegram-sourced wire stories automatically embed their source post —
   don't hand-embed those.
4. Before pushing, run `python3 build.py` and confirm `✓ original:` for your
   files. Push with fetch/rebase/retry — this repo receives frequent commits.
5. Respect beats: `washington-brief-*` is Claude's; crypto/financial-freedom
   is ChatGPT's; check `topics.json` and recent originals to avoid duplicating
   the investigations desk or another agent's coverage.
