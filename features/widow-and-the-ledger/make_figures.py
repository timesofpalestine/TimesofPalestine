#!/usr/bin/env python3
"""
Generates the five infographics for "The Widow and the Ledger", in English and Arabic.

Design system — "audit ledger":
  paper   pale accountant's columnar green
  ink     near-black green
  slate   DOCUMENTED / on the record
  red     ASSERTED / no source produced
Figures are the argument, not decoration: every number carries its attribution.
"""
import html, os

W = 1000
PAPER = "#F4F6F0"
RULE = "#C9D3C2"
RULE2 = "#DFE6DA"
INK = "#14201B"
INK2 = "#55655C"
RED = "#A6291F"
RED_BG = "#F0DCD9"
SLATE = "#1D3A57"
SLATE_BG = "#D8E1EA"

SERIF = "'IBM Plex Serif', Georgia, 'Times New Roman', serif"
MONO = "'IBM Plex Mono', 'SF Mono', Consolas, 'Courier New', monospace"
ARAB = "'IBM Plex Sans Arabic', 'Noto Sans Arabic', 'Segoe UI', Tahoma, sans-serif"

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")


class Fig:
    def __init__(self, lang, h):
        self.lang = lang
        self.rtl = (lang == "ar")
        self.h = h
        self.p = []
        self.body = ARAB if self.rtl else SERIF
        self.mono = ARAB if self.rtl else MONO

    def x(self, v):
        """Mirror the horizontal axis for the Arabic edition."""
        return W - v if self.rtl else v

    def anchor(self, a):
        if not self.rtl:
            return a
        return {"start": "end", "end": "start", "middle": "middle"}[a]

    def t(self, x, y, s, size=15, fill=INK, weight="400", family=None,
          anchor="start", spacing=None, opacity=None, style=None):
        fam = family or self.body
        a = ['x="%s"' % self.x(x), 'y="%s"' % y,
             'font-family="%s"' % fam, 'font-size="%s"' % size,
             'fill="%s"' % fill, 'font-weight="%s"' % weight,
             'text-anchor="%s"' % self.anchor(anchor)]
        if spacing:
            a.append('letter-spacing="%s"' % spacing)
        if opacity:
            a.append('opacity="%s"' % opacity)
        if style:
            a.append('font-style="%s"' % style)
        if self.rtl:
            a.append('direction="rtl"')
        self.p.append("<text %s>%s</text>" % (" ".join(a), html.escape(s)))

    def line(self, x1, y1, x2, y2, stroke=RULE, w=1, dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        self.p.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                      'stroke-width="%s"%s/>' % (self.x(x1), y1, self.x(x2), y2, stroke, w, d))

    def rect(self, x, y, w, h, fill, rx=0, stroke=None, sw=1, opacity=None):
        xx = self.x(x + w) if self.rtl else x
        a = ['x="%s"' % xx, 'y="%s"' % y, 'width="%s"' % w, 'height="%s"' % h,
             'fill="%s"' % fill, 'rx="%s"' % rx]
        if stroke:
            a.append('stroke="%s"' % stroke)
            a.append('stroke-width="%s"' % sw)
        if opacity:
            a.append('opacity="%s"' % opacity)
        self.p.append("<rect %s/>" % " ".join(a))

    def tag(self, x, y, label, kind):
        """Small status chip: 'doc' = documented, 'no' = no source produced."""
        fill, bg = (SLATE, SLATE_BG) if kind == "doc" else (RED, RED_BG)
        w = 8.2 * len(label) + 20
        self.rect(x, y - 13, w, 20, bg, rx=2)
        self.t(x + 10, y + 1.5, label, size=11, fill=fill, weight="600",
               family=self.mono, spacing="0.06em")
        return w

    def header(self, eyebrow, title, sub):
        self.rect(0, 0, W, self.h, PAPER)
        self.line(0, 0, W, 0, INK, 6)
        self.t(48, 52, eyebrow, size=11.5, fill=RED, weight="600",
               family=self.mono, spacing="0.16em")
        self.t(48, 88, title, size=27, fill=INK, weight="600")
        self.t(48, 114, sub, size=13.5, fill=INK2)
        self.line(48, 134, W - 48, 134, RULE, 1)

    def footer(self, note):
        self.line(48, self.h - 46, W - 48, self.h - 46, RULE, 1)
        self.t(48, self.h - 26, note, size=11, fill=INK2, family=self.mono)
        self.t(W - 48, self.h - 26, "TIMES OF PALESTINE", size=11, fill=INK2,
               family=self.mono, anchor="end", spacing="0.14em")

    def save(self, name):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
               'width="%d" height="%d" font-kerning="normal">\n%s\n</svg>\n'
               % (W, self.h, W, self.h, "\n".join(self.p)))
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, "%s-%s.svg" % (name, self.lang))
        open(path, "w", encoding="utf-8").write(svg)
        print("wrote", path)


