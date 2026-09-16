#!/usr/bin/env python3
"""Rebuild ddrnorway.no (2007 design) as a static site.

Inputs (raw/): Wayback Machine snapshots of ddrnorway.no pages + assets, and
ccbs.sesse.net (the Challenge Cup score system) pages for results.
Output: docs/  (plain HTML, GitHub Pages friendly).
"""
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, unquote

ROOT = Path(__file__).parent
RAW = ROOT / 'raw'
OUT = ROOT / 'docs'
SUB = {'forum': 'forum.html', 'gallery': 'galleri.html', 'multimedia': 'galleri.html', 'wiki': 'leksikon.html',
       'webshop': 'webshop.html', 'pgshop': 'webshop.html', 'cp': 'cp.html'}

START = '<td valign="top" bgcolor="#FFFFFF" style="padding: 8px 3px 10px 3px;">'
END = '<td width="12" bgcolor="#0C59A9">&nbsp;</td>'
DASH = ('<br><table width="350" height="1" align="center"><tr>'
        '<td width="350" height="1" background="img/dashline.gif"></td></tr></table><br>\n')


def read(p):
    return Path(p).read_bytes().decode('cp1252', 'replace')


def read8(p):
    return Path(p).read_text('utf-8', 'replace')


# ---------------------------------------------------------------- URLs
LOCAL = set()   # html files we emit (filled before rendering)


def page_name(qs):
    """'id=ircquote&top' -> 'ircquote_top', 'id=omtaler&omtale=x' -> 'omtaler_omtale_x'"""
    parts = []
    for k, v in parse_qsl(qs, keep_blank_values=True):
        if k == 'id':
            parts.insert(0, v)
        elif v == '':
            parts.append(k)
        else:
            parts.append(f'{k}_{v}')
    return '_'.join(p for p in parts if p)


def fix_url(u):
    u = u.strip()
    if not u or u.startswith(('#', 'mailto:', 'javascript:')):
        return u
    if u.startswith('mailtp:'):
        return 'mailto:' + u[7:]
    if re.search(r'%20(at|AT)%20', u):
        return 'mailto:' + re.sub(r'%20(at|AT)%20', '@', re.sub(r'%20(dot|DOT)%20', '.', u))
    if 'ineptia.net' in u:
        return 'irc.html'
    u = re.sub(r'^https?://(www\.)?ddrnorway\.no(:80)?/?', '', u)
    if u.startswith(('http://', 'https://')):
        return u
    u = u.lstrip('/')
    while u.startswith('../'):
        u = u[3:]
    m = re.match(r'^wiki/index\.php\?title=([^&#]+)', u)
    if m:
        return wiki_page(unquote(m.group(1)))
    m = re.match(r'^(forum|gallery|wiki|webshop|multimedia|cp|pgshop)(/|$)', u)
    if m:
        return SUB[m.group(1)]
    if u in ('', 'index.php'):
        return 'index.html'
    m = re.match(r'^(?:index\.php)?\?(.*)$', u)
    if m:
        name = page_name(m.group(1))
        for cand in (name, name.split('_')[0]):
            if cand + '.html' in LOCAL:
                return cand + '.html'
        return '404.html'
    return u


def wiki_page(title):
    if title == 'Hovedside':
        return 'leksikon.html'
    return 'leksikon_' + re.sub(r'[^A-Za-z0-9_-]', '_', title) + '.html'


def wiki_content(s):
    i = s.index('<!-- start content -->') + len('<!-- start content -->')
    j = s.index('<!-- end content -->')
    c = s[i:j]
    c = re.sub(r'<div class="editsection".*?</div>', '', c, flags=re.S)
    c = re.sub(r'<div class="printfooter">.*?</div>', '', c, flags=re.S)
    c = re.sub(r'<div id="catlinks">.*?</div>', '', c, flags=re.S)
    c = re.sub(r"<span class='urlexpansion'>.*?</span>", '', c, flags=re.S)
    return f'<div class="wiki">{c}</div>'


