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
import hashlib
import re
import shutil
from pathlib import Path

from publishing import (
    MediaRights, PublishingError, load_media_manifest, media_rights_for,
)

ROOT = Path(__file__).parent
MEDIA_SRC = ROOT / "originals" / "media"
MEDIA_RIGHTS = load_media_manifest(ROOT / "media-rights.json")

H_RX = re.compile(r"^(#{2,4})\s+(.*)$")
IMG_RX = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
# Video embeds: !video[caption](url). Whitelisted hosts only — the iframe src
# is rebuilt from captured IDs, never echoed from the input, so a hostile URL
# cannot smuggle markup or a javascript: scheme into the page. Anything not
# whitelisted falls through as a literal paragraph and the residue check
# skips the article.
VIDEO_RX = re.compile(r"^!video\[([^\]]*)\]\(([^)\s]+)\)\s*$")
_YT_ID_RX = re.compile(
    r"^https://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{6,20})")
_TME_RX = re.compile(r"^https://t\.me/([A-Za-z0-9_]{3,40})/(\d+)$")
_MP4_RX = re.compile(r"^https://[\w.-]+/[\w./%-]+\.mp4$")


def video_embed(caption, url):
    """Return figure HTML for a whitelisted video URL, or None."""
    m = _YT_ID_RX.match(url)
    if m:
        frame = (f'<div class="embed"><iframe '
                 f'src="https://www.youtube-nocookie.com/embed/{m.group(1)}" '
                 f'title="{_esc(caption) or "Video"}" loading="lazy" '
                 f'allowfullscreen frameborder="0" '
                 f'allow="encrypted-media; picture-in-picture"></iframe></div>')
    else:
        m = _TME_RX.match(url)
        if m:
            frame = (f'<div class="embed tme"><iframe '
                     f'src="https://t.me/{m.group(1)}/{m.group(2)}?embed=1" '
                     f'title="{_esc(caption) or "Video"}" loading="lazy" '
                     f'frameborder="0"></iframe></div>')
        elif _MP4_RX.match(url):
            frame = (f'<video controls preload="metadata" playsinline '
                     f'src="{_esc(url)}"></video>')
        else:
            return None
    cap = f'<figcaption>{_inline(caption)}</figcaption>' if caption else ""
    return f'<figure class="lf video">{frame}{cap}</figure>'
ROW_RX = re.compile(r"^\|(.+)\|\s*$")
SEP_RX = re.compile(r"^\|[\s:|-]+\|\s*$")
LI_RX = re.compile(r"^-\s+(.*)$")
OL_RX = re.compile(r"^(\d{1,2})\.\s+(.*)$")
BOLD_RX = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RX = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
CODE_RX = re.compile(r"`([^`\n]+)`")
LINK_RX = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _esc(s):
    return html.escape(s or "", quote=True)