# ---------------------------------------------------------------- FIGURE 1
def fig1(lang):
    T = {
        "en": dict(
            eyebrow="FIGURE 1 · THE LEDGER OF FIGURES",
            title="What Suha Arafat was said to receive",
            sub="Alleged monthly payments in circulation, 2003\u20132020. Same person. Same period. Same currency.",
            col1="ALLEGED PER MONTH", col2="WHO SAID IT", col3="EVIDENCE PRODUCED",
            no="NO SOURCE PRODUCED", yes="NAMED, ON THE RECORD",
            rows=[
                ("$200,000", 200, "US newsmagazine, Nov 2004 \u2014 \u201Cpeople familiar with Arafat\u2019s finances\u201D", "no"),
                ("$100,000", 100, "US network television, Nov 2003 \u2014 Israeli officials; later an unnamed PA official", "no"),
                ("$50,000", 50, "Arabic press, 2011 \u2014 unattributed; she denied it specifically", "no"),
                ("$12,000", 12, "Suha Arafat, Asharq Al-Awsat, 2011 \u2014 plus rent, described as the PLO pension", "yes"),
                ("\u20AC10,000", 12, "Suha Arafat, Israeli broadcaster Kan, 2020 \u2014 same account, nine years later", "yes"),
            ],
            spread="A SIXTEEN-FOLD SPREAD. THEY CANNOT ALL BE TRUE.",
            aside="Separately, a figure of $22 million per year \u2014 a supposed settlement paid from secret accounts \u2014 has circulated since 2004, "
                  "attributed to unnamed Palestinian officials. The agreement has never been produced.",
            foot="Compiled from contemporaneous wire and broadcast reporting, 2003\u20132020.",
        ),
        "ar": dict(
            eyebrow="\u0627\u0644\u0634\u0643\u0644 \u0661 \u00B7 \u062F\u0641\u062A\u0631 \u0627\u0644\u0623\u0631\u0642\u0627\u0645",
            title="\u0645\u0627 \u0642\u064A\u0644 \u0625\u0646\u0651 \u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A \u062A\u062A\u0642\u0627\u0636\u0627\u0647",
            sub="\u0645\u0628\u0627\u0644\u063A \u0634\u0647\u0631\u064A\u0629 \u0645\u0632\u0639\u0648\u0645\u0629 \u062A\u062F\u0627\u0648\u0644\u062A\u0647\u0627 \u0627\u0644\u0635\u062D\u0627\u0641\u0629 \u0628\u064A\u0646 \u0662\u0660\u0660\u0663 \u0648\u0662\u0660\u0662\u0660. \u0627\u0644\u0634\u062E\u0635 \u0646\u0641\u0633\u0647\u060C \u0648\u0627\u0644\u0641\u062A\u0631\u0629 \u0646\u0641\u0633\u0647\u0627\u060C \u0648\u0627\u0644\u0639\u0645\u0644\u0629 \u0646\u0641\u0633\u0647\u0627.",
            col1="\u0627\u0644\u0645\u0628\u0644\u063A \u0627\u0644\u0645\u0632\u0639\u0648\u0645 \u0634\u0647\u0631\u064A\u0627\u064B",
            col2="\u0645\u0646 \u0642\u0627\u0644\u0647", col3="\u0627\u0644\u062F\u0644\u064A\u0644 \u0627\u0644\u0645\u0642\u062F\u0651\u064E\u0645",
            no="\u0644\u0627 \u0645\u0635\u062F\u0631 \u0645\u0639\u0644\u0646",
            yes="\u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649 \u0648\u0645\u0648\u062B\u0651\u064E\u0642",
            rows=[
                ("\u0662\u0660\u0660 \u0623\u0644\u0641 $", 200, "\u0645\u062C\u0644\u0629 \u0623\u0645\u064A\u0631\u0643\u064A\u0629\u060C \u062A\u0634\u0631\u064A\u0646 \u0627\u0644\u062B\u0627\u0646\u064A \u0662\u0660\u0660\u0664 \u2014 \u00AB\u0645\u0637\u0644\u0639\u0648\u0646 \u0639\u0644\u0649 \u0645\u0627\u0644\u064A\u0629 \u0639\u0631\u0641\u0627\u062A\u00BB", "no"),
                ("\u0661\u0660\u0660 \u0623\u0644\u0641 $", 100, "\u062A\u0644\u0641\u0632\u064A\u0648\u0646 \u0623\u0645\u064A\u0631\u0643\u064A\u060C \u0662\u0660\u0660\u0663 \u2014 \u0645\u0633\u0624\u0648\u0644\u0648\u0646 \u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0648\u0646\u060C \u062B\u0645\u0651 \u0645\u0633\u0624\u0648\u0644 \u0641\u0644\u0633\u0637\u064A\u0646\u064A \u0644\u0645 \u064A\u064F\u0633\u0645\u0651", "no"),
                ("\u0665\u0660 \u0623\u0644\u0641 $", 50, "\u0635\u062D\u0627\u0641\u0629 \u0639\u0631\u0628\u064A\u0629\u060C \u0662\u0660\u0661\u0661 \u2014 \u062F\u0648\u0646 \u0625\u0633\u0646\u0627\u062F\u061B \u0648\u0642\u062F \u0646\u0641\u062A\u0647 \u062A\u062D\u062F\u064A\u062F\u0627\u064B", "no"),
                ("\u0661\u0662 \u0623\u0644\u0641 $", 12, "\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A\u060C \u0627\u0644\u0634\u0631\u0642 \u0627\u0644\u0623\u0648\u0633\u0637 \u0662\u0660\u0661\u0661 \u2014 \u0648\u0635\u0641\u062A\u0647 \u0628\u0645\u0639\u0627\u0634 \u0645\u0646\u0638\u0645\u0629 \u0627\u0644\u062A\u062D\u0631\u064A\u0631\u060C \u0632\u0627\u0626\u062F \u0627\u0644\u0625\u064A\u062C\u0627\u0631", "yes"),
                ("\u0661\u0660 \u0622\u0644\u0627\u0641 \u20AC", 12, "\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A\u060C \u0642\u0646\u0627\u0629 \u0643\u0627\u0646 \u0627\u0644\u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0629 \u0662\u0660\u0662\u0660 \u2014 \u0627\u0644\u0631\u0648\u0627\u064A\u0629 \u0646\u0641\u0633\u0647\u0627 \u0628\u0639\u062F \u062A\u0633\u0639 \u0633\u0646\u0648\u0627\u062A", "yes"),
            ],
            spread="\u0641\u0627\u0631\u0642 \u0633\u062A\u0629 \u0639\u0634\u0631 \u0636\u0639\u0641\u0627\u064B. \u0645\u0646 \u0627\u0644\u0645\u0633\u062A\u062D\u064A\u0644 \u0623\u0646 \u062A\u0643\u0648\u0646 \u0643\u0644\u0651\u0647\u0627 \u0635\u062D\u064A\u062D\u0629.",
            aside="\u0648\u0645\u0646\u0641\u0635\u0644\u0627\u064B\u060C \u064A\u062A\u062F\u0627\u0648\u0644 \u0645\u0646\u0630 \u0662\u0660\u0660\u0664 \u0631\u0642\u0645 \u0662\u0662 \u0645\u0644\u064A\u0648\u0646 \u062F\u0648\u0644\u0627\u0631 \u0633\u0646\u0648\u064A\u0627\u064B \u2014 \u062A\u0633\u0648\u064A\u0629 \u0645\u0632\u0639\u0648\u0645\u0629 \u062A\u064F\u062F\u0641\u0639 \u0645\u0646 \u062D\u0633\u0627\u0628\u0627\u062A \u0633\u0631\u064A\u0629 \u2014 \u0645\u0646\u0633\u0648\u0628\u0627\u064B \u0625\u0644\u0649 \u0645\u0633\u0624\u0648\u0644\u064A\u0646 \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u064A\u0646 \u0644\u0645 \u064A\u064F\u0633\u0645\u0651\u0648\u0627. \u0648\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u0646\u0635\u0651 \u0627\u0644\u0627\u062A\u0641\u0627\u0642 \u0642\u0637\u0651.",
            foot="\u062C\u064F\u0645\u0639\u062A \u0645\u0646 \u062A\u0642\u0627\u0631\u064A\u0631 \u0627\u0644\u0648\u0643\u0627\u0644\u0627\u062A \u0648\u0627\u0644\u0628\u062B \u0627\u0644\u0645\u0639\u0627\u0635\u0631\u0629\u060C \u0662\u0660\u0660\u0663\u2013\u0662\u0660\u0662\u0660.",
        ),
    }[lang]

    f = Fig(lang, 660)
    f.header(T["eyebrow"], T["title"], T["sub"])

    f.t(48, 164, T["col1"], size=10.5, fill=INK2, family=f.mono, spacing="0.12em")
    f.t(360, 164, T["col2"], size=10.5, fill=INK2, family=f.mono, spacing="0.12em")
    f.t(W - 48, 164, T["col3"], size=10.5, fill=INK2, family=f.mono, spacing="0.12em", anchor="end")

    y = 196
    scale = 1.28  # px per $1k
    for amount, val, who, kind in T["rows"]:
        bar = val * scale
        col = RED if kind == "no" else SLATE
        f.rect(48, y - 14, bar, 22, col, opacity="0.16")
        f.line(48, y - 14, 48, y + 8, col, 3)
        f.t(54, y + 2.5, amount, size=17, fill=INK, weight="600", family=f.mono)
        f.t(360, y + 2.5, who, size=12.5, fill=INK2)
        f.tag(W - 48 - (150 if kind == "no" else 168), y + 2.5,
              T["no"] if kind == "no" else T["yes"], "no" if kind == "no" else "doc")
        y += 62

    y += 4
    f.line(48, y, W - 48, y, INK, 2)
    f.t(48, y + 30, T["spread"], size=15, fill=RED, weight="600", family=f.mono, spacing="0.04em")

    f.rect(48, y + 52, W - 96, 66, "#FFFFFF", rx=2, stroke=RULE)
    f.line(48, y + 52, 48, y + 118, INK2, 3)
    for i, ln in enumerate(_wrap(T["aside"], 108 if lang == "en" else 92)):
        f.t(66, y + 76 + i * 19, ln, size=12.5, fill=INK2)

    f.footer(T["foot"])
    f.save("fig1-ledger-of-figures")


