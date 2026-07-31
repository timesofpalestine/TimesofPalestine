# The Widow and the Ledger — publication package

Bilingual investigative feature for **timesofpalestine.com**, English and Arabic, with five original infographics.

**I could not publish this.** I have no credentials for your site and no GitHub connector is available in this environment. Everything below is ready to commit; a human has to do the commit.

---

## Contents

```
site/
  index-en.html      English edition, complete standalone page
  index-ar.html      Arabic edition, RTL, complete standalone page
  style.css          shared stylesheet, both directions
figures/
  fig1-ledger-of-figures-en.svg      English SVGs for social cards / print
  fig2-claim-vs-record-en.svg
  fig3-market-for-a-story-en.svg
  fig4-the-asymmetry-en.svg
  fig5-anatomy-of-a-claim-en.svg
article-en.md        CMS-ready markdown, [[FIG1]]–[[FIG5]] markers
article-ar.md        CMS-ready markdown, same markers, same structure
build.py             regenerates both HTML pages from the markdown
make_figures.py      regenerates the SVGs
PHOTO-LICENSING.md   which photographs to licence, from whom, and why
```

## Deploying to GitHub Pages

```bash
git checkout -b widow-and-the-ledger
mkdir -p suha-arafat
cp -r site/* suha-arafat/
cp -r figures suha-arafat/
git add suha-arafat && git commit -m "Feature: The Widow and the Ledger (EN/AR)"
git push -u origin widow-and-the-ledger
```

Live at `/suha-arafat/index-en.html` and `/suha-arafat/index-ar.html`. The two editions cross-link via the toggle in the masthead. Nothing else is required — no build step, no JS, no dependencies beyond the Google Fonts link.

**If your site uses a CMS instead**, paste `article-en.md` / `article-ar.md` and replace each `[[FIGn]]` marker with the corresponding SVG or with the HTML block from the built pages.

## Regenerating

```bash
pip install markdown cairosvg --break-system-packages
python3 make_figures.py     # → figures/*.svg
python3 build.py            # → site/*.html
```

Edit the markdown, not the HTML. Figure content lives in the `FIGS` dict in `build.py`; keep the English and Arabic entries in sync.

## Design notes

The visual system is an **audit ledger**, taken from the subject matter: pale columnar-pad green, ink, and a two-colour status system that carries the whole argument —

- **slate blue = documented**, on the record, attributable
- **audit red = asserted, no source produced**

Every figure puts the attribution in its own column. That column is the thesis: five of the six monthly figures ever attached to Suha Arafat have nothing in it.

Typography is IBM Plex throughout — Serif and Mono for English, Sans Arabic for Arabic — so both editions share one type system rather than looking like a translation bolted onto a design.

**The figures are HTML/CSS, not images.** This was a deliberate reversal: I built them as SVG first, and Arabic text in SVG breaks — glyphs render unshaped and unordered in several renderers and in server-side rasterisation. As HTML the Arabic shapes correctly everywhere, the text is selectable, indexable and screen-reader accessible, and the layouts reflow on a phone. The SVGs survive as English-only social/print assets.

Checked: 390px to 1180px, both directions, no horizontal overflow; print stylesheet keeps figures off page breaks; reduced-motion respected.

## Before you publish

1. **Right of reply.** The closing note in both editions commits to carrying a response unedited. Send the draft to Suha Arafat, and separately to the PLO/PA on the stipend question, before publication. A week's delay makes the piece close to unattackable.
2. **Photographs.** See `PHOTO-LICENSING.md`. Do not run unlicensed wire images in a piece about evidentiary standards.
3. **Legal read.** The article names a sovereign state's official account as the source of a false claim about a private individual. That is accurate and defensible, but have counsel confirm the standard in your publishing jurisdiction — and keep the archived post.
4. **Archive your sources.** Capture the January 2025 post and the agency captions to a web archive now, and keep the links. If the post is deleted after you publish, you need the record.
5. **One open gap.** The formal disposition of the 2003 French money-laundering inquiry could not be established. The article states this precisely and treats the silence as part of the story. If anyone on staff can query the Paris *parquet* directly, a documented `classé sans suite` is the single most valuable addition to this piece.

## Unverified claims deliberately not asserted

The rented flat, the ordinary job, the absence of visible wealth are attributed as description, followed by an explicit statement that the publication has not verified them and does not need to — because the burden sits with whoever published the $8bn figure. Do not upgrade these to flat assertions without a named source or a document. Section VII is written to be strongest exactly as it stands.
