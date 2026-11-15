#!/usr/bin/env python3
"""Genera il sito statico Erasmus+ a partire da src/mobilities.json.

Uso:  python3 tools/build.py

Per ogni mobilità (cartella <slug>/):
  photos/*.jpg   foto della galleria (ordinate per nome). Le foto grandi vengono
                 ridimensionate in-place a max 2000px; le miniature vanno in photos/thumbs/
  people/*       foto delle testimonianze (ridimensionate a max 640px)
  video.mp4      video opzionale; la copertina poster.jpg viene estratta con ffmpeg

Dipendenze: Pillow (pip install pillow); ffmpeg opzionale per i poster video.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "src" / "mobilities.json").read_text(encoding="utf-8"))
SITE = DATA["site"]
TYPES = DATA["types"]

PHOTO_MAX = 2000
THUMB_MAX = 720
PEOPLE_MAX = 640
JPEG_Q = 80

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
# Bandiere SVG semplificate (le emoji-bandiera non si vedono su Windows). viewBox 3x2.
_FLAG_SVG = {
    "PT": '<rect width="3" height="2" fill="#da291c"/><rect width="1.2" height="2" fill="#046a38"/>'
          '<circle cx="1.2" cy="1" r=".42" fill="#ffe900"/><circle cx="1.2" cy="1" r=".24" fill="#da291c"/>',
    "GR": '<rect width="3" height="2" fill="#0d5eaf"/>'
          + "".join(f'<rect y="{2*i/9:.3f}" width="3" height="{2/9:.3f}" fill="#fff"/>' for i in (1, 3, 5, 7))
          + '<rect width="1.111" height="1.111" fill="#0d5eaf"/>'
          '<rect x=".444" width=".222" height="1.111" fill="#fff"/><rect y=".444" width="1.111" height=".222" fill="#fff"/>',
    "IE": '<rect width="1" height="2" fill="#169b62"/><rect x="1" width="1" height="2" fill="#fff"/>'
          '<rect x="2" width="1" height="2" fill="#ff883e"/>',
    "ES": '<rect width="3" height="2" fill="#aa151b"/><rect y=".5" width="3" height="1" fill="#f1bf00"/>',
    "CZ": '<rect width="3" height="1" fill="#fff"/><rect y="1" width="3" height="1" fill="#d7141a"/>'
          '<path d="M0 0L1.5 1 0 2z" fill="#11457e"/>',
    "IT": '<rect width="1" height="2" fill="#009246"/><rect x="1" width="1" height="2" fill="#fff"/>'
          '<rect x="2" width="1" height="2" fill="#ce2b37"/>',
}


def flag(code: str) -> str:
    body = _FLAG_SVG.get(code)
    if not body:
        return ""
    return f'<svg class="flag" viewBox="0 0 3 2" aria-hidden="true">{body}</svg>'


class _Flags(dict):
    def get(self, code, default=""):  # compatibile con FLAGS.get(...)
        return flag(code) or default


FLAGS = _Flags()

e = html.escape


# --------------------------------------------------------------------------- media

def save_jpeg(im: Image.Image, path: Path) -> None:
    im.convert("RGB").save(path, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)


def fit(im: Image.Image, max_side: int) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    return im


def process_photos(slug: str) -> list[dict]:
    folder = ROOT / slug / "photos"
    thumbs = folder / "thumbs"
    thumbs.mkdir(exist_ok=True)
    out = []
    for src in sorted(folder.glob("*.jp*g")):
        with Image.open(src) as im:
            needs = max(im.size) > PHOTO_MAX or bool(im.getexif()) or src.suffix != ".jpg"
            if needs:
                im = fit(im, PHOTO_MAX)
                dst = src.with_suffix(".jpg")
                save_jpeg(im, dst)
                if dst != src:
                    src.unlink()
                src = dst
        thumb = thumbs / src.name
        if not thumb.exists() or thumb.stat().st_mtime < src.stat().st_mtime:
            with Image.open(src) as im:
                save_jpeg(fit(im, THUMB_MAX), thumb)
        with Image.open(src) as im:
            w, h = im.size
        with Image.open(thumb) as im:
            tw, th = im.size
        out.append({"file": src.name, "w": w, "h": h, "tw": tw, "th": th})
    return out


def process_people(slug: str) -> None:
    folder = ROOT / slug / "people"
    if not folder.exists():
        return
    for src in list(folder.iterdir()):
        if src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        with Image.open(src) as im:
            if max(im.size) <= PEOPLE_MAX and src.suffix == ".jpg" and not im.getexif():
                continue
            im = fit(im, PEOPLE_MAX)
            if im.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", im.size, "white")
                im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1])
                im = bg
            dst = src.with_suffix(".jpg")
            save_jpeg(im, dst)
            if dst != src:
                src.unlink()


def process_video(slug: str) -> dict | None:
    video = ROOT / slug / "video.mp4"
    if not video.exists():
        return None
    poster = ROOT / slug / "poster.jpg"
    if not poster.exists() and shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "3", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "4",
                        str(poster)], check=True)
    w, h = 16, 9
    if shutil.which("ffprobe"):
        res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=width,height", "-of", "csv=p=0",
                              str(video)], capture_output=True, text=True)
        try:
            w, h = (int(x) for x in res.stdout.strip().split(","))
        except ValueError:
            pass
    return {"poster": poster.exists(), "w": w, "h": h}


def person_photo(slug: str, name: str | None) -> str | None:
    if not name:
        return None
    stem = Path(name).stem
    for ext in (".jpg", ".jpeg", ".png"):
        if (ROOT / slug / "people" / f"{stem}{ext}").exists():
            return f"people/{stem}{ext}"
    raise FileNotFoundError(f"{slug}/people/{name}")


# --------------------------------------------------------------------------- helpers

def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def date_range(m: dict) -> str:
    a, b = d(m["start"]), d(m["end"])
    if a.year != b.year:
        return f"{a.day} {MONTHS[a.month-1]} {a.year} – {b.day} {MONTHS[b.month-1]} {b.year}"
    if a.month != b.month:
        return f"{a.day} {MONTHS[a.month-1]} – {b.day} {MONTHS[b.month-1]} {b.year}"
    return f"{a.day}–{b.day} {MONTHS[a.month-1]} {a.year}"


def short_range(m: dict) -> str:
    a, b = d(m["start"]), d(m["end"])
    return f"{a:%d.%m} → {b:%d.%m.%Y}"


def quote_html(text: str) -> str:
    out = e(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    return out.replace("\n", "<br>")


def initials(name: str) -> str:
    words = [w for w in re.split(r"[\s,]+", name)
             if w and not re.match(r"(?i)(prof|ins|dott|sig)", w) and not w.endswith(".")]
    return "".join(w[0] for w in words[-2:]).upper() or name[:1]


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


ICON = {
    "menu": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h10"/></svg>',
    "close": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    "prev": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>',
    "next": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>',
    "arrow": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    "back": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
    "photo": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-8 8"/></svg>',
    "play": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>',
    "quote": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h4v4c0 3-1.5 5-4 6M15 7h4v4c0 3-1.5 5-4 6"/></svg>',
    "mail": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
    "phone": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-6.2-7-11.5A7 7 0 0112 2.5a7 7 0 017 7C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
    "ext": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5"/></svg>',
}


# --------------------------------------------------------------------------- layout

def head(title: str, desc: str, prefix: str, canonical: str, og_image: str) -> str:
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#0b1d4a">
<meta property="og:type" content="website">
<meta property="og:locale" content="it_IT">
<meta property="og:site_name" content="{e(SITE['title'])}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{prefix}assets/img/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Instrument+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{prefix}assets/css/style.css?v={VERSION}">
<script src="{prefix}assets/js/main.js?v={VERSION}" defer></script>
</head>"""