# ---------------------------------------------------------------- FIGURE 2
def fig2(lang):
    T = {
        "en": dict(
            eyebrow="FIGURE 2 · CLAIM VS. RECORD",
            title="What was announced, and what was ever established",
            sub="Six claims that shaped the public memory of the Arafat family finances.",
            colA="AS IT CIRCULATED", colB="WHAT THE RECORD SHOWS",
            rows=[
                ("Suha Arafat was investigated for money laundering in France",
                 "Preliminary inquiry opened Oct 2003. French officials stated the illicit-origin threshold was not met. No formal investigation, no charge, no public disposition, ever.", "no"),
                ("She lived on an entire floor of a five-star Paris hotel",
                 "The hotel said she had never stayed there. The denial was published. The claim continued to circulate unchanged.", "no"),
                ("She received $100,000 a month from Palestinian funds",
                 "No bank record, transfer instruction, budget line or named source has been produced in twenty-two years.", "no"),
                ("Zahwa Arafat is worth $8 billion and owns London property",
                 "No filing, registry entry, audit or court record exists. The same post places her in Paris; she has lived in Malta since childhood.", "no"),
                ("She was subject to a Tunisian arrest warrant",
                 "Correct. Issued Oct 2011 over a private school venture with the Ben Ali family's circle \u2014 a Tunisian commercial matter, not Palestinian public money.", "doc"),
                ("$900 million of Palestinian revenue was diverted, 1995\u20132000",
                 "Correct, per the IMF. Into an account controlled by Yasser Arafat. Most of the traced portion was recovered under Salam Fayyad's reforms.", "doc"),
            ],
            k1="UNEVIDENCED OR CONTRADICTED", k2="DOCUMENTED",
            foot="Sources: Paris prosecutor statements 2003\u201304; IMF, Sept 2003; Tunisian Justice Ministry, Oct 2011; wire reporting.",
        ),
        "ar": dict(
            eyebrow="\u0627\u0644\u0634\u0643\u0644 \u0662 \u00B7 \u0627\u0644\u0627\u062F\u0651\u0639\u0627\u0621 \u0641\u064A \u0645\u0648\u0627\u062C\u0647\u0629 \u0627\u0644\u0633\u062C\u0644",
            title="\u0645\u0627 \u0623\u064F\u0639\u0644\u0646\u060C \u0648\u0645\u0627 \u062B\u064E\u0628\u064E\u062A \u0641\u0639\u0644\u0627\u064B",
            sub="\u0633\u062A\u0629 \u0627\u062F\u0651\u0639\u0627\u0621\u0627\u062A \u0635\u0627\u063A\u062A \u0627\u0644\u0630\u0627\u0643\u0631\u0629 \u0627\u0644\u0639\u0627\u0645\u0629 \u0639\u0646 \u0645\u0627\u0644\u064A\u0629 \u0639\u0627\u0626\u0644\u0629 \u0639\u0631\u0641\u0627\u062A.",
            colA="\u0643\u0645\u0627 \u062A\u064E\u062F\u0627\u0648\u064E\u0644", colB="\u0645\u0627 \u064A\u064F\u0638\u0647\u0631\u0647 \u0627\u0644\u0633\u062C\u0644",
            rows=[
                ("\u062E\u0636\u0639\u062A \u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A \u0644\u062A\u062D\u0642\u064A\u0642 \u0641\u064A \u063A\u0633\u064A\u0644 \u0627\u0644\u0623\u0645\u0648\u0627\u0644 \u0641\u064A \u0641\u0631\u0646\u0633\u0627",
                 "\u062A\u062D\u0642\u064A\u0642 \u0623\u0648\u0651\u0644\u064A \u0641\u064F\u062A\u062D \u0641\u064A \u062A\u0634\u0631\u064A\u0646 \u0627\u0644\u0623\u0648\u0644 \u0662\u0660\u0660\u0663. \u0648\u0642\u0627\u0644 \u0645\u0633\u0624\u0648\u0644\u0648\u0646 \u0641\u0631\u0646\u0633\u064A\u0648\u0646 \u0625\u0646\u0651 \u0634\u0631\u0637 \u0627\u0644\u0645\u0635\u062F\u0631 \u063A\u064A\u0631 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0644\u0645 \u064A\u062A\u062D\u0642\u0651\u0642. \u0644\u0627 \u062A\u062D\u0642\u064A\u0642 \u0631\u0633\u0645\u064A\u060C \u0648\u0644\u0627 \u062A\u0647\u0645\u0629\u060C \u0648\u0644\u0627 \u0642\u0631\u0627\u0631 \u0645\u0639\u0644\u0646 \u2014 \u0623\u0628\u062F\u0627\u064B.", "no"),
                ("\u0623\u0642\u0627\u0645\u062A \u0641\u064A \u0637\u0627\u0628\u0642 \u0643\u0627\u0645\u0644 \u0628\u0641\u0646\u062F\u0642 \u0628\u0627\u0631\u064A\u0633\u064A \u062E\u0645\u0633 \u0646\u062C\u0648\u0645",
                 "\u0623\u0641\u0627\u062F \u0627\u0644\u0641\u0646\u062F\u0642 \u0628\u0623\u0646\u0651\u0647\u0627 \u0644\u0645 \u062A\u0646\u0632\u0644 \u0641\u064A\u0647 \u0642\u0637\u0651. \u0648\u0646\u064F\u0634\u0631 \u0627\u0644\u0646\u0641\u064A. \u0648\u0627\u0633\u062A\u0645\u0631\u0651 \u0627\u0644\u0627\u062F\u0651\u0639\u0627\u0621 \u064A\u064F\u062A\u062F\u0627\u0648\u0644 \u062F\u0648\u0646 \u062A\u063A\u064A\u064A\u0631.", "no"),
                ("\u062A\u0644\u0642\u0651\u062A \u0661\u0660\u0660 \u0623\u0644\u0641 \u062F\u0648\u0644\u0627\u0631 \u0634\u0647\u0631\u064A\u0627\u064B \u0645\u0646 \u0627\u0644\u0645\u0627\u0644 \u0627\u0644\u0641\u0644\u0633\u0637\u064A\u0646\u064A",
                 "\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u0645 \u0637\u0648\u0627\u0644 \u0627\u062B\u0646\u062A\u064A\u0646 \u0648\u0639\u0634\u0631\u064A\u0646 \u0633\u0646\u0629 \u0623\u064A\u0651 \u0643\u0634\u0641 \u0645\u0635\u0631\u0641\u064A \u0623\u0648 \u0623\u0645\u0631 \u062A\u062D\u0648\u064A\u0644 \u0623\u0648 \u0628\u0646\u062F \u0645\u0648\u0627\u0632\u0646\u0629 \u0623\u0648 \u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649.", "no"),
                ("\u0632\u0647\u0648\u0629 \u0639\u0631\u0641\u0627\u062A \u062A\u0645\u0644\u0643 \u0668 \u0645\u0644\u064A\u0627\u0631\u0627\u062A \u0648\u0639\u0642\u0627\u0631\u0627\u062A \u0641\u064A \u0644\u0646\u062F\u0646",
                 "\u0644\u0627 \u0648\u062B\u064A\u0642\u0629 \u0648\u0644\u0627 \u0642\u064A\u062F \u0633\u062C\u0644\u0651 \u0648\u0644\u0627 \u062A\u062F\u0642\u064A\u0642 \u0648\u0644\u0627 \u062D\u0643\u0645 \u0642\u0636\u0627\u0626\u064A. \u0648\u0627\u0644\u0645\u0646\u0634\u0648\u0631 \u0646\u0641\u0633\u0647 \u064A\u0636\u0639\u0647\u0627 \u0641\u064A \u0628\u0627\u0631\u064A\u0633\u061B \u0648\u0647\u064A \u062A\u0642\u064A\u0645 \u0641\u064A \u0645\u0627\u0644\u0637\u0627 \u0645\u0646\u0630 \u0637\u0641\u0648\u0644\u062A\u0647\u0627.", "no"),
                ("\u0635\u062F\u0631\u062A \u0628\u062D\u0642\u0651\u0647\u0627 \u0645\u0630\u0643\u0631\u0629 \u062A\u0648\u0642\u064A\u0641 \u062A\u0648\u0646\u0633\u064A\u0629",
                 "\u0635\u062D\u064A\u062D. \u0635\u062F\u0631\u062A \u0641\u064A \u062A\u0634\u0631\u064A\u0646 \u0627\u0644\u0623\u0648\u0644 \u0662\u0660\u0661\u0661 \u0628\u0634\u0623\u0646 \u0645\u0634\u0631\u0648\u0639 \u0645\u062F\u0631\u0633\u0629 \u062E\u0627\u0635\u0629 \u0645\u0639 \u0645\u062D\u064A\u0637 \u0639\u0627\u0626\u0644\u0629 \u0628\u0646 \u0639\u0644\u064A \u2014 \u0645\u0633\u0623\u0644\u0629 \u062A\u062C\u0627\u0631\u064A\u0629 \u062A\u0648\u0646\u0633\u064A\u0629\u060C \u0644\u0627 \u0645\u0627\u0644\u0627\u064B \u0639\u0627\u0645\u0651\u0627\u064B \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u0627\u064B.", "doc"),
                ("\u062A\u062D\u0648\u064A\u0644 \u0669\u0660\u0660 \u0645\u0644\u064A\u0648\u0646 \u062F\u0648\u0644\u0627\u0631 \u0645\u0646 \u0627\u0644\u0625\u064A\u0631\u0627\u062F\u0627\u062A\u060C \u0661\u0669\u0669\u0665\u2013\u0662\u0660\u0660\u0660",
                 "\u0635\u062D\u064A\u062D\u060C \u0648\u0641\u0642 \u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F \u0627\u0644\u062F\u0648\u0644\u064A. \u0625\u0644\u0649 \u062D\u0633\u0627\u0628 \u064A\u0633\u064A\u0637\u0631 \u0639\u0644\u064A\u0647 \u064A\u0627\u0633\u0631 \u0639\u0631\u0641\u0627\u062A. \u0648\u0627\u0633\u062A\u064F\u0631\u062F\u0651 \u0645\u0639\u0638\u0645 \u0627\u0644\u062C\u0632\u0621 \u0627\u0644\u0645\u062A\u062A\u0628\u0651\u0639 \u0641\u064A \u0625\u0635\u0644\u0627\u062D\u0627\u062A \u0633\u0644\u0627\u0645 \u0641\u064A\u0627\u0636.", "doc"),
            ],
            k1="\u0628\u0644\u0627 \u062F\u0644\u064A\u0644 \u0623\u0648 \u0645\u0646\u0627\u0642\u0636 \u0644\u0644\u0648\u0642\u0627\u0626\u0639", k2="\u0645\u0648\u062B\u0651\u064E\u0642",
            foot="\u0627\u0644\u0645\u0635\u0627\u062F\u0631: \u0628\u064A\u0627\u0646\u0627\u062A \u0627\u0644\u0646\u064A\u0627\u0628\u0629 \u0627\u0644\u0628\u0627\u0631\u064A\u0633\u064A\u0629 \u0662\u0660\u0660\u0663\u2013\u0662\u0660\u0660\u0664\u061B \u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F \u0627\u0644\u062F\u0648\u0644\u064A \u0662\u0660\u0660\u0663\u061B \u0648\u0632\u0627\u0631\u0629 \u0627\u0644\u0639\u062F\u0644 \u0627\u0644\u062A\u0648\u0646\u0633\u064A\u0629 \u0662\u0660\u0661\u0661.",
        ),
    }[lang]

    f = Fig(lang, 800)
    f.header(T["eyebrow"], T["title"], T["sub"])

    f.t(48, 164, T["colA"], size=10.5, fill=INK2, family=f.mono, spacing="0.12em")
    f.t(452, 164, T["colB"], size=10.5, fill=INK2, family=f.mono, spacing="0.12em")
    f.line(436, 148, 436, 706, RULE, 1)

    y = 194
    wrapA = 40 if lang == "en" else 34
    wrapB = 62 if lang == "en" else 54
    for claim, record, kind in T["rows"]:
        col = RED if kind == "no" else SLATE
        f.rect(48, y - 16, 4, 62, col)
        for i, ln in enumerate(_wrap(claim, wrapA)):
            f.t(64, y + i * 19, ln, size=13.5, fill=INK, weight="600")
        for i, ln in enumerate(_wrap(record, wrapB)):
            f.t(452, y + i * 18.5, ln, size=12.5, fill=INK2)
        y += 92
        f.line(48, y - 26, W - 48, y - 26, RULE2, 1)

    f.rect(48, 724, 14, 14, RED_BG, rx=2)
    f.rect(48, 724, 4, 14, RED)
    f.t(70, 735, T["k1"], size=11, fill=RED, weight="600", family=f.mono, spacing="0.06em")
    kx = 340 if lang == "en" else 300
    f.rect(kx, 724, 14, 14, SLATE_BG, rx=2)
    f.rect(kx, 724, 4, 14, SLATE)
    f.t(kx + 22, 735, T["k2"], size=11, fill=SLATE, weight="600", family=f.mono, spacing="0.06em")

    f.footer(T["foot"])
    f.save("fig2-claim-vs-record")