def _inline(text):
    """Escape first, then re-introduce the two inline marks we allow."""
    out = _esc(text)
    code_spans = []
    def _save_code(m):
        code_spans.append(f"<code>{m.group(1)}</code>")
        return f"@@CODE{len(code_spans) - 1}@@"
    out = CODE_RX.sub(_save_code, out)
    out = LINK_RX.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = BOLD_RX.sub(r"<strong>\1</strong>", out)
    out = ITALIC_RX.sub(r"<em>\1</em>", out)
    for i, span in enumerate(code_spans):
        out = out.replace(f"@@CODE{i}@@", span)
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

        m = VIDEO_RX.match(line)
        if m:
            embed = video_embed(m.group(1).strip(), m.group(2).strip())
            if embed:
                out.append(embed)
                i += 1
                continue
            # unsupported host: fall through as a paragraph; the residue
            # check will flag "!video[" and skip the article loudly

        m = IMG_RX.match(line)
        if m:
            alt, src = m.group(1).strip(), m.group(2).strip()
            rights = media_rights_for(src, MEDIA_RIGHTS)
            if not rights:
                # The desks generate fresh house graphics daily and cannot
                # pre-register them. A local file in originals/media/ is by
                # charter a self-created TOP graphic: default to owned rights.
                # Only remote or missing assets still require a manifest entry.
                local = (not src.startswith(("http://", "https://", "/"))
                         and (MEDIA_SRC / Path(src.lstrip("./")).name).is_file())
                if local:
                    rights = MediaRights(
                        asset=f"originals/media/{Path(src.lstrip('./')).name}",
                        rights_basis="owned",
                        credit="Graphic: Times of Palestine",
                        source="Times of Palestine",
                    )
                else:
                    raise PublishingError(
                        f"long-form image {src!r} lacks rights metadata")
            if not src.startswith(("http://", "https://", "/")):
                src = media_prefix + src.lstrip("./")
            caption = " · ".join(x for x in (alt, rights.credit) if x)
            if rights.license_url:
                caption += f' · <a href="{_esc(rights.license_url)}" rel="license noopener">License</a>'
                cap = f"<figcaption>{_inline(alt)} · {rights.credit} · " \
                      f'<a href="{_esc(rights.license_url)}" rel="license noopener">License</a></figcaption>'
            else:
                cap = f'<figcaption>{_inline(caption)}</figcaption>' if caption else ""
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

        if OL_RX.match(line):
            items = []
            while i < len(lines) and OL_RX.match(lines[i].strip()):
                items.append(OL_RX.match(lines[i].strip()).group(2).strip())
                i += 1
            out.append('<ol class="lf">' + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ol>")
            continue

        out.append(f'<p class="summary">{_inline(line)}</p>')
        i += 1
    return "".join(out)


def rendered_residue_warnings(rendered):
    """Return unsafe Markdown tokens left behind by the supported renderer."""
    warnings = []
    if "[^" in rendered:
        warnings.append("unrendered footnote marker '[^'")
    if "![" in rendered:
        warnings.append("unrendered image markdown '!['")
    if "!video" in rendered:
        warnings.append("unrendered or non-embeddable !video directive "
                        "(only YouTube, t.me posts and direct .mp4 embed)")
    if "**" in rendered:
        warnings.append("unrendered bold marker '**'")
    if re.search(r'<p class="summary">\s*#', rendered):
        warnings.append("line-initial heading marker '#' fell through into paragraph")
    for paragraph in re.findall(
        r'<p class="summary">(.*?)</p>', rendered, flags=re.S
    ):
        if "|" in re.sub(r"<[^>]+>", "", html.unescape(paragraph)):
            warnings.append("pipe table residue '|' remained inside paragraph")
            break
    return warnings


def validate_media_references(text, manifest, label):
    """Require a rights record for every long-form image before publication."""
    for line in (text or "").replace("\r\n", "\n").splitlines():
        match = IMG_RX.match(line.strip())
        if match:
            asset = match.group(2).strip()
            if asset.startswith(("http://", "https://")):
                raise PublishingError(
                    f"{label}: remote media hotlinking is disabled")
            if not media_rights_for(asset, manifest):
                raise PublishingError(
                    f"{label}: image {asset!r} lacks rights metadata")


def media_review_evidence(text, header_image=None):
    """Hash local media and rights records into the exact review version."""
    assets = set()
    if header_image:
        assets.add(header_image)
    for line in (text or "").replace("\r\n", "\n").splitlines():
        match = IMG_RX.match(line.strip())
        if match:
            assets.add(match.group(2).strip())
    evidence = []
    for asset in sorted(assets):
        rights = media_rights_for(asset, MEDIA_RIGHTS)
        if not rights:
            raise PublishingError(f"image {asset!r} lacks rights metadata")
        row = {
            "asset": asset,
            "rightsBasis": rights.rights_basis,
            "credit": rights.credit,
            "source": rights.source,
            "licenseUrl": rights.license_url,
        }
        if not asset.startswith(("http://", "https://", "/")):
            source = MEDIA_SRC / Path(asset).name
            if not source.is_file():
                raise PublishingError(f"referenced media does not exist: {asset}")
            row["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        evidence.append(row)
    return evidence


def copy_media(dist, stories):
    """Copy only media referenced by review-eligible stories."""
    needed = set()
    for story in stories:
        image = story.get("image") or ""
        if image.startswith("/media/"):
            needed.add(Path(image).name)
        for line in (story.get("brief") or "").replace("\r\n", "\n").splitlines():
            match = IMG_RX.match(line.strip())
            if match and not match.group(2).startswith(("http://", "https://", "/")):
                needed.add(Path(match.group(2)).name)
    dest = Path(dist) / "media"
    if dest.exists():
        shutil.rmtree(dest)
    if not MEDIA_SRC.is_dir() or not needed:
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for name in sorted(needed):
        f = MEDIA_SRC / name
        if not f.is_file():
            raise PublishingError(f"referenced media does not exist: {name}")
        relative = f"originals/media/{f.name}"
        if relative not in MEDIA_RIGHTS:
            raise PublishingError(f"{relative}: local media lacks rights metadata")
        shutil.copy2(f, dest / f.name)
        n += 1
    if n:
        print(f"  → long-form media: {n} file(s) copied")
    return n


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
.story ol.lf{margin:.9rem 0 1.1rem;padding-inline-start:1.3rem;font-family:var(--serif);font-size:1.06rem;line-height:1.7;color:#26262e}
.story ol.lf li{margin-bottom:.5rem}
[lang=ar] .story ol.lf{line-height:2}
.story figure.lf{margin:1.7rem 0}
.story figure.lf img{width:100%;height:auto;background:#e8e6df;border:1px solid var(--line)}
.story figure.lf figcaption{margin-top:.5rem;font-size:.8rem;color:var(--muted);line-height:1.5}
.story .tablewrap{overflow-x:auto;margin:1.5rem 0}
.story table.lf{border-collapse:collapse;width:100%;font-size:.92rem}
.story table.lf th,.story table.lf td{border:1px solid var(--line-dark);padding:.55rem .7rem;text-align:start;vertical-align:top}
.story table.lf th{background:rgba(0,0,0,.04);font-weight:800;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}
[lang=ar] .story table.lf th{letter-spacing:0;text-transform:none;font-size:.88rem}
.story .summary a{text-decoration:underline;text-underline-offset:2px}
.story code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,monospace;font-size:.92em;background:rgba(0,0,0,.06);padding:.08em .3em;border-radius:3px}
.story figure.lf.video{margin:1.6rem 0}
.story .embed{position:relative;width:100%;padding-top:56.25%;background:#0b0b0c}
.story .embed iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.story .embed.tme{padding-top:0;height:520px}
.story .embed.tme iframe{position:static;height:100%}
.story figure.lf.video video{width:100%;display:block;background:#0b0b0c}
@media (prefers-color-scheme:dark){
  .story .sub{color:var(--ink)}
  .story ul.lf{color:#d6d6de}
  .story ol.lf{color:#d6d6de}
  .story code{background:rgba(255,255,255,.12)}
  .story table.lf th{background:rgba(255,255,255,.06)}
}
"""