def header(prefix: str, current: str | None, mobs: list[dict]) -> str:
    items = []
    for i, m in enumerate(mobs, 1):
        cur = ' aria-current="page"' if m["slug"] == current else ""
        items.append(f"""<li><a href="{prefix}{m['slug']}/"{cur}>
        <span class="menu-num">{i:02d}</span>
        <span class="menu-city">{e(m['city'])}</span>
        <span class="menu-meta">{e(TYPES[m['type']])} · {d(m['start']).strftime('%m/%Y')}</span>
      </a></li>""")
    home_cur = ' aria-current="page"' if current is None else ""
    return f"""<a class="skip" href="#main">Vai al contenuto</a>
<header class="site-header" data-header>
  <div class="wrap header-inner">
    <a class="brand" href="{prefix}"{home_cur}>
      <img src="{prefix}assets/img/erasmus-logo.png" alt="Erasmus+" width="640" height="249">
      <span class="brand-text"><strong>{e(SITE['school'])}</strong></span>
    </a>
    <button class="menu-btn" type="button" data-menu-open aria-haspopup="dialog">
      <span>Mobilità</span>{ICON['menu']}
    </button>
  </div>
</header>
<dialog class="menu" data-menu aria-label="Tutte le mobilità">
  <div class="menu-head">
    <a class="menu-home" href="{prefix}">{ICON['back']} Tutte le mobilità</a>
    <button class="icon-btn" type="button" data-menu-close aria-label="Chiudi menu">{ICON['close']}</button>
  </div>
  <nav aria-label="Mobilità"><ol class="menu-list">
      {''.join(items)}
  </ol></nav>
</dialog>"""