# ---------------------------------------------------------------- FIGURE 3
def fig3(lang):
    T = {
        "en": dict(
            eyebrow="FIGURE 3 · THE MARKET FOR A STORY",
            title="Four buyers, and what each one got",
            sub="A smear is not a mistake. It is a product, and products have buyers.",
            l1="WHO", l2="WHEN", l3="WHAT THEY PUT INTO CIRCULATION", l4="WHAT IT BOUGHT THEM",
            cols=[
                ("The Israeli government", "2002\u20132004",
                 "Military intelligence briefs the Knesset that Arafat personally controls $1.3bn. Israeli officials are the sourcing behind the $100,000-a-month figure.",
                 "Converts a national leadership into a criminal enterprise. Once a movement is a racket, the question of what it is owed politically stops being asked."),
                ("The PA and Fatah old guard", "2004\u2013present",
                 "The largest and least sourced figures \u2014 $22m a year, \u201Chundreds of millions inherited\u201D \u2014 are attributed to unnamed Palestinian officials, not Israeli ones.",
                 "Neutralises a widow who had criticised PA corruption publicly, controlled access to the dying president, and knew where accounts were."),
                ("Ben Ali's Tunisia", "2007\u20132011",
                 "Strips her citizenship by decree after she disparages the ruling family to the US ambassador. Post-revolution, her name joins the Trabelsi dragnet.",
                 "Removes an inconvenient guest, then supplies the world with a court document that reads, at a glance, as proof of everything else."),
                ("The content economy", "2010s\u2013now",
                 "\u201CNet worth\u201D pages, viral posts, AI-generated encyclopedia entries. A state account puts $8bn in front of millions at zero cost.",
                 "Revenue, engagement, and a permanent answer to anyone who says Palestinians in Gaza need food."),
            ],
            foot="Analysis. Attributions are to the reporting cited in the accompanying article.",
        ),
        "ar": dict(
            eyebrow="\u0627\u0644\u0634\u0643\u0644 \u0663 \u00B7 \u0633\u0648\u0642 \u0627\u0644\u0631\u0648\u0627\u064A\u0629",
            title="\u0623\u0631\u0628\u0639\u0629 \u0645\u0634\u062A\u0631\u064A\u0646\u060C \u0648\u0645\u0627 \u062D\u0635\u0644 \u0639\u0644\u064A\u0647 \u0643\u0644\u0651 \u0645\u0646\u0647\u0645",
            sub="\u0627\u0644\u062A\u0634\u0647\u064A\u0631 \u0644\u064A\u0633 \u062E\u0637\u0623\u064B\u060C \u0628\u0644 \u0645\u0646\u062A\u064E\u062C\u061B \u0648\u0644\u0644\u0645\u0646\u062A\u064E\u062C \u0645\u0634\u062A\u0631\u0648\u0646.",
            l1="\u0645\u064E\u0646", l2="\u0645\u062A\u0649", l3="\u0645\u0627 \u0623\u064F\u062F\u062E\u0650\u0644 \u0625\u0644\u0649 \u0627\u0644\u062A\u062F\u0627\u0648\u0644", l4="\u0645\u0627 \u0627\u0634\u062A\u0631\u0627\u0647 \u0644\u0647\u0645",
            cols=[
                ("\u0627\u0644\u062D\u0643\u0648\u0645\u0629 \u0627\u0644\u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0629", "\u0662\u0660\u0660\u0662\u2013\u0662\u0660\u0660\u0664",
                 "\u0627\u0644\u0627\u0633\u062A\u062E\u0628\u0627\u0631\u0627\u062A \u0627\u0644\u0639\u0633\u0643\u0631\u064A\u0629 \u062A\u064F\u0628\u0644\u0650\u063A \u0627\u0644\u0643\u0646\u064A\u0633\u062A \u0623\u0646\u0651 \u0639\u0631\u0641\u0627\u062A \u064A\u0633\u064A\u0637\u0631 \u0639\u0644\u0649 \u0661.\u0663 \u0645\u0644\u064A\u0627\u0631. \u0648\u0645\u0633\u0624\u0648\u0644\u0648\u0646 \u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0648\u0646 \u0647\u0645 \u0645\u0635\u062F\u0631 \u0631\u0642\u0645 \u0627\u0644\u0645\u0626\u0629 \u0623\u0644\u0641 \u0634\u0647\u0631\u064A\u0627\u064B.",
                 "\u064A\u062D\u0648\u0651\u0644 \u0642\u064A\u0627\u062F\u0629 \u0648\u0637\u0646\u064A\u0629 \u0625\u0644\u0649 \u0639\u0635\u0627\u0628\u0629. \u0648\u0645\u062A\u0649 \u0635\u0627\u0631\u062A \u0627\u0644\u062D\u0631\u0643\u0629 \u0639\u0635\u0627\u0628\u0629\u060C \u064A\u0633\u0642\u0637 \u0627\u0644\u0633\u0624\u0627\u0644 \u0639\u0645\u0651\u0627 \u062A\u0633\u062A\u062D\u0642\u0651\u0647 \u0633\u064A\u0627\u0633\u064A\u0627\u064B."),
                ("\u0627\u0644\u062D\u0631\u0633 \u0627\u0644\u0642\u062F\u064A\u0645 \u0641\u064A \u0627\u0644\u0633\u0644\u0637\u0629 \u0648\u0641\u062A\u062D", "\u0662\u0660\u0660\u0664\u2013\u0627\u0644\u064A\u0648\u0645",
                 "\u0623\u0636\u062E\u0645 \u0627\u0644\u0623\u0631\u0642\u0627\u0645 \u0648\u0623\u0642\u0644\u0651\u0647\u0627 \u0625\u0633\u0646\u0627\u062F\u0627\u064B \u2014 \u0662\u0662 \u0645\u0644\u064A\u0648\u0646\u0627\u064B \u0633\u0646\u0648\u064A\u0627\u064B\u060C \u00AB\u0645\u0626\u0627\u062A \u0627\u0644\u0645\u0644\u0627\u064A\u064A\u0646 \u0645\u0648\u0631\u0648\u062B\u0629\u00BB \u2014 \u062A\u064F\u0646\u0633\u064E\u0628 \u0625\u0644\u0649 \u0645\u0633\u0624\u0648\u0644\u064A\u0646 \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u064A\u0646 \u0644\u0627 \u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u064A\u0646.",
                 "\u064A\u064F\u062D\u064E\u064A\u0651\u062F \u0623\u0631\u0645\u0644\u0629 \u0627\u0646\u062A\u0642\u062F\u062A \u0641\u0633\u0627\u062F \u0627\u0644\u0633\u0644\u0637\u0629 \u0639\u0644\u0646\u0627\u064B\u060C \u0648\u062A\u062D\u0643\u0651\u0645\u062A \u0628\u0627\u0644\u0648\u0635\u0648\u0644 \u0625\u0644\u0649 \u0627\u0644\u0631\u0626\u064A\u0633 \u0627\u0644\u0645\u062D\u062A\u0636\u0631\u060C \u0648\u062A\u0639\u0631\u0641 \u0645\u0648\u0627\u0642\u0639 \u0627\u0644\u062D\u0633\u0627\u0628\u0627\u062A."),
                ("\u062A\u0648\u0646\u0633 \u0628\u0646 \u0639\u0644\u064A", "\u0662\u0660\u0660\u0667\u2013\u0662\u0660\u0661\u0661",
                 "\u062A\u064F\u062C\u0631\u0651\u062F\u0647\u0627 \u0645\u0646 \u0627\u0644\u062C\u0646\u0633\u064A\u0629 \u0628\u0645\u0631\u0633\u0648\u0645 \u0628\u0639\u062F \u0627\u0646\u062A\u0642\u0627\u062F\u0647\u0627 \u0627\u0644\u0639\u0627\u0626\u0644\u0629 \u0627\u0644\u062D\u0627\u0643\u0645\u0629 \u0623\u0645\u0627\u0645 \u0627\u0644\u0633\u0641\u064A\u0631 \u0627\u0644\u0623\u0645\u064A\u0631\u0643\u064A\u060C \u062B\u0645\u0651 \u064A\u0644\u062D\u0642 \u0627\u0633\u0645\u0647\u0627 \u0628\u062D\u0645\u0644\u0629 \u0645\u0627 \u0628\u0639\u062F \u0627\u0644\u062B\u0648\u0631\u0629.",
                 "\u064A\u062A\u062E\u0644\u0651\u0635 \u0645\u0646 \u0636\u064A\u0641\u0629 \u0645\u0632\u0639\u062C\u0629\u060C \u062B\u0645\u0651 \u064A\u0645\u0646\u062D \u0627\u0644\u0639\u0627\u0644\u0645 \u0648\u062B\u064A\u0642\u0629 \u0642\u0636\u0627\u0626\u064A\u0629 \u062A\u0628\u062F\u0648 \u0644\u0644\u0648\u0647\u0644\u0629 \u0627\u0644\u0623\u0648\u0644\u0649 \u062F\u0644\u064A\u0644\u0627\u064B \u0639\u0644\u0649 \u0643\u0644\u0651 \u0645\u0627 \u0639\u062F\u0627\u0647."),
                ("\u0627\u0642\u062A\u0635\u0627\u062F \u0627\u0644\u0645\u062D\u062A\u0648\u0649", "\u0645\u0646 \u0662\u0660\u0661\u0660 \u062D\u062A\u0651\u0649 \u0627\u0644\u064A\u0648\u0645",
                 "\u0635\u0641\u062D\u0627\u062A \u00AB\u0627\u0644\u062B\u0631\u0648\u0629 \u0627\u0644\u0635\u0627\u0641\u064A\u0629\u00BB\u060C \u0645\u0646\u0634\u0648\u0631\u0627\u062A \u0641\u064A\u0631\u0648\u0633\u064A\u0629\u060C \u0645\u0648\u0633\u0648\u0639\u0627\u062A \u062A\u0648\u0644\u0651\u062F\u0647\u0627 \u0627\u0644\u0622\u0644\u0629. \u062D\u0633\u0627\u0628 \u0631\u0633\u0645\u064A \u064A\u0636\u0639 \u0668 \u0645\u0644\u064A\u0627\u0631\u0627\u062A \u0623\u0645\u0627\u0645 \u0627\u0644\u0645\u0644\u0627\u064A\u064A\u0646 \u0628\u0644\u0627 \u0643\u0644\u0641\u0629.",
                 "\u0625\u064A\u0631\u0627\u062F\u0627\u062A \u0648\u062A\u0641\u0627\u0639\u0644\u060C \u0648\u0631\u062F\u0651 \u062F\u0627\u0626\u0645 \u062C\u0627\u0647\u0632 \u0639\u0644\u0649 \u0643\u0644\u0651 \u0645\u0646 \u064A\u0642\u0648\u0644 \u0625\u0646\u0651 \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u064A \u063A\u0632\u0629 \u0628\u062D\u0627\u062C\u0629 \u0625\u0644\u0649 \u0637\u0639\u0627\u0645."),
            ],
            foot="\u062A\u062D\u0644\u064A\u0644. \u0627\u0644\u0625\u0633\u0646\u0627\u062F\u0627\u062A \u0648\u0641\u0642 \u0627\u0644\u062A\u0642\u0627\u0631\u064A\u0631 \u0627\u0644\u0645\u0630\u0643\u0648\u0631\u0629 \u0641\u064A \u0627\u0644\u0645\u0642\u0627\u0644.",
        ),
    }[lang]

    f = Fig(lang, 720)
    f.header(T["eyebrow"], T["title"], T["sub"])

    colw = 214
    gap = 14
    wrap = 30 if lang == "en" else 26
    for i, (who, when, put, got) in enumerate(T["cols"]):
        x = 48 + i * (colw + gap)
        f.rect(x, 162, colw, 6, INK)
        f.t(x, 194, when, size=10.5, fill=RED, weight="600", family=f.mono, spacing="0.12em")
        for j, ln in enumerate(_wrap(who, 22 if lang == "en" else 20)):
            f.t(x, 222 + j * 21, ln, size=16.5, fill=INK, weight="600")

        yy = 292
        f.t(x, yy, T["l3"], size=9.5, fill=INK2, family=f.mono, spacing="0.1em")
        for j, ln in enumerate(_wrap(put, wrap)):
            f.t(x, yy + 22 + j * 17.5, ln, size=12, fill=INK)

        yy2 = 470
        f.line(x, yy2 - 22, x + colw, yy2 - 22, RULE, 1)
        f.t(x, yy2, T["l4"], size=9.5, fill=SLATE, family=f.mono, spacing="0.1em")
        for j, ln in enumerate(_wrap(got, wrap)):
            f.t(x, yy2 + 22 + j * 17.5, ln, size=12, fill=INK2)

    f.footer(T["foot"])
    f.save("fig3-market-for-a-story")