def gallery(pages):
    """Rebuild the 4images photo gallery from archived category/detail pages + media files."""
    MM = RAW / 'multimedia'
    if not (MM / 'index.html').exists():
        return
    idx = read(MM / 'index.html')
    cats = {}
    for cid, name, count, desc in re.findall(
            r'categories\.php\?cat_id=(\d+)&amp;sessionid=\w+" class="maincat">([^<]+)</a>&nbsp;\((\d+)\)(?:.*?)<span class="smalltext">(.*?)</span>', idx, re.S):
        cats[int(cid)] = dict(name=html.unescape(name).strip(), count=int(count), desc=html.unescape(re.sub(r'<[^>]+>', '', desc)).strip(), images=[])
    photos = {}
    for p in MM.glob('details.php_image_id_*'):
        d = read(p)
        iid = int(p.name.rsplit('_', 1)[1])
        media = re.search(r'src="\./(data/media/(\d+)/[^"]+)"', d)
        cat = media and re.match(r'.*/media/(\d+)/', media.group(1))
        title = re.search(r'<title>[^<]*?-\s*([^<]*)</title>', d)
        if not title:
            title = re.search(r'<b class="title">([^<]+)</b>', d)
        text = html.unescape(re.sub(r'<[^>]+>', '\n', re.sub(r'<script.*?</script>|<style.*?</style>', '', d, flags=re.S)))
        text = re.sub(r'\n\s*\n+', '\n', text)
        field = lambda k: (re.search(k + r':\s*\n?\s*([^\n]+)', text) or [None, ''])[1].strip()
        if not media or not (MM / media.group(1)).exists():
            continue
        photos[iid] = dict(id=iid, cat=int(cat.group(1)) if cat else 0, media=media.group(1),
                           title=html.unescape(title.group(1)).strip() if title else f'Bilde {iid}',
                           desc=field('Description'), date=field('Date'), by=field('Added by'))
    for p in MM.glob('categories.php_cat_id_*'):
        c = read(p)
        cid = int(p.name.rsplit('_', 1)[1])
        name = re.search(r'<b class="title">([^<]+)</b>', c)
        desc = re.search(r'</table>\s*<br />\s*([^<(]*?)\s*\(Hits: \d+\)', c)
        crumbs = re.findall(r'categories\.php\?cat_id=(\d+)&amp;sessionid=\w+" class="clickstream">([^<]+)</a>', c)
        cat = cats.setdefault(cid, dict(name='', count=0, desc='', images=[]))
        if name:
            cat['name'] = html.unescape(name.group(1)).strip()
        if desc and desc.group(1).strip():
            cat['desc'] = html.unescape(desc.group(1)).strip()
        if crumbs:
            cat['parent'] = html.unescape(crumbs[-1][1]).strip()
        for iid, thumb, t in re.findall(r'details\.php\?image_id=(\d+)&amp;sessionid=\w+"><img src="\./(data/thumbnails/[^"]+)"[^>]*alt="([^"]*)"', c):
            iid = int(iid)
            if iid in photos:
                photos[iid]['cat'] = photos[iid]['cat'] or cid
                if (MM / thumb).exists():
                    photos[iid]['thumb'] = thumb
    # photos whose detail page was not archived: use folder (=category) and file name
    known = {ph['media'] for ph in photos.values()}
    nid = 100000
    for f in sorted(MM.glob('data/media/*/*')) + sorted(MM.glob('data/thumbnails/*/*')):
        rel = str(f.relative_to(MM))
        if rel in known or f.suffix.lower() not in ('.jpg', '.jpeg', '.gif', '.png'):
            continue
        if 'thumbnails' in rel and any(k.endswith('/' + f.name) for k in known):
            continue   # thumbnail of a photo we already have in full size
        known.add(rel)
        nid += 1
        title = re.sub(r'[_-]+', ' ', f.stem).strip()
        photos[nid] = dict(id=nid, cat=int(f.parent.name), media=rel, title=title, desc='', date='', by='')
    for ph in photos.values():
        cats.setdefault(ph['cat'], dict(name='Diverse', count=0, desc='', images=[]))['images'].append(ph)
    body = '<p><br>Bilder fra DDR Norway-milj&oslash;et: medlemmer, treff og turneringer.</p><ul>'
    for cid, cat in sorted(cats.items(), key=lambda kv: (kv[1].get('parent', ''), kv[1]['name'])):
        if not cat['images']:
            continue
        parent = f'{html.escape(cat["parent"])} / ' if cat.get('parent') else ''
        body += (f'<li>{parent}<b><a href="galleri_{cid}.html">{html.escape(cat["name"])}</a></b> ({len(cat["images"])} bilder)'
                 f'<br><span style="font-size:10px;color:#666">{html.escape(cat["desc"])}</span></li>')
        grid = '<p><a href="galleri.html">&laquo; Tilbake til galleriet</a></p><table width="100%"><tr>'
        for n, ph in enumerate(sorted(cat['images'], key=lambda x: x['id'])):
            src = ph.get('thumb', ph['media'])
            grid += (f'<td align="center" valign="top" width="25%"><a href="bilde_{ph["id"]}.html">'
                     f'<img src="bilder/{src}" width="100" border="1" alt="{html.escape(ph["title"])}"></a><br>'
                     f'<span style="font-size:10px">{html.escape(ph["title"])}</span></td>')
            if n % 4 == 3:
                grid += '</tr><tr>'
            info = ''.join(f'<b>{k}:</b> {html.escape(v)}<br>' for k, v in
                           (('Beskrivelse', ph['desc']), ('Dato', ph['date']), ('Lagt til av', ph['by'])) if v)
            pages[f'bilde_{ph["id"]}'] = (f'DDR Norway - {ph["title"]}', section(html.escape(ph['title']),
                f'<p><a href="galleri_{cid}.html">&laquo; {html.escape(cat["name"])}</a></p>'
                f'<p align="center"><img src="bilder/{ph["media"]}" style="max-width:100%" border="1" alt="{html.escape(ph["title"])}"></p><p>{info}</p>'))
        pages[f'galleri_{cid}'] = (f'DDR Norway - {cat["name"]}', section(html.escape(cat['name']), grid + '</tr></table>'))
    pages['galleri'] = ('DDR Norway - Galleri', section('DDR arkiv', body + '</ul>'))
    (OUT / 'bilder').mkdir(exist_ok=True)
    for ph in photos.values():
        for f in (ph['media'], ph.get('thumb')):
            if f:
                (OUT / 'bilder' / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(MM / f, OUT / 'bilder' / f)


def fix_links(s):
    s = re.sub(r'''(href|src|background|action)=(["']?)([^"' >]+)''',
               lambda m: f'{m.group(1)}={m.group(2)}{fix_url(m.group(3))}', s, flags=re.I)
    s = re.sub(r"parent\.location='([^']*)'",
               lambda m: f"parent.location='{fix_url(m.group(1))}'", s)
    return s


def dewayback(s):
    """Strip Wayback Machine rewriting from a snapshot (fallback if no raw copy)."""
    s = re.sub(r'(https?://web\.archive\.org)?/web/\d+[a-z_]*/', '', s)
    s = re.sub(r'<script src="https://web-static[^\n]*\n.*?<!-- End Wayback Rewrite JS Include -->', '', s, flags=re.S)
    s = re.sub(r'<!-- BEGIN WAYBACK TOOLBAR INSERT -->.*?<!-- END WAYBACK TOOLBAR INSERT -->', '', s, flags=re.S)
    s = re.sub(r'<!--\s*FILE ARCHIVED ON.*$', '', s, flags=re.S)
    return s


# ---------------------------------------------------------------- content
def find_block(s, start, open_tag='<table', close_tag='</table>'):
    """Return (i, j) of a nesting-aware element starting at s[start:]."""
    depth = 0
    pos = start
    while True:
        o = s.find(open_tag, pos)
        c = s.find(close_tag, pos)
        if c == -1:
            return start, len(s)
        if o != -1 and o < c:
            depth += 1
            pos = o + len(open_tag)
        else:
            depth -= 1
            pos = c + len(close_tag)
            if depth == 0:
                return start, pos


def strip_countdown(c):
    c = c.replace('<!-- Nedtellings-table -->', '')
    while True:
        m = re.search(r'<table width="500"[^>]*#FF3300;">', c)
        if not m:
            return c
        i, j = find_block(c, m.start())
        c = c[:i] + c[j:]


EMO = {':happy:': ':)', ';)': ';)', ':P': ':P', ':D': ':D', ':)': ':)', ':(': ':('}


def clean_embedded(c):
    """Some pages embed a whole <html> document inside the content cell."""
    # forum emoticon images were never archived; fall back to the text code
    c = re.sub(r'<!--emo&(.*?)--><img[^>]*><!--endemo-->', lambda m: EMO.get(m.group(1), m.group(1)), c, flags=re.S)
    c = re.sub(r'<!DOCTYPE[^>]*>', '', c, flags=re.I)
    c = re.sub(r'<head>.*?</head>', '', c, flags=re.S | re.I)
    c = re.sub(r'</?(html|body)[^>]*>', '', c, flags=re.I)
    return c


def content_of(s):
    i = s.index(START) + len(START)
    j = s.index(END, i)
    c = s[i:j]
    c = c[:c.rstrip().rfind('</td>')]
    return clean_embedded(strip_countdown(c))


def title_of(c, default='DDR Norway'):
    m = re.search(r'class="topstory_title"[^>]*>\s*(.*?)\s*</td>', c, flags=re.S)
    if not m:
        return default
    t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    return f'DDR Norway - {html.unescape(t)}' if t else default


def section(title, body):
    return (f'<table width="100%" border="0" cellspacing="0" cellpadding="0">\n'
            f'<tr><td align="left" class="topstory_title" valign="top">{title}</td></tr>\n'
            f'<tr><td align="left" class="topstory_text" style="padding-left: 25px;" valign="top">\n'
            f'{body}\n</td></tr></table>\n')


PLAYER_BY_NICK = {}


def author_links(c):
    def sub(m):
        nick = m.group(1).strip()
        pid = PLAYER_BY_NICK.get(nick.lower())
        return f'<a href="spiller_{pid}.html">{nick}</a>' if pid else nick
    return re.sub(r'''<a href=['"][^'"]*forum/index\.php\?(?:act=Profile|showuser)[^'"]*['"]>([^<]+)</a>''', sub, c)


def news_posts(s):
    """Extract forum-news blocks (title, html) in page order."""
    out = []
    for m in re.finditer(r'<table cellpadding=.4. border=.0. width=.100%. style=.font-family:Verdana;font-size:11px.>', s):
        i, j = find_block(s, m.start())
        block = s[i:j]
        t = re.search(r'<b>(.*?)</b>', block, flags=re.S)
        out.append((html.unescape(re.sub(r'<[^>]+>', '', t.group(1))).strip() if t else '', block))
    return out


def drop_dead(s, base):
    """Images that were never archived are removed; other dead local links go to the archive."""
    def exists(u):
        return (base / u.split('#')[0].split('?')[0].replace('%20', ' ')).exists()

    def img(m):
        src = re.search(r'src=["\']?([^"\' >]+)', m.group(0))
        return '' if src and not src.group(1).startswith('http') and not exists(src.group(1)) else m.group(0)
    s = re.sub(r'<img[^>]*>', img, s, flags=re.I)

    def anchor(m):
        u = m.group(1)
        if u.startswith(('http', 'mailto:', 'javascript:', '#')) or exists(u):
            return m.group(0)
        return m.group(2)
    return re.sub(r'<a\b[^>]*href=["\']?([^"\' >]+)["\']?[^>]*>(.*?)</a>', anchor, s, flags=re.I | re.S)


# ---------------------------------------------------------------- ccbs (sesse.net)
def scope_css(css, scope='.ccbs'):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []
    for m in re.finditer(r'([^{}]+)\{([^}]*)\}', css):
        sels = [x.strip() for x in m.group(1).split(',') if x.strip() and x.strip() != '*']
        sels = [scope if x == 'body' else f'{scope} {x}' for x in sels]
        if sels:
            out.append(', '.join(sels) + ' {' + m.group(2) + '}')
    out.append(f'{scope} .main {{ margin-left: 0; }} {scope} table {{ margin-left: 0.5em; }} '
               f'{scope} h2 {{ font-size: 14px; }} {scope} ul {{ padding-left: 1.5em; }} '
               f'{scope}, {scope} table {{ font-family: Verdana, Arial, Helvetica, sans-serif; }} '
               f'{scope} table {{ font-size: 10px; }} {scope} th, {scope} td {{ padding: 1px 3px; }}')
    return '\n'.join(out)


def ccbs_main(s):
    i = s.index('<div class="main">') + len('<div class="main">')
    j = s.rindex('</div>', 0, s.index('</body>'))
    c = s[i:j]
    c = re.sub(r'<form[^>]*>|</form>|<input[^>]*>', '', c)
    c = re.sub(r'<p class="button">.*?</p>', '', c, flags=re.S)
    c = re.sub(r'href="player\.pl\?id=(\d+)"', r'href="spiller_\1.html"', c)
    c = re.sub(r'href="show-tournament\.pl\?id=(\d+)"', r'href="turnering_\1.html"', c)
    c = re.sub(r'href="song\.pl\?id=(\d+)"', r'href="sanger.html#s_\1"', c)
    c = re.sub(r'href="songratings\.pl[^"]*"', 'href="sanger.html"', c)
    c = re.sub(r'href="(players|tournaments|songs)\.pl"',
               lambda m: {'players': 'spillere', 'tournaments': 'resultater', 'songs': 'sanger'}[m.group(1)] + '.html', c)
    return f'<div class="ccbs"><div class="main">{c}</div></div>'


# ---------------------------------------------------------------- images
def make_missing_images(img):
    from PIL import Image, ImageDraw, ImageFont
    blue, yellow, white, red = (12, 89, 169), (248, 196, 18), (255, 255, 255), (220, 30, 30)

    def font(size, name='Arial Black.ttf'):
        for p in (f'/System/Library/Fonts/Supplemental/{name}', f'/Library/Fonts/{name}'):
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        return ImageFont.load_default()

    def save(name, im):
        p = img / name
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            im.save(p)

    # ponytail: the header middle band (topp_02..07) was never archived; this is a stand-in.
    if not (img / 'topp/topp_02.gif').exists():
        band = Image.new('RGB', (742, 177), blue)
        d = ImageDraw.Draw(band)
        d.text((30, 40), 'DDR Norway', font=font(44), fill=white)
        d.text((32, 100), 'Norges største DDR-samfunn', font=font(15, 'Arial Bold.ttf'), fill=yellow)
        # simple down-arrow continuing the logo column (x 286..412)
        cx = 349
        d.polygon([(cx - 40, 10), (cx + 40, 10), (cx, 80)], fill=white)
        d.polygon([(cx - 28, 14), (cx + 28, 14), (cx, 64)], fill=red)
        cells = {'topp_02': (0, 0, 286, 42), 'topp_03': (286, 0, 412, 42), 'topp_04': (412, 0, 742, 42),
                 'topp_05': (0, 42, 286, 177), 'topp_06': (286, 42, 412, 177), 'topp_07': (412, 42, 742, 177)}
        for name, box in cells.items():
            save(f'topp/{name}.gif', band.crop(box).convert('P', palette=Image.ADAPTIVE))
    save('bg_top.gif', Image.new('RGB', (4, 27), blue))
    save('mnu_bg.gif', Image.new('RGB', (53, 4), yellow))
    save('mnu_bg2.gif', Image.new('RGB', (4, 4), white))
    dash = Image.new('RGB', (350, 1), white)
    for x in range(0, 350, 4):
        dash.putpixel((x, 0), (170, 170, 170)); dash.putpixel((x + 1, 0), (170, 170, 170))
    save('dashline.gif', dash)
    if (img / 'storytop_title.gif').exists() and not (img / 'story_title.gif').exists():
        shutil.copy(img / 'storytop_title.gif', img / 'story_title.gif')
    for name, label in (('stars/wiki.gif', 'wiki'),):
        if not (img / name).exists():
            star = Image.new('RGBA', (100, 104), (0, 0, 0, 0))
            d = ImageDraw.Draw(star)
            import math
            pts = [(50 + (45 if k % 2 == 0 else 20) * math.cos(math.radians(-90 + k * 36)),
                    52 + (45 if k % 2 == 0 else 20) * math.sin(math.radians(-90 + k * 36))) for k in range(10)]
            d.polygon(pts, fill=(240, 60, 60), outline=(180, 20, 20))
            d.text((50, 52), label, font=font(16, 'Arial Bold.ttf'), fill=white, anchor='mm')
            save(name, star.convert('P', palette=Image.ADAPTIVE))


# ---------------------------------------------------------------- build
def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for d in ('img', 'style_emoticons', 'docs'):
        if (RAW / 'assets' / d).exists():
            shutil.copytree(RAW / 'assets' / d, OUT / d)
    for f in ('favicon.ico', 'style.css'):
        shutil.copy(RAW / 'assets' / f, OUT / f)
    make_missing_images(OUT / 'img')
    (OUT / 'style.css').write_text(
        (RAW / 'assets/style.css').read_text() + '\n\n/* ccbs (results system) */\n' +
        scope_css(read8(RAW / 'ccbs/ccbs.css')) +
        '\n.quote { font-family: monospace; font-size: 11px; padding: 4px 0; }\n'
        '.board { border: 1px solid #B2B2B2; margin-bottom: 4px; } .board th { background: #0C59A9; color: #fff; text-align: left; }\n'
        '.board tr.hdr td { background: #F8C412; font-weight: bold; } .board td { border-bottom: 1px solid #E6E6E6; vertical-align: top; }\n'
        '.board .desc { font-size: 10px; color: #666; } .board .mod { font-size: 10px; color: #0C59A9; }\n'
        '.wiki h2 { font-size: 14px; border-bottom: 1px solid #B2B2B2; } .wiki h3 { font-size: 12px; } .wiki table { font-size: 11px; }\n')

    # ---- template from the 2007 front page
    src = RAW / 'pages/index2007.html'
    tpl = read(src) if src.exists() else dewayback(read(RAW / 'index.html'))
    i = tpl.index(START) + len(START)
    j = tpl.rindex('</td>', 0, tpl.index(END, i))
    front = strip_countdown(tpl[i:j])
    tpl = tpl[:i] + '{{CONTENT}}' + tpl[j:]
    tpl = tpl.replace('charset=iso-8859-1', 'charset=utf-8')
    tpl = tpl.replace('<title>DDR Norway</title>', '<title>{{TITLE}}</title>')
    tpl = tpl.replace("'http://www.positivegaming.com/score/'", "'resultater.html'")
    tpl = tpl.replace('"http://www.positivegaming.com/score/"', '"resultater.html"')

    pages = {}   # name -> (title, content html)
    players = json.load(open(RAW / 'ccbs/players.json'))
    PLAYER_BY_NICK.update({pl['nick'].lower(): pl['id'] for pl in players})

    # ---- archived content pages
    skip = {'index_shtml', 'irc_index_shtml', 'kontakt_shtml', 'linker_shtml', 'regler_shtml',
            'steder_shtml', 'omoss_shtml', 'medlem_', 'novsuk_', 'summertour2004_', 'press_',
            '404', '404.php', 'klubb_ddrhardcore', 'ircquote_', 'ircquote_browse', 'ircquote_top',
            'ircquote_latest', 'ircquote_random', 'index2007', 'index2006'}
    for p in sorted((RAW / 'pages').glob('*.html')):
        name = p.stem
        if name in skip or name.startswith('nm05_'):
            continue
        s = read(p)
        if START not in s:
            continue
        c = content_of(s)
        pages[name] = (title_of(c), c)

    # ---- front page + merged news
    pages['index'] = ('DDR Norway', front)
    seen, posts = set(), []
    for name in ('index2007', 'klubb_ddrhardcore', '404', 'nyheter'):
        p = RAW / 'pages' / f'{name}.html'
        if not p.exists():
            continue
        for t, block in news_posts(read(p)):
            if t and t not in seen:
                seen.add(t); posts.append(block)
    pages['nyheter'] = ('DDR Norway - Nyheter', section('Nyheter', '<br>' + DASH.join(posts)))

    # ---- DDR Hardcore club page (its capture was really a front page)
    pages['klubb_ddrhardcore'] = ('DDR Norway - DDR Hardcore', section('Bli medlem', '''
<p><strong>DDR Hardcore</strong></p>
<blockquote><p><img src="img/Klubber/DDRHardcore-banner.jpg" alt="DDR Hardcore" border="1"></p></blockquote>
<p>Lokalisasjon: Oslo<br>Klubben for de mest aktive spillerne i Oslo-omr&aring;det, med flest deltakere i Challenge Cup.</p>
<p>Se <a href="spillere.html">spilleroversikten</a> for medlemmer og resultater.</p>'''))

    # ---- 404
    pages['404'] = ('DDR Norway - Siden finnes ikke', section('Siden finnes ikke',
                    '<p>Beklager, siden du lette etter finnes ikke. G&aring; til <a href="index.html">hovedsiden</a>.</p>'))

    # ---- IRC quotes (rebuilt from the captured lists)
    quotes = {}
    for name in ('ircquote_browse', 'ircquote_top', 'ircquote_latest', 'ircquote_random'):
        p = RAW / 'pages' / f'{name}.html'
        if p.exists():
            for qid, score, body in re.findall(
                    r"q=(\d+)'>\d+</a> -\s*Poeng: <a[^>]*>\[\+\]</a> (-?\d+) <a[^>]*>\[-\]</a></b><br>\s*<div id='quote'>(.*?)</div>",
                    read(p), flags=re.S):
                quotes[int(qid)] = (int(score), body.strip())
    nav = ('<div align="left"><img src="img/reviews/arrow_filled.png" width="15" height="15">&nbsp;&nbsp; '
           '<a href="ircquote.html">hjem</a> / <a href="ircquote_latest.html">siste</a> / '
           '<a href="ircquote_browse.html">bla gjennom</a> / <a href="ircquote_random.html">tilfeldig sitat</a> / '
           '<a href="ircquote_top.html">topp 20</a> / <a href="ircquote_add.html">legg til</a> / '
           '<a href="ircquote_search.html">s&oslash;k</a></div><br><br>\n')

    def qblock(qid):
        score, body = quotes[qid]
        return f'#<b>{qid}</b> - <b>Poeng: {score}</b><br><div class="quote">{body}</div><hr>\n'

    qt = ' IRC Quotes fra #DDRNorway '
    pages['ircquote_browse'] = ('DDR Norway - IRC Quotes', section(qt, nav + ''.join(qblock(q) for q in sorted(quotes))))
    pages['ircquote_latest'] = ('DDR Norway - IRC Quotes', section(qt, nav + ''.join(qblock(q) for q in sorted(quotes, reverse=True)[:10])))
    pages['ircquote_top'] = ('DDR Norway - IRC Quotes', section(qt, nav + ''.join(
        qblock(q) for q in sorted(quotes, key=lambda q: -quotes[q][0])[:20])))
    qjson = json.dumps([qblock(q) for q in sorted(quotes)], ensure_ascii=False)
    pages['ircquote_random'] = ('DDR Norway - IRC Quotes', section(qt, nav + f'''<div id="rq">{qblock(min(quotes))}</div>
<script>var Q={qjson};document.getElementById("rq").innerHTML=Q[Math.floor(Math.random()*Q.length)];</script>'''))

    # ---- forum index (from the archived board index), webshop, control panel
    fj = json.load(open(RAW / 'sub/forum.json'))
    body = ('<p><br><b>Velkommen til forum-delen av DDRNorway.no!</b><br>Det er anbefalt &aring; registrere seg som medlem '
            'p&aring; forumet. Du oppn&aring;r en rekke fordeler, og det er helt gratis og uten forpliktelser. '
            'Se <a href="forumregler.html">forumreglene</a> f&oslash;r du poster.</p>\n')
    for cat in fj['categories']:
        body += f'<table class="board" width="100%" cellspacing="0" cellpadding="3"><tr><th colspan="4">{html.escape(cat["name"])}</th></tr>' \
                '<tr class="hdr"><td width="55%">Forum</td><td>Emner</td><td>Svar</td><td>Siste postering</td></tr>'
        for f in cat['forums']:
            mod = f' <span class="mod">Forum ledes av: {html.escape(f["mod"])}</span>' if f['mod'] else ''
            body += (f'<tr><td><b>{html.escape(f["name"])}</b><br><span class="desc">{html.escape(f["desc"])}{mod}</span></td>'
                     f'<td align="center">{f["topics"]}</td><td align="center">{f["replies"]}</td>'
                     f'<td><span class="desc">{html.escape(f["last_date"])}</span><br>I: {html.escape(f["last_topic"])}<br>Av: {html.escape(f["last_by"])}</td></tr>')
        body += '</table><br>'
    body += f'<p><b>Forumstatistikk:</b> {fj["posts"]} innlegg | {fj["members"]} medlemmer</p>'
    pages['forum'] = ('DDR Norway - Forum', section('DDR Norways Forum', body))

    shop = read(RAW / 'sub/webshop.html')
    shop = html.unescape(re.sub(r'<[^>]+>', '\n', re.sub(r'<script.*?</script>|<style.*?</style>', '', shop, flags=re.S)))
    products = []
    for name, price in re.findall(r'\n([^\n]+)\n\s*Our price:\s*([\d.]+ SEK)', shop):
        if (name, price) not in products:
            products.append((name, price))
    body = ('<p><br>Nettbutikken drives av Positive Gaming AS og selger dansematter, spill og tilbeh&oslash;r. '
            'Alle priser er i SEK.</p><table class="board" width="100%" cellspacing="0" cellpadding="3">'
            '<tr><th>Produkt</th><th>Pris</th></tr>' +
            ''.join(f'<tr><td>{html.escape(n)}</td><td align="right">{p}</td></tr>' for n, p in products) +
            '</table><p>Bestilling og sp&oslash;rsm&aring;l: <a href="kontakt.html">kontakt oss</a>.</p>')
    pages['webshop'] = ('DDR Norway - Webshop', section('Positive Gaming Webshop', body))

    pages['cp'] = ('DDR Norway - Kontrollpanel', section('Kontrollpanel', '''<p><br>Logg inn for &aring; administrere sidene.</p>
<form onsubmit="return false"><table><tr><td>Brukernavn:</td><td><input type="text" size="20"></td></tr>
<tr><td>Passord:</td><td><input type="password" size="20"></td></tr>
<tr><td></td><td><input type="submit" value="Logg inn"></td></tr></table></form>'''))

    # ---- wiki ("DDR-leksikon")
    for p in sorted((RAW / 'wiki').rglob('*.html')):
        raw_title = unquote(str(p.relative_to(RAW / 'wiki'))[:-5])
        title = raw_title.replace('_', ' ')
        name = wiki_page(raw_title)[:-5]
        c = wiki_content(read8(p))
        pages[name] = (f'DDR Norway - {title}', section('DDR-leksikon' if name == 'leksikon' else html.escape(title), c))

    gallery(pages)

    # ---- results from ccbs.sesse.net
    NB = RAW / 'ccbs/nb'
    tournaments = json.load(open(RAW / 'ccbs/tournaments.json'))
    seasons = {}
    for t in tournaments:
        seasons.setdefault(t['season'], []).append(t)
    body = ('<p><br>Resultater fra alle turneringer i regi av DDR Norway, hentet fra turneringssystemet CCBS. '
            'Se ogs&aring; <a href="spillere.html">spillere</a> og <a href="sanger.html">sanger</a>.</p>\n<div class="ccbs"><div class="main">')
    for season, ts in seasons.items():
        body += f'<h2>{html.escape(season)}</h2><div><ul>' + ''.join(
            f'<li><a href="turnering_{t["id"]}.html">{html.escape(t["name"])}</a></li>' for t in ts) + '</ul></div>'
    pages['resultater'] = ('DDR Norway - Resultater', section('Resultater', body + '</div></div>'))
    for t in tournaments:
        p = NB / f'tournaments/{t["id"]}.html'
        if p.exists():
            pages[f'turnering_{t["id"]}'] = (f'DDR Norway - {t["name"]}', section(html.escape(t['name']), ccbs_main(read8(p))))
    for pl in players:
        p = NB / f'players/{pl["id"]}.html'
        if p.exists():
            pages[f'spiller_{pl["id"]}'] = (f'DDR Norway - {pl["nick"]}', section(html.escape(pl['nick']), ccbs_main(read8(p))))
    pages['spillere'] = ('DDR Norway - Spillere', section('Spillere', ccbs_main(read8(NB / 'players.html'))))
    songs = ccbs_main(read8(NB / 'songs.html'))
    songs = re.sub(r'<tr>(\s*<td><a href="sanger\.html#s_(\d+)")', r'<tr id="s_\2">\1', songs)
    pages['sanger'] = ('DDR Norway - Sanger', section('Sanger', songs))

    # ---- render
    LOCAL.update(f'{n}.html' for n in pages)
    tpl = fix_links(tpl)
    for name, (title, c) in pages.items():
        out = tpl.replace('{{TITLE}}', html.escape(title)).replace('{{CONTENT}}', fix_links(author_links(clean_embedded(c))))
        (OUT / f'{name}.html').write_text(out, 'utf-8')
    for p in OUT.glob('*.html'):
        p.write_text(drop_dead(p.read_text('utf-8'), OUT), 'utf-8')

    # ---- NM 2005 mini-site (own design)
    nm = OUT / 'nm05'
    nm.mkdir()
    for p in (RAW / 'pages').glob('nm05_index.php_x_*.html'):
        s = read(p).replace('charset=iso-8859-1', 'charset=utf-8')
        s = re.sub(r'href="(?:http://www\.ddrnorway\.no/nm05/)?index\.php\?x=(\w+)"',
                   lambda m: f'href="{m.group(1)}.html"' if (RAW / f'pages/nm05_index.php_x_{m.group(1)}.html').exists() else 'href="paamelding.html"', s)
        s = re.sub(r'<img src="(\w+\.(?:gif|png))"[^>]*>',
                   lambda m: m.group(0) if (RAW / 'assets/nm05' / m.group(1)).exists() else '', s)
        (nm / (p.stem.split('x_')[1] + '.html')).write_text(drop_dead(s, nm), 'utf-8')
    if (RAW / 'assets/nm05').exists():
        for f in (RAW / 'assets/nm05').iterdir():
            shutil.copy(f, nm / f.name)

    # ---- link check
    missing = set()
    for p in OUT.rglob('*.html'):
        for u in re.findall(r'''(?:href|src|background)=["']?([^"' >#]+)''', p.read_text('utf-8')):
            if u.startswith(('http', 'mailto:', 'javascript:')) or not u:
                continue
            if not (p.parent / u.replace('%20', ' ')).exists():
                missing.add(f'{p.relative_to(OUT)} -> {u}')
    print(f'{len(pages)} pages written to {OUT}')
    if missing:
        print('MISSING:', *sorted(missing), sep='\n  ')


if __name__ == '__main__':
    main()