def footer(prefix: str, mobs: list[dict]) -> str:
    year = dt.date.today().year
    links = "".join(f'<li><a href="{e(l["url"])}" target="_blank" rel="noopener">{e(l["label"])}{ICON["ext"]}</a></li>'
                    for l in SITE["links"])
    cities = "".join(f'<li><a href="{prefix}{m["slug"]}/">{e(m["city"])}</a></li>' for m in mobs)
    tel = re.sub(r"\D", "", SITE["phone"])
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="footer-grid">
      <div class="footer-brand">
        <img src="{prefix}assets/img/erasmus-logo.png" alt="Erasmus+" width="640" height="249" loading="lazy">
        <p>{e(SITE['school'])}<br>Il diario delle nostre esperienze Erasmus+ in Europa.</p>
      </div>
      <div>
        <h2>Contatti</h2>
        <ul class="footer-contacts">
          <li>{ICON['mail']}<a href="mailto:{SITE['email']}">{SITE['email']}</a></li>
          <li>{ICON['phone']}<a href="tel:+39{tel}">{e(SITE['phone'])}</a></li>
          <li>{ICON['pin']}<span>{e(SITE['address'])}</span></li>
        </ul>
      </div>
      <div>
        <h2>Link utili</h2>
        <ul class="footer-links">{links}</ul>
      </div>
      <div>
        <h2>Mobilità</h2>
        <ul class="footer-cities">{cities}</ul>
      </div>
    </div>
    <div class="footer-bottom">
      <p>© {year} {e(SITE['school'])} · Progetto Erasmus+</p>
      <p class="credit">Design by <img src="{prefix}assets/img/11studio-white.png" alt="11 studio" width="480" height="79" loading="lazy"></p>
    </div>
  </div>
</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------- pages