# ---------------------------------------------------------------- FIGURE 4
def fig4(lang):
    T = {
        "en": dict(
            eyebrow="FIGURE 4 · THE ASYMMETRY",
            title="Who held the money. Who holds the blame.",
            sub="The two columns are drawn from the same body of reporting \u2014 including the most hostile.",
            n1="YASSER ARAFAT", n2="SUHA ARAFAT",
            h1="CONTROL OF FUNDS", h2="HOW HE IS REMEMBERED",
            h3="CONTROL OF FUNDS", h4="HOW SHE IS REMEMBERED",
            a=["IMF: $900m in revenue routed to an account under his personal control, 1995\u20132000",
               "Forensic audit: a secret portfolio worth close to $1bn",
               "Sole signatory over monopolies on cement, fuel and cigarettes"],
            b=["Ascetic. Frugal. Lived in a shelled compound.",
               "A former head of the Palestinian National Fund: no house, no orchard, no personal account.",
               "His accusers volunteered his personal austerity."],
            c=["No budget authority. No signing power. No office.",
               "Never charged, anywhere, with taking Palestinian public funds.",
               "No bank record has ever been produced."],
            d=["The shopping. The hotel. The fashion shows.",
               "Her uncovered hair. Her Western clothes.",
               "A neighbour's verdict, printed in a US daily: Paris and money do that to a person."],
            kicker="THE MONEY WENT WHERE THE CONTROL WAS. THE BLAME WENT WHERE THE WOMAN WAS.",
            foot="Sources: IMF Sept 2003; forensic audit commissioned by the PA finance ministry; contemporaneous US and Israeli reporting.",
        ),
        "ar": dict(
            eyebrow="\u0627\u0644\u0634\u0643\u0644 \u0664 \u00B7 \u0627\u0644\u0627\u062E\u062A\u0644\u0627\u0644",
            title="\u0645\u064E\u0646 \u0623\u0645\u0633\u0643 \u0627\u0644\u0645\u0627\u0644\u061F \u0648\u0645\u064E\u0646 \u064A\u062D\u0645\u0644 \u0627\u0644\u062A\u0647\u0645\u0629\u061F",
            sub="\u0627\u0644\u0639\u0645\u0648\u062F\u0627\u0646 \u0645\u0633\u062A\u0645\u062F\u0651\u0627\u0646 \u0645\u0646 \u0627\u0644\u0645\u0627\u062F\u0629 \u0627\u0644\u0635\u062D\u0641\u064A\u0629 \u0646\u0641\u0633\u0647\u0627 \u2014 \u0628\u0645\u0627 \u0641\u064A\u0647\u0627 \u0623\u0634\u062F\u0651\u0647\u0627 \u0639\u062F\u0627\u0621\u064B.",
            n1="\u064A\u0627\u0633\u0631 \u0639\u0631\u0641\u0627\u062A", n2="\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A",
            h1="\u0627\u0644\u0633\u064A\u0637\u0631\u0629 \u0639\u0644\u0649 \u0627\u0644\u0645\u0627\u0644", h2="\u0643\u064A\u0641 \u064A\u064F\u0630\u0643\u064E\u0631",
            h3="\u0627\u0644\u0633\u064A\u0637\u0631\u0629 \u0639\u0644\u0649 \u0627\u0644\u0645\u0627\u0644", h4="\u0643\u064A\u0641 \u062A\u064F\u0630\u0643\u064E\u0631",
            a=["\u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F: \u0669\u0660\u0660 \u0645\u0644\u064A\u0648\u0646 \u062F\u0648\u0644\u0627\u0631 \u0625\u0644\u0649 \u062D\u0633\u0627\u0628 \u062A\u062D\u062A \u0633\u064A\u0637\u0631\u062A\u0647 \u0627\u0644\u0634\u062E\u0635\u064A\u0629\u060C \u0661\u0669\u0669\u0665\u2013\u0662\u0660\u0660\u0660",
               "\u062A\u062F\u0642\u064A\u0642 \u062C\u0646\u0627\u0626\u064A: \u0645\u062D\u0641\u0638\u0629 \u0627\u0633\u062A\u062B\u0645\u0627\u0631\u064A\u0629 \u0633\u0631\u064A\u0629 \u062A\u0642\u0627\u0631\u0628 \u0627\u0644\u0645\u0644\u064A\u0627\u0631",
               "\u0627\u0644\u0645\u0648\u0642\u0651\u0650\u0639 \u0627\u0644\u0648\u062D\u064A\u062F \u0639\u0644\u0649 \u0627\u062D\u062A\u0643\u0627\u0631\u0627\u062A \u0627\u0644\u0625\u0633\u0645\u0646\u062A \u0648\u0627\u0644\u0648\u0642\u0648\u062F \u0648\u0627\u0644\u062A\u0628\u063A"],
            b=["\u0632\u0627\u0647\u062F. \u0645\u0642\u062A\u0635\u062F. \u0639\u0627\u0634 \u0641\u064A \u0645\u0642\u0631\u0651 \u0645\u0642\u0635\u0648\u0641.",
               "\u0631\u0626\u064A\u0633 \u0633\u0627\u0628\u0642 \u0644\u0644\u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0642\u0648\u0645\u064A: \u0644\u0627 \u0628\u064A\u062A \u0648\u0644\u0627 \u0628\u0633\u062A\u0627\u0646 \u0648\u0644\u0627 \u062D\u0633\u0627\u0628 \u0634\u062E\u0635\u064A.",
               "\u0648\u0645\u062A\u0651\u0647\u0645\u0648\u0647 \u0623\u0646\u0641\u0633\u0647\u0645 \u0634\u0647\u062F\u0648\u0627 \u0628\u062A\u0642\u0634\u0651\u0641\u0647."],
            c=["\u0644\u0627 \u0635\u0644\u0627\u062D\u064A\u0629 \u0645\u0627\u0644\u064A\u0629. \u0644\u0627 \u062D\u0642\u0651 \u062A\u0648\u0642\u064A\u0639. \u0644\u0627 \u0645\u0646\u0635\u0628.",
               "\u0644\u0645 \u062A\u064F\u062A\u0651\u0647\u0645 \u0642\u0637\u0651\u060C \u0641\u064A \u0623\u064A\u0651 \u0645\u0643\u0627\u0646\u060C \u0628\u0623\u062E\u0630 \u0645\u0627\u0644 \u0639\u0627\u0645\u0651 \u0641\u0644\u0633\u0637\u064A\u0646\u064A.",
               "\u0648\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u0623\u064A\u0651 \u0643\u0634\u0641 \u0645\u0635\u0631\u0641\u064A \u0642\u0637\u0651."],
            d=["\u0627\u0644\u062A\u0633\u0648\u0651\u0642. \u0627\u0644\u0641\u0646\u062F\u0642. \u0639\u0631\u0648\u0636 \u0627\u0644\u0623\u0632\u064A\u0627\u0621.",
               "\u0634\u0639\u0631\u0647\u0627 \u0627\u0644\u0645\u0643\u0634\u0648\u0641. \u0645\u0644\u0627\u0628\u0633\u0647\u0627 \u0627\u0644\u063A\u0631\u0628\u064A\u0629.",
               "\u062D\u0643\u0645 \u062C\u0627\u0631\u0629\u060C \u0646\u064F\u0634\u0631 \u0641\u064A \u0635\u062D\u064A\u0641\u0629 \u0623\u0645\u064A\u0631\u0643\u064A\u0629: \u0628\u0627\u0631\u064A\u0633 \u0648\u0627\u0644\u0645\u0627\u0644 \u064A\u0641\u0639\u0644\u0627\u0646 \u0630\u0644\u0643 \u0628\u0627\u0644\u0645\u0631\u0621."],
            kicker="\u0630\u0647\u0628 \u0627\u0644\u0645\u0627\u0644 \u062D\u064A\u062B \u0643\u0627\u0646\u062A \u0627\u0644\u0633\u064A\u0637\u0631\u0629. \u0648\u0630\u0647\u0628\u062A \u0627\u0644\u062A\u0647\u0645\u0629 \u062D\u064A\u062B \u0643\u0627\u0646\u062A \u0627\u0644\u0645\u0631\u0623\u0629.",
            foot="\u0627\u0644\u0645\u0635\u0627\u062F\u0631: \u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F \u0627\u0644\u062F\u0648\u0644\u064A \u0662\u0660\u0660\u0663\u061B \u062A\u062F\u0642\u064A\u0642 \u0643\u0644\u0651\u0641\u062A\u0647 \u0648\u0632\u0627\u0631\u0629 \u0627\u0644\u0645\u0627\u0644\u064A\u0629 \u0627\u0644\u0641\u0644\u0633\u0637\u064A\u0646\u064A\u0629\u061B \u062A\u0642\u0627\u0631\u064A\u0631 \u0623\u0645\u064A\u0631\u0643\u064A\u0629 \u0648\u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0629 \u0645\u0639\u0627\u0635\u0631\u0629.",
        ),
    }[lang]

    f = Fig(lang, 700)
    f.header(T["eyebrow"], T["title"], T["sub"])
    mid = 500
    f.line(mid, 152, mid, 596, RULE, 1)
    wrap = 44 if lang == "en" else 38

    def panel(x, name, hA, listA, hB, listB, accent):
        f.rect(x, 164, 5, 26, accent)
        f.t(x + 18, 184, name, size=19, fill=INK, weight="600", spacing="0.02em")
        f.t(x, 226, hA, size=9.5, fill=accent, family=f.mono, spacing="0.12em")
        y = 250
        for item in listA:
            for i, ln in enumerate(_wrap(item, wrap)):
                f.t(x + 14, y + i * 17.5, ln, size=12, fill=INK)
            f.rect(x, y - 9, 3, 12, accent, opacity="0.5")
            y += 17.5 * len(_wrap(item, wrap)) + 16
        y += 12
        f.line(x, y - 18, x + 400, y - 18, RULE, 1)
        f.t(x, y, hB, size=9.5, fill=INK2, family=f.mono, spacing="0.12em")
        y += 24
        for item in listB:
            for i, ln in enumerate(_wrap(item, wrap)):
                f.t(x + 14, y + i * 17.5, ln, size=12, fill=INK2)
            f.rect(x, y - 9, 3, 12, RULE, opacity="0.9")
            y += 17.5 * len(_wrap(item, wrap)) + 16

    panel(48, T["n1"], T["h1"], T["a"], T["h2"], T["b"], SLATE)
    panel(mid + 40, T["n2"], T["h3"], T["c"], T["h4"], T["d"], RED)

    f.rect(48, 612, W - 96, 42, INK, rx=2)
    f.t(W / 2, 638, T["kicker"], size=13.5, fill=PAPER, weight="600",
        family=f.mono, anchor="middle", spacing="0.04em")
    f.footer(T["foot"])
    f.save("fig4-the-asymmetry")


