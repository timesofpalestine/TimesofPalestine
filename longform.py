"""Long-form rendering for original reporting: subheads, figures, tables, lists.

The story renderer takes plain paragraphs, which is all a wire brief ever needs. A
researched package is different — it carries section subheads, explanatory charts, an
at-a-glance table and source notes, and flattening those loses the work.

This module turns a restrained subset of Markdown into real HTML so an editor can
write a long-form original without HTML, and so nothing arrives on the page as a
literal ![alt](file.png). Deliberately small: no inline HTML passthrough, no nested
lists, no arbitrary Markdown. Anything unrecognised falls through as a paragraph,
which is the same behaviour the site had before.

Images referenced as ![alt](name.png) are looked up in originals/media/ and copied to
dist/media/, then served from /media/name.png so the path works from any page depth.
"""
import html
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
MEDIA_SRC = ROOT / "originals" / "media"

H_RX = re.compile(r"^(#{2,4})\s+(.*)$")
IMG_RX = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
ROW_RX = re.compile(r"^\|(.+)\|\s*$")
SEP_RX = re.compile(r"^\|[\s:|-]+\|\s*$")
LI_RX = re.compile(r"^[-*]\s+(.*)$")
BOLD_RX = re.compile(r"\*\*(.+?)\*\*")
LINK_RX = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _esc(s):
    return html.escape(s or "", quote=True)


def _inline(text):
    """Escape first, then re-introduce the two inline marks we allow."""
    out = _esc(text)
    out = LINK_RX.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = BOLD_RX.sub(r"<strong>\1</strong>", out)
    return out


def _cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def body_html(text, media_prefix="/media/"):
    """Render a long-form body. Unrecognised lines become paragraphs, as before."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        m = H_RX.match(line)
        if m:
            level = min(len(m.group(1)), 4)          # ## -> h2, ### -> h3, #### -> h4
            out.append(f'<h{level} class="sub">{_inline(m.group(2).strip())}</h{level}>')
            i += 1
            continue

        m = IMG_RX.match(line)
        if m:
            alt, src = m.group(1).strip(), m.group(2).strip()
            if not src.startswith(("http://", "https://", "/")):
                src = media_prefix + src.lstrip("./")
            cap = f'<figcaption>{_inline(alt)}</figcaption>' if alt else ""
            out.append(f'<figure class="lf"><img src="{_esc(src)}" alt="{_esc(alt)}" '
                       f'loading="lazy">{cap}</figure>')
            i += 1
            continue

        if ROW_RX.match(line):                        # a pipe table: header, sep, rows
            rows = []
            while i < len(lines) and ROW_RX.match(lines[i].strip()):
                if not SEP_RX.match(lines[i].strip()):
                    rows.append(_cells(lines[i]))
                i += 1
            if rows:
                head = "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
                body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                               for r in rows[1:])
                out.append(f'<div class="tablewrap"><table class="lf"><thead><tr>{head}</tr>'
                           f"</thead><tbody>{body}</tbody></table></div>")
            continue

        if LI_RX.match(line):
            items = []
            while i < len(lines) and LI_RX.match(lines[i].strip()):
                items.append(LI_RX.match(lines[i].strip()).group(1).strip())
                i += 1
            out.append('<ul class="lf">' + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            continue

        out.append(f'<p class="summary">{_inline(line)}</p>')
        i += 1
    return "".join(out)


def copy_media(dist):
    """Copy originals/media/* to dist/media/ so ![alt](name.png) resolves. Fail-open."""
    try:
        if not MEDIA_SRC.is_dir():
            return 0
        dest = Path(dist) / "media"
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in MEDIA_SRC.iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy2(f, dest / f.name)
                n += 1
        if n:
            print(f"  → long-form media: {n} file(s) copied")
        return n
    except Exception as e:
        print(f"  ✗ long-form media copy skipped ({type(e).__name__})")
        return 0


CSS = """
.story .sub{font-family:var(--serif);font-weight:800;line-height:1.25;margin:1.9rem 0 .6rem;color:var(--black)}
.story h2.sub{font-size:1.42rem}
.story h3.sub{font-size:1.14rem}
.story h4.sub{font-size:1rem;text-transform:uppercase;letter-spacing:.06em;font-family:var(--sans)}
[lang=ar] .story .sub{font-weight:800;line-height:1.5}
[lang=ar] .story h4.sub{letter-spacing:0;text-transform:none}
.story ul.lf{margin:.9rem 0 1.1rem;padding-inline-start:1.3rem;font-family:var(--serif);font-size:1.06rem;line-height:1.7;color:#26262e}
.story ul.lf li{margin-bottom:.5rem}
[lang=ar] .story ul.lf{line-height:2}
.story figure.lf{margin:1.7rem 0}
.story figure.lf img{width:100%;height:auto;background:#e8e6df;border:1px solid var(--line)}
.story figure.lf figcaption{margin-top:.5rem;font-size:.8rem;color:var(--muted);line-height:1.5}
.story .tablewrap{overflow-x:auto;margin:1.5rem 0}
.story table.lf{border-collapse:collapse;width:100%;font-size:.92rem}
.story table.lf th,.story table.lf td{border:1px solid var(--line-dark);padding:.55rem .7rem;text-align:start;vertical-align:top}
.story table.lf th{background:rgba(0,0,0,.04);font-weight:800;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}
[lang=ar] .story table.lf th{letter-spacing:0;text-transform:none;font-size:.88rem}
.story .summary a{text-decoration:underline;text-underline-offset:2px}
@media (prefers-color-scheme:dark){
  .story .sub{color:var(--ink)}
  .story ul.lf{color:#d6d6de}
  .story table.lf th{background:rgba(255,255,255,.06)}
}
"""