def card(m: dict, i: int, prefix: str = "") -> str:
    cover = f"{prefix}{m['slug']}/photos/thumbs/{m['cover']}"
    stats = [plural(len(m["photos"]), "foto", "foto")]
    if m["video"]:
        stats.append("video")
    if m["testimonials"]:
        stats.append(plural(len(m["testimonials"]), "storia", "storie"))
    return f"""<li class="card reveal" data-type="{m['type']}">
  <a href="{prefix}{m['slug']}/">
    <figure class="card-media">
      <img src="{cover}" alt="" loading="lazy" decoding="async" width="{m['cover_dim'][0]}" height="{m['cover_dim'][1]}">
      <span class="stamp" aria-hidden="true"><span>{m['code']}</span><small>{d(m['start']).year}</small></span>
    </figure>
    <div class="card-body">
      <p class="card-num">{i:02d} · <span class="tag tag-{m['type']}">{e(TYPES[m['type']])}</span></p>
      <h3>{e(m['city'])}</h3>
      <p class="card-meta">{FLAGS.get(m['code'], '')} {e(m['country'])} · {date_range(m)}</p>
      <p class="card-stats">{' · '.join(stats)}<span class="card-go">{ICON['arrow']}</span></p>
    </div>
  </a>
</li>"""


def render_index(mobs: list[dict]) -> str:
    countries = len({m["country"] for m in mobs})
    photos = sum(len(m["photos"]) for m in mobs)
    stories = sum(len(m["testimonials"]) for m in mobs)
    collage_picks = [mobs[i] for i in (0, 3, 6, 7) if i < len(mobs)]
    collage = "".join(
        f'<img src="{m["slug"]}/photos/thumbs/{m["cover"]}" alt="" width="{m["cover_dim"][0]}" '
        f'height="{m["cover_dim"][1]}" class="c{k}" {"fetchpriority=high" if k == 0 else "loading=lazy"}>'
        for k, m in enumerate(collage_picks))

    by_year: dict[int, list] = {}
    for i, m in reversed(list(enumerate(mobs, 1))):  # dalla più recente
        by_year.setdefault(d(m["start"]).year, []).append(card(m, i))
    years = "".join(f"""<section class="year" data-year>
      <h3 class="year-label"><span>{y}</span></h3>
      <ol class="cards">{''.join(cs)}</ol>
    </section>""" for y, cs in sorted(by_year.items(), reverse=True))

    used = []
    for m in mobs:
        if m["type"] not in used:
            used.append(m["type"])
    chips = '<button type="button" class="chip" aria-pressed="true" data-filter="all">Tutte</button>' + "".join(
        f'<button type="button" class="chip" aria-pressed="false" data-filter="{t}">{e(TYPES[t])}</button>' for t in used)

    route = "".join(f'<li><a href="{m["slug"]}/">{flag(m["code"])}{e(m["city"])}</a></li>' for m in mobs)
    first, last = d(mobs[0]["start"]).year, d(mobs[-1]["start"]).year
    title = SITE["title"]
    return head(title, SITE["description"], "", SITE["base_url"], SITE["base_url"] + "assets/img/og.jpg") + f"""
<body class="page-home">
{header('', None, mobs)}
<main id="main">
  <section class="hero-home">
    <div class="wrap hero-home-grid">
      <div class="hero-home-text">
        <p class="eyebrow"><span class="dot"></span> Erasmus+ · {first}–{last}</p>
        <h1><mark>Una sola</mark><br>Europa.</h1>
        <p class="lead">{e(SITE['description'])}</p>
        <dl class="stats">
          <div><dt>Mobilità</dt><dd data-count="{len(mobs)}">{len(mobs)}</dd></div>
          <div><dt>Paesi</dt><dd data-count="{countries}">{countries}</dd></div>
          <div><dt>Foto</dt><dd data-count="{photos}">{photos}</dd></div>
          <div><dt>Storie</dt><dd data-count="{stories}">{stories}</dd></div>
        </dl>
        <a class="btn" href="#mobilita">Esplora le mobilità {ICON['arrow']}</a>
      </div>
      <div class="collage" aria-hidden="true">{collage}</div>
    </div>
    <div class="route" aria-label="Itinerario">
      <ol class="route-track">{route}{route.replace('<li>', '<li aria-hidden="true">').replace('<a ', '<a tabindex="-1" ')}</ol>
    </div>
  </section>

  <section class="section" id="mobilita" aria-labelledby="mob-title">
    <div class="wrap">
      <div class="section-head">
        <div>
          <p class="eyebrow">Il diario di bordo</p>
          <h2 id="mob-title">Le mobilità</h2>
        </div>
        <div class="chips" role="group" aria-label="Filtra per tipologia">{chips}</div>
      </div>
      {years}
      <p class="empty" data-empty hidden>Nessuna mobilità per questa tipologia.</p>
    </div>
  </section>

  <section class="about">
    <div class="wrap about-grid">
      <h2>Cos'è<br>Erasmus+?</h2>
      <div>
        <p>Erasmus+ è il programma dell'Unione Europea per l'istruzione, la formazione, la gioventù e lo sport. Grazie al progetto della nostra scuola, studenti e docenti partono per vivere la scuola di altri Paesi: lezioni condivise, job shadowing, corsi di formazione e famiglie ospitanti.</p>
        <p>Ogni viaggio torna a casa sotto forma di nuove competenze, nuove lingue e nuove amicizie. Qui raccogliamo foto, video e parole di chi è partito.</p>
        <a class="btn btn-dark" href="{e(SITE['links'][0]['url'])}" target="_blank" rel="noopener">Il progetto sul sito della scuola {ICON['ext']}</a>
      </div>
    </div>
  </section>
</main>
""" + footer("", mobs)


