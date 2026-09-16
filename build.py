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
from urllib.parse import parse_qsl

ROOT = Path(__file__).parent
RAW = ROOT / 'raw'
OUT = ROOT / 'docs'
WB = 'https://web.archive.org/web/2007/'   # dead external links go to the archive

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
    u = re.sub(r'^https?://(www\.)?ddrnorway\.no(:80)?/?', '', u)
    if u.startswith(('http://', 'https://')):
        return u if 'web.archive.org' in u else WB + u
    u = u.lstrip('/')
    while u.startswith('../'):
        u = u[3:]
    if re.match(r'^(forum|gallery|wiki|webshop|multimedia|cp|pgshop)(/|$)', u):
        return WB + 'http://www.ddrnorway.no/' + u
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

    def href(m):
        u = m.group(2)
        if u.startswith(('http', 'mailto:', 'javascript:', '#')) or exists(u):
            return m.group(0)
        return f'{m.group(1)}{WB}http://www.ddrnorway.no/{u}'
    return re.sub(r'(href=["\']?)([^"\' >]+)', href, s, flags=re.I)


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
        '\n.quote { font-family: monospace; font-size: 11px; padding: 4px 0; }\n')

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
    players = json.load(open(RAW / 'ccbs/players.json'))
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
        out = tpl.replace('{{TITLE}}', html.escape(title)).replace('{{CONTENT}}', fix_links(clean_embedded(c)))
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
