// Browser sweep for originals/media/*.svg text that leaves the canvas.
//
// Why this exists: build.svg_text_overflows estimates glyph widths and is
// blind to RTL geometry (issue #260). An Arabic run can sit entirely inside
// the estimator's budget and still render off the canvas, because in SVG the
// side of `x` that RTL text occupies is decided by text-anchor:
//
//   direction="rtl", no anchor / anchor="start"  -> RIGHT edge sits at x,
//                                                   text flows LEFT
//   direction="rtl", anchor="end"                -> LEFT edge sits at x,
//                                                   text flows RIGHT
//
// So an Arabic label meant to be right-aligned at the right side of the
// canvas must NOT carry text-anchor="end" (it would flow off the right
// edge), and an Arabic label meant to sit left-aligned under an English
// title at the same small x MUST carry it (or it flows off the left edge).
// Getting that backwards is invisible to the estimator and to a reader of
// the source; only a real layout engine shows it.
//
// Usage (weekly maintenance cycle):
//   npx playwright install --with-deps chromium
//   npm install --no-save playwright-core
//   CHROME_EXE=$(echo ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome) \
//     node tools/svg_rtl_sweep.mjs
//
// Install the system Arabic fonts first (fonts-noto-core) — without them
// glyph metrics come from a fallback face and the reported overflow
// magnitudes are meaningless. The SIDE of the overflow is font-independent.
//
// Exit code 1 when any text node leaves the viewBox, so it can gate a run.
//
// --collisions additionally reports text-on-text overlap. Treat that output
// as ADVISORY only: bilingual English/Arabic label pairs are deliberately
// stacked all over the house style, and their line boxes overlap without the
// glyphs colliding, so most hits are false positives. It is useful for
// finding the on-canvas half of the anchor bug (a label spilling out of its
// own card into the next one), which the viewBox check cannot see.

import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';

const DIR = 'originals/media';
const TOL = 2;               // user units; below this is antialiasing noise
const WANT_COLLISIONS = process.argv.includes('--collisions');

const files = fs.readdirSync(DIR).filter((f) => f.endsWith('.svg')).sort();
const browser = await chromium.launch({ executablePath: process.env.CHROME_EXE });
const page = await browser.newPage();

const overflows = [];
const collisions = [];

for (const file of files) {
  try {
    await page.goto('file://' + path.resolve(DIR, file), { waitUntil: 'load', timeout: 20000 });
  } catch (err) {
    console.log(`LOADFAIL ${file}: ${err.message}`);
    continue;
  }

  const res = await page.evaluate(({ tol, wantCollisions }) => {
    const svg = document.querySelector('svg');
    if (!svg) return { err: 'no svg root' };
    const vb = svg.viewBox && svg.viewBox.baseVal;
    if (!vb || (!vb.width && !vb.height)) return { err: 'no viewBox' };

    const box = svg.getBoundingClientRect();
    const sx = box.width / vb.width;
    const sy = box.height / vb.height;
    const toUserX = (px) => (px - box.left) / sx + vb.x;
    const toUserY = (px) => (px - box.top) / sy + vb.y;

    const attr = (node, name) =>
      node.getAttribute(name) ||
      (node.parentElement && node.parentElement.getAttribute(name)) ||
      '';

    const nodes = [];
    for (const t of svg.querySelectorAll('text, tspan')) {
      const text = (t.textContent || '').trim();
      if (!text) continue;
      const tag = t.tagName.toLowerCase();
      // measure the innermost run only, so a <text> wrapping <tspan>s and
      // its own children are not both counted
      if (tag === 'tspan' && t.parentElement.tagName.toLowerCase() === 'tspan') continue;
      if (tag === 'text' && t.querySelector('tspan')) continue;
      const r = t.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      nodes.push({
        text: text.slice(0, 60),
        rect: r,
        left: toUserX(r.left), right: toUserX(r.right),
        top: toUserY(r.top), bottom: toUserY(r.bottom),
        rtl: attr(t, 'direction') === 'rtl',
        anchor: attr(t, 'text-anchor'),
        x: attr(t, 'x'),
      });
    }

    const over = [];
    for (const n of nodes) {
      const sides = [];
      if (n.left < vb.x - tol) sides.push(`left ${(vb.x - n.left).toFixed(1)}`);
      if (n.right > vb.x + vb.width + tol) sides.push(`right ${(n.right - vb.x - vb.width).toFixed(1)}`);
      if (n.top < vb.y - tol) sides.push(`top ${(vb.y - n.top).toFixed(1)}`);
      if (n.bottom > vb.y + vb.height + tol) sides.push(`bottom ${(n.bottom - vb.y - vb.height).toFixed(1)}`);
      if (sides.length) {
        over.push({ text: n.text, over: sides, anchor: n.anchor, rtl: n.rtl, x: n.x });
      }
    }

    const hits = [];
    if (wantCollisions) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const ox = Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left);
          const oy = Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top);
          if (ox <= 1 || oy <= 1) continue;
          const smaller = Math.min(a.rect.width * a.rect.height, b.rect.width * b.rect.height);
          const pct = (100 * ox * oy) / smaller;
          if (pct < 15) continue;
          hits.push({
            a: a.text, b: b.text, pct: Math.round(pct),
            rtlEnd: [a, b].filter((n) => n.rtl && n.anchor === 'end').length,
          });
        }
      }
    }

    return { vb: [vb.x, vb.y, vb.width, vb.height], over, hits };
  }, { tol: TOL, wantCollisions: WANT_COLLISIONS });

  if (res.err) {
    console.log(`SKIP ${file}: ${res.err}`);
    continue;
  }
  if (res.over.length) overflows.push({ file, vb: res.vb, nodes: res.over });
  if (res.hits && res.hits.length) collisions.push({ file, pairs: res.hits });
}

await browser.close();

console.log(`=== ${files.length} SVG files scanned — ${overflows.length} with text off the canvas ===`);
for (const f of overflows) {
  console.log(`\n${f.file}  viewBox=${f.vb.join(' ')}`);
  for (const n of f.nodes) {
    console.log(`   [${n.over.join(', ')}] anchor=${n.anchor || '-'} rtl=${n.rtl} x=${n.x || '-'}`);
    console.log(`      ${n.text}`);
  }
}

if (WANT_COLLISIONS) {
  const rtlEnd = collisions.flatMap((f) => f.pairs.filter((p) => p.rtlEnd).map((p) => ({ file: f.file, p })));
  console.log(`\n=== ADVISORY: ${collisions.length} files with text-on-text overlap; ` +
              `${rtlEnd.length} pair(s) involve an rtl+anchor=end node ===`);
  console.log('Bilingual stacked labels overlap by line box without colliding glyphs — verify each hit');
  console.log('against a screenshot before changing anything.');
  for (const { file, p } of rtlEnd) {
    console.log(`\n${file}  ${p.pct}% overlap\n   A: ${p.a}\n   B: ${p.b}`);
  }
}

process.exit(overflows.length ? 1 : 0);