def render_city(m: dict, i: int, mobs: list[dict]) -> str:
    p = "../"
    canonical = f"{SITE['base_url']}{m['slug']}/"
    title = f"{m['city']} · {TYPES[m['type']]} · {SITE['title']}"
    desc = f"{TYPES[m['type']]} a {m['city']} ({m['country']}), {date_range(m)}. {m['intro']}"
    cover = m["cover"]

    gallery = "".join(
        f'<li><a href="photos/{ph["file"]}" data-lightbox data-w="{ph["w"]}" data-h="{ph["h"]}">'
        f'<img src="photos/thumbs/{ph["file"]}" alt="{e(m["city"])} — foto {k} di {len(m["photos"])}" '
        f'width="{ph["tw"]}" height="{ph["th"]}" loading="{'eager' if k <= 6 else 'lazy'}" decoding="async"></a></li>'
        for k, ph in enumerate(m["photos"], 1))

    video = ""
    if m["video"]:
        v = m["video"]
        poster = ' poster="poster.jpg"' if v["poster"] else ""
        orient = "portrait" if v["h"] > v["w"] else "landscape"
        video = f"""
  <section class="section video-section" aria-labelledby="video-title">
    <div class="wrap">
      <div class="section-head center">
        <p class="eyebrow">Il film del viaggio</p>
        <h2 id="video-title">Scopri l'esperienza</h2>
      </div>
      <div class="video-frame {orient} reveal" style="--ar:{v['w']}/{v['h']}">
        <video controls playsinline preload="none"{poster} width="{v['w']}" height="{v['h']}">
          <source src="video.mp4" type="video/mp4">
          Il tuo browser non supporta i video HTML5. <a href="video.mp4">Scarica il video</a>.
        </video>
      </div>
    </div>
  </section>"""

    stories = ""
    if m["testimonials"]:
        items = []
        for t in m["testimonials"]:
            ph = person_photo(m["slug"], t.get("photo"))
            avatar = (f'<img src="{ph}" alt="{e(t["name"])}" loading="lazy" decoding="async">' if ph
                      else f'<span class="avatar-fallback" aria-hidden="true">{e(initials(t["name"]))}</span>')
            long_cls = " long" if len(t["quote"]) > 320 else ""
            items.append(f"""<li class="story reveal">
        <figure>
          <div class="story-photo">{avatar}<span class="story-mark">{ICON['quote']}</span></div>
          <div class="story-text">
            <blockquote class="{long_cls.strip()}"><p>{quote_html(t['quote'])}</p></blockquote>
            <figcaption>{e(t['name'])}</figcaption>
          </div>
        </figure>
      </li>""")
        stories = f"""
  <section class="section stories" aria-labelledby="stories-title">
    <div class="wrap">
      <div class="section-head">
        <div>
          <p class="eyebrow">Testimonianze</p>
          <h2 id="stories-title">Le loro storie</h2>
        </div>
      </div>
      <ul class="story-list">{''.join(items)}</ul>
    </div>
  </section>"""

    prev_m = mobs[i - 2] if i > 1 else None
    next_m = mobs[i] if i < len(mobs) else None

    def pn(x: dict | None, label: str, cls: str) -> str:
        if not x:
            return f'<a class="pn {cls} pn-home" href="../"><span class="pn-label">{label}</span><span class="pn-city">Tutte le mobilità</span></a>'
        return (f'<a class="pn {cls}" href="../{x["slug"]}/">'
                f'<img src="../{x["slug"]}/photos/thumbs/{x["cover"]}" alt="" loading="lazy">'
                f'<span class="pn-label">{label}</span><span class="pn-city">{e(x["city"])}</span>'
                f'<span class="pn-meta">{date_range(x)}</span></a>')

    nav_counts = [plural(len(m["photos"]), "foto", "foto")]
    if m["video"]:
        nav_counts.append("1 video")
    if m["testimonials"]:
        nav_counts.append(plural(len(m["testimonials"]), "storia", "storie"))

    return head(title, desc, p, canonical, f"{canonical}photos/{cover}") + f"""
<body class="page-city">
{header(p, m['slug'], mobs)}
<main id="main">
  <section class="hero-city">
    <img class="hero-bg" src="photos/{cover}" alt="" fetchpriority="high" decoding="async">
    <div class="wrap hero-city-inner">
      <nav class="crumbs" aria-label="Percorso"><a href="../">Mobilità</a><span aria-hidden="true">/</span><span>{i:02d} di {len(mobs):02d}</span></nav>
      <p class="tag tag-{m['type']}">{e(TYPES[m['type']])}</p>
      <h1>{e(m['city'])}</h1>
      <p class="hero-meta"><span>{FLAGS.get(m['code'], '')} {e(m['country'])}</span><span>{date_range(m)}</span></p>
      <p class="hero-intro">{e(m['intro'])}</p>
      <p class="hero-counts">{' · '.join(nav_counts)}</p>
    </div>
  </section>

  <section class="section gallery-section" aria-labelledby="gallery-title">
    <div class="wrap">
      <div class="section-head">
        <div>
          <p class="eyebrow">{ICON['photo']} {len(m['photos'])} scatti</p>
          <h2 id="gallery-title">Galleria</h2>
        </div>
        <p class="hint">Tocca una foto per ingrandirla</p>
      </div>
      <ul class="gallery">{gallery}</ul>
    </div>
  </section>
{video}{stories}

  <nav class="wrap prevnext" aria-label="Altre mobilità">
    {pn(prev_m, '← Precedente', 'pn-prev')}
    {pn(next_m, 'Successiva →', 'pn-next')}
  </nav>
</main>

<dialog class="lightbox" data-lightbox-dialog aria-label="Visualizzatore foto">
  <figure><img alt="" data-lb-img><figcaption data-lb-caption></figcaption></figure>
  <button class="icon-btn lb-close" type="button" data-lb-close aria-label="Chiudi">{ICON['close']}</button>
  <button class="icon-btn lb-prev" type="button" data-lb-prev aria-label="Foto precedente">{ICON['prev']}</button>
  <button class="icon-btn lb-next" type="button" data-lb-next aria-label="Foto successiva">{ICON['next']}</button>
</dialog>
""" + footer(p, mobs)


