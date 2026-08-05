# X (Twitter) watchlist — breaking-news accounts

Owner directive 2026-08-01: the newsroom tracks the most important accounts on
X so breaking news reaches the site ahead of the wire cycle. Every automated
editorial run (daily editor cycle, investigations desk research) starts with a
sweep of Tier 1, via live web search (`"<handle>" site:x.com`, news search for
the account's latest posts, or a mirror). A Tier-1 item from the last 24 hours
that the site has not covered outranks all other editorial work that day.

Rules of use:
- X posts are CLAIMS, not facts. Attribute ("…said in a post on X"), quote
  precisely, translate faithfully, and state when no independent confirmation
  exists — exactly the wire-attribution and precision rules of the charter.
- Embeds: X embeds are not whitelisted in article bodies. Quote the text
  inline; screenshots only as rights-cleared media with a manifest entry.
- This is a living document. Any agent may add or correct handles via PR;
  verify a handle before adding it. Remove accounts that go dormant.
- Some principals break news on other platforms (Mohammad Dahlan posts on
  Facebook; several Gaza journalists are primarily on Instagram). The sweep
  covers those named accounts on their home platform too.

## Tier 1 — principals and official channels (sweep every run)

| Account | Who | Why it breaks news |
| --- | --- | --- |
| @jaredkushner | Jared Kushner | US side of the Gaza framework; deal announcements |
| @IsraeliPM | Israeli PM's office | Official Israeli positions, operations |
| @AvichayAdraee | IDF Arabic spokesman | Strike and evacuation announcements affecting Gaza |
| @StateDept | US State Department | US policy moves, envoy readouts |
| @ochaopt | UN OCHA oPt | Casualty, aid and displacement data |
| @UNRWA | UNRWA | Aid corridors, shelters, famine indicators |
| @WAFANewsEnglish | WAFA (official PA agency) | PA statements and presidency readouts |
| @Palestine_UN | Palestine's UN mission | Riyad Mansour, Security Council moves |
| @CIJ_ICJ | International Court of Justice (official) | Owner-flagged 2026-08-02: orders, hearings and advisory-opinion steps in South Africa v. Israel and the occupation dockets — sweep every run |
| @IntlCrimCourt | International Criminal Court (official) | Owner-flagged 2026-08-02: every move on the Netanyahu/Gallant arrest warrants — appeals, state compliance, sanctions on the court — is same-day coverage |
| @hzomlot | Husam Zomlot | London embassy; recognition diplomacy |
| @BarakRavid | Barak Ravid, Axios | Owner-flagged 2026-08-05: very important source — his Axios reporting breaks US–Israel–Iran diplomacy (Hormuz talks, ceasefire mechanics, White House readouts) hours ahead of the wires. Sweep every run; significant reports are same-day coverage in both languages, always crediting him and Axios by name for the reporting. |
| Mohammad Dahlan — Facebook (verified page) | Exiled Fatah leader | Kushner channel; Gaza governance file |

## Tier 2 — journalists and witnesses on the ground

| Account | Who |
| --- | --- |
| @WaelDahdouh | Wael al-Dahdouh, Al Jazeera Gaza |
| @Hind_Gaza | Hind Khoudary, reporting from Gaza |
| @wizard_bisan1 | Bisan Owda, Emmy-winning filmmaker |
| @muhammadshehad2 | Muhammad Shehada, analyst-journalist |
| @m7mdkurd | Mohammed El-Kurd, writer |
| Motaz Azaiza — Instagram (@motaz_azaiza) | Photojournalist |
| Plestia Alaqad — Instagram (@byplestia) | Journalist-author |
| @amit_segal | Amit Segal, Channel 12 — first on Israeli coalition/poll moves (election watch; treat as claims, attribute) |
| Hani Almadhoun — LinkedIn (@hanifundraiser) | UNRWA USA vice president of philanthropy; co-founded Gaza Soup Kitchen with his brother Mahmoud (killed by an Israeli drone strike, Nov 2024). First-hand family reporting from Beit Lahia + DC aid-world signal, including Dahlan-orbit aid activity. Owner-flagged 2026-08-02: his stories and posts are important — sweep his feed for story leads. |

## Tier 3 — outlets, analysts and the diaspora public square

| Account | Who |
| --- | --- |
| @AJEnglish / @AJArabic | Al Jazeera |
| @MiddleEastEye | Middle East Eye |
| @972mag | +972 Magazine |
| @QudsNen | Quds News Network |
| @PalestineChron | Palestine Chronicle |
| @RepRashida | Rep. Rashida Tlaib |
| @YousefMunayyer | Yousef Munayyer |
| @4noura | Noura Erakat |
| Rashid Khalidi — رشيد خالدي (no active personal X; track via interviews, lectures and shared video clips) | Historian, Columbia's Edward Said Professor Emeritus; author of "The Hundred Years' War on Palestine"; TOP 100 honoree. Owner-flagged 2026-08-02: important name — sweep for his new interviews, lectures and essays; his interventions are coverage, not just commentary. |
| @JohnKiriakou (verify handle before each citation; track primarily via his shows and interviews) | John Kiriakou, ex-CIA officer and torture whistleblower. Owner-flagged 2026-08-04: pay close attention — sweep his interviews (The Tucker Carlson Show, Rogan, Judging Freedom circuit) and his own programs (DEEP FOCUS, DeProgram with Ted Rall) plus columns for Israel/Palestine material; his Iran-intel, Israel-lobby and Gaza Tribunal threads feed the accountability file. Launch profile: `originals/john-kiriakou-palestine-2026.*`. |
| @KenRoth | Kenneth Roth, Human Rights Watch executive director 1993–2022, now Princeton visiting professor. Owner-flagged 2026-08-05: pay attention to everything he says on Israel and Palestine — his X feed runs daily legal-accountability commentary (apartheid findings, the ICC file, Gaza starvation, settlement expansion) with three decades of institutional authority behind it. Significant posts are same-day coverage in both languages; quote precisely per the claims-not-facts rule and identify him by his HRW tenure on first reference. |

## What "ahead of the curve" means operationally

1. Tier-1 sweep at the start of every automated editorial run, and whenever
   the owner flags an item, treat it as the day's first assignment.
2. A breaking post becomes a story the way the Dahlan Sunday-halt report did:
   precise translation, exact attribution, verified context from live
   research, an honest line on what remains unconfirmed, bilingual editions,
   house visual — validated and published the same hour.
3. Real-time (minute-level) X ingestion needs paid X API credentials; if the
   owner supplies them, build a `feeds.json`-style ingest as a new layer. Until
   then the cadence is: twice-hourly wire builds + daily sweep + owner flags.