# ---------------------------------------------------------------- FIGURE 5
def fig5(lang):
    T = {
        "en": dict(
            eyebrow="FIGURE 5 · ANATOMY OF A CLAIM",
            title="Four assertions about a private citizen",
            sub="Posted January 2025 by the official account of the State of Israel, concerning Zahwa Arafat \u2014 born 1995, no public office, never charged with anything, anywhere.",
            rows=[
                ("01", "She is worth $8 billion",
                 "No filing, registry entry, audit, court record or named source has ever been produced.", "UNEVIDENCED"),
                ("02", "She owns prime real estate across London",
                 "No title record, company filing or address has ever been produced.", "UNEVIDENCED"),
                ("03", "She lives in Paris",
                 "She has lived in Malta since childhood. Wire photographs filed from her family's Malta home in 2011 and 2012; family interviews from 2009 to 2025; a degree from a Maltese university.",
                 "FALSE \u2014 AND CHECKABLE"),
                ("04", "She is eligible for UNRWA funds as a refugee",
                 "No evidence has been offered that she has ever registered with, applied to, or received anything from UNRWA.", "UNEVIDENCED"),
            ],
            kicker="If the easiest verifiable detail in a four-sentence claim is wrong,\nask what standard of care was applied to the other three.",
            foot="The post remains publicly visible. No correction has been issued.",
        ),
        "ar": dict(
            eyebrow="\u0627\u0644\u0634\u0643\u0644 \u0665 \u00B7 \u062A\u0634\u0631\u064A\u062D \u0627\u062F\u0651\u0639\u0627\u0621",
            title="\u0623\u0631\u0628\u0639 \u062F\u0639\u0627\u0648\u0649 \u0628\u062D\u0642\u0651 \u0645\u0648\u0627\u0637\u0646\u0629 \u062E\u0627\u0635\u0629",
            sub="\u0646\u064F\u0634\u0650\u0631\u062A \u0641\u064A \u0643\u0627\u0646\u0648\u0646 \u0627\u0644\u062B\u0627\u0646\u064A \u0662\u0660\u0662\u0665 \u0639\u0646 \u0627\u0644\u062D\u0633\u0627\u0628 \u0627\u0644\u0631\u0633\u0645\u064A \u0644\u062F\u0648\u0644\u0629 \u0625\u0633\u0631\u0627\u0626\u064A\u0644 \u0628\u0634\u0623\u0646 \u0632\u0647\u0648\u0629 \u0639\u0631\u0641\u0627\u062A \u2014 \u0645\u0648\u0627\u0644\u064A\u062F \u0661\u0669\u0669\u0665\u060C \u0628\u0644\u0627 \u0645\u0646\u0635\u0628 \u0639\u0627\u0645\u060C \u0648\u0644\u0645 \u062A\u064F\u062A\u0651\u0647\u0645 \u0628\u0634\u064A\u0621 \u0641\u064A \u0623\u064A\u0651 \u0645\u0643\u0627\u0646.",
            rows=[
                ("\u0660\u0661", "\u062A\u0645\u0644\u0643 \u062B\u0645\u0627\u0646\u064A\u0629 \u0645\u0644\u064A\u0627\u0631\u0627\u062A \u062F\u0648\u0644\u0627\u0631",
                 "\u0644\u0645 \u062A\u064F\u0642\u062F\u0651\u064E\u0645 \u0642\u0637\u0651 \u0623\u064A\u0651 \u0648\u062B\u064A\u0642\u0629 \u0623\u0648 \u0642\u064A\u062F \u0633\u062C\u0644\u0651 \u0623\u0648 \u062A\u062F\u0642\u064A\u0642 \u0623\u0648 \u062D\u0643\u0645 \u0642\u0636\u0627\u0626\u064A \u0623\u0648 \u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649.", "\u0628\u0644\u0627 \u062F\u0644\u064A\u0644"),
                ("\u0660\u0662", "\u062A\u0645\u0644\u0643 \u0639\u0642\u0627\u0631\u0627\u062A \u0631\u0627\u0642\u064A\u0629 \u0641\u064A \u0644\u0646\u062F\u0646",
                 "\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u0623\u064A\u0651 \u0633\u0646\u062F \u0645\u0644\u0643\u064A\u0629 \u0623\u0648 \u0633\u062C\u0644\u0651 \u0634\u0631\u0643\u0629 \u0623\u0648 \u0639\u0646\u0648\u0627\u0646.", "\u0628\u0644\u0627 \u062F\u0644\u064A\u0644"),
                ("\u0660\u0663", "\u062A\u0639\u064A\u0634 \u0641\u064A \u0628\u0627\u0631\u064A\u0633",
                 "\u0647\u064A \u062A\u0642\u064A\u0645 \u0641\u064A \u0645\u0627\u0644\u0637\u0627 \u0645\u0646\u0630 \u0637\u0641\u0648\u0644\u062A\u0647\u0627. \u0635\u0648\u0631 \u0648\u0643\u0627\u0644\u0627\u062A \u0645\u0646 \u0645\u0646\u0632\u0644 \u0627\u0644\u0639\u0627\u0626\u0644\u0629 \u0641\u064A \u0645\u0627\u0644\u0637\u0627 \u0662\u0660\u0661\u0661 \u0648\u0662\u0660\u0661\u0662\u061B \u0645\u0642\u0627\u0628\u0644\u0627\u062A \u0639\u0627\u0626\u0644\u064A\u0629 \u0645\u0646 \u0662\u0660\u0660\u0669 \u0625\u0644\u0649 \u0662\u0660\u0662\u0665\u061B \u0648\u0634\u0647\u0627\u062F\u0629 \u062C\u0627\u0645\u0639\u064A\u0629 \u0645\u0627\u0644\u0637\u064A\u0629.",
                 "\u062E\u0627\u0637\u0626 \u2014 \u0648\u0642\u0627\u0628\u0644 \u0644\u0644\u062A\u062D\u0642\u0651\u0642"),
                ("\u0660\u0664", "\u062A\u0633\u062A\u062D\u0642\u0651 \u0623\u0645\u0648\u0627\u0644 \u0627\u0644\u0623\u0648\u0646\u0631\u0648\u0627 \u0628\u0648\u0635\u0641\u0647\u0627 \u0644\u0627\u062C\u0626\u0629",
                 "\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u062F\u0644\u064A\u0644 \u0639\u0644\u0649 \u0623\u0646\u0651\u0647\u0627 \u0633\u062C\u0651\u0644\u062A \u0644\u062F\u0649 \u0627\u0644\u0623\u0648\u0646\u0631\u0648\u0627 \u0623\u0648 \u062A\u0642\u062F\u0651\u0645\u062A \u0625\u0644\u064A\u0647\u0627 \u0623\u0648 \u062A\u0644\u0642\u0651\u062A \u0645\u0646\u0647\u0627 \u0634\u064A\u0626\u0627\u064B.", "\u0628\u0644\u0627 \u062F\u0644\u064A\u0644"),
            ],
            kicker="\u0625\u0630\u0627 \u0643\u0627\u0646\u062A \u0623\u0633\u0647\u0644 \u062A\u0641\u0635\u064A\u0644\u0629 \u0642\u0627\u0628\u0644\u0629 \u0644\u0644\u062A\u062D\u0642\u0642 \u0641\u064A \u0627\u062F\u0651\u0639\u0627\u0621 \u0645\u0646 \u0623\u0631\u0628\u0639 \u062C\u0645\u0644 \u062E\u0627\u0637\u0626\u0629\u060C\n\u0641\u0627\u0633\u0623\u0644 \u0623\u064A\u0651 \u0639\u0646\u0627\u064A\u0629 \u0628\u064F\u0630\u0644\u062A \u0641\u064A \u0627\u0644\u062B\u0644\u0627\u062B \u0627\u0644\u0623\u062E\u0631\u0649.",
            foot="\u0627\u0644\u0645\u0646\u0634\u0648\u0631 \u0645\u0627 \u0632\u0627\u0644 \u0645\u062A\u0627\u062D\u0627\u064B \u0644\u0644\u0639\u0644\u0646. \u0648\u0644\u0645 \u064A\u0635\u062F\u0631 \u0623\u064A\u0651 \u062A\u0635\u062D\u064A\u062D.",
        ),
    }[lang]

    f = Fig(lang, 800)
    f.header(T["eyebrow"], T["title"], "")
    for i, ln in enumerate(_wrap(T["sub"], 118 if lang == "en" else 100)):
        f.t(48, 114 + i * 18, ln, size=13, fill=INK2)
    f.line(48, 156, W - 48, 156, RULE, 1)

    y = 196
    wrap = 84 if lang == "en" else 72
    for num, claim, check, verdict in T["rows"]:
        false_row = "FALSE" in verdict or "\u062E\u0627\u0637\u0626" in verdict
        col = RED
        f.t(48, y + 2, num, size=26, fill=RULE, weight="700", family=f.mono)
        f.t(100, y, claim, size=16, fill=INK, weight="600")
        lines = _wrap(check, wrap)
        for j, ln in enumerate(lines):
            f.t(100, y + 24 + j * 17.5, ln, size=12, fill=INK2)
        vy = y + 26 + len(lines) * 17.5
        f.tag(100, vy, verdict, "no")
        if false_row:
            f.rect(48, y - 22, W - 96, 34 + len(lines) * 17.5 + 26, RED, rx=2, opacity="0.05")
        y += 56 + len(lines) * 17.5 + 26
        if num not in ("04", "\u0660\u0664"):
            f.line(48, y - 32, W - 48, y - 32, RULE2, 1)

    ky = y - 6
    f.rect(48, ky, W - 96, 56, INK, rx=2)
    for i, ln in enumerate(T["kicker"].split("\n")):
        f.t(W / 2, ky + 24 + i * 20, ln, size=13, fill=PAPER, weight="600",
            anchor="middle", family=f.mono)
    f.h = int(ky + 56 + 62)
    f.p[0] = '<rect x="0" y="0" width="%d" height="%d" fill="%s" rx="0"/>' % (W, f.h, PAPER)
    f.footer(T["foot"])
    f.save("fig5-anatomy-of-a-claim")


def _wrap(s, n):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= n:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


if __name__ == "__main__":
    for lang in ("en",):
        fig1(lang); fig2(lang); fig3(lang); fig4(lang); fig5(lang)