def render_404(mobs: list[dict]) -> str:
    base = SITE["base_url"]
    prefix = "/" + base.split("://", 1)[1].split("/", 1)[1]  # /erasmus-programme/
    return head(f"Pagina non trovata · {SITE['title']}", SITE["description"], prefix, base,
                base + "assets/img/og.jpg").replace("<head>", '<head>\n<meta name="robots" content="noindex">') + f"""
<body class="page-404">
{header(prefix, '', mobs)}
<main id="main" class="wrap notfound">
  <p class="eyebrow">Errore 404</p>
  <h1>Destinazione<br><mark>non trovata</mark>.</h1>
  <p class="lead">Questa pagina non esiste o è stata spostata. Scegli una delle nostre mobilità:</p>
  <ol class="cards">{''.join(card(m, k, prefix) for k, m in enumerate(mobs, 1))}</ol>
</main>
""" + footer(prefix, mobs)


def render_redirect(m: dict) -> str:
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=../{m['slug']}/">
<link rel="canonical" href="{SITE['base_url']}{m['slug']}/">
<title>{e(m['city'])} · {e(SITE['title'])}</title>
</head>
<body>
<p><a href="../{m['slug']}/">Vai alla mobilità di {e(m['city'])}</a></p>
</body>
</html>
"""


def make_og(mobs: list[dict]) -> None:
    out = ROOT / "assets" / "img" / "og.jpg"
    W, H = 1200, 630
    canvas = Image.new("RGB", (W, H), (11, 29, 74))
    picks = mobs[:6] if len(mobs) >= 6 else mobs
    cols = 3
    rows = max(1, (len(picks) + cols - 1) // cols)
    cw, ch = W // cols, H // rows
    for k, m in enumerate(picks):
        with Image.open(ROOT / m["slug"] / "photos" / "thumbs" / m["cover"]) as im:
            tile = ImageOps.fit(im.convert("RGB"), (cw - 6, ch - 6))
        canvas.paste(tile, ((k % cols) * cw + 3, (k // cols) * ch + 3))
    logo_p = ROOT / "assets" / "img" / "erasmus-logo.png"
    with Image.open(logo_p) as logo:
        logo = logo.convert("RGBA")
        logo.thumbnail((440, 200))
        badge = Image.new("RGBA", (logo.width + 60, logo.height + 50), (255, 255, 255, 255))
        badge.paste(logo, (30, 25), logo)
        canvas.paste(badge.convert("RGB"), ((W - badge.width) // 2, (H - badge.height) // 2))
    save_jpeg(canvas, out)


# --------------------------------------------------------------------------- main

VERSION = dt.date.today().strftime("%Y%m%d")


def main() -> None:
    mobs = sorted(DATA["mobilities"], key=lambda m: m["start"])
    for m in mobs:
        slug = m["slug"]
        m["photos"] = process_photos(slug)
        if not m["photos"]:
            raise SystemExit(f"{slug}: nessuna foto in {slug}/photos/")
        names = [p["file"] for p in m["photos"]]
        if m.get("cover") not in names:
            m["cover"] = names[0]
        ph = next(p for p in m["photos"] if p["file"] == m["cover"])
        m["cover_dim"] = (ph["tw"], ph["th"])
        process_people(slug)
        m["video"] = process_video(slug)
        print(f"  {slug:14} {len(names):3} foto  video={'sì' if m['video'] else 'no'}  storie={len(m['testimonials'])}")

    for i, m in enumerate(mobs, 1):
        (ROOT / m["slug"] / "index.html").write_text(render_city(m, i, mobs), encoding="utf-8")
        (ROOT / "redirect").mkdir(exist_ok=True)
        (ROOT / "redirect" / f"{m['slug']}.html").write_text(render_redirect(m), encoding="utf-8")

    (ROOT / "index.html").write_text(render_index(mobs), encoding="utf-8")
    (ROOT / "404.html").write_text(render_404(mobs), encoding="utf-8")
    make_og(mobs)

    urls = [SITE["base_url"]] + [f"{SITE['base_url']}{m['slug']}/" for m in mobs]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE['base_url']}sitemap.xml\n",
                                     encoding="utf-8")
    (ROOT / ".nojekyll").touch()
    print("Fatto.")


if __name__ == "__main__":
    main()
