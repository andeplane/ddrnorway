# ddrnorway.no (2007) – static recreation

A static rebuild of the old DDR Norway community site as it looked in early
2007, assembled from Wayback Machine snapshots (2003–2007) and the Challenge
Cup score system at ccbs.sesse.net. Live at https://andeplane.github.io/ddrnorway/

* `docs/` – the generated site (open `docs/index.html`, or serve the folder).
* `raw/` – the source material: archived pages, assets, forum index, wiki
  articles, gallery pages and photos, plus the sesse.net tournament, player
  and song pages.
* `build.py` – rebuilds `docs/` from `raw/` (needs Python 3 and Pillow).

## What is real

Every content page in the left menu is the archived original: news, guides,
arcade locations, club pages, player profiles, reviews, rules, history, press,
contact, IRC quotes. Results come from CCBS: 61 tournaments (Challenge Cup
2003–2005, NM, European Cup, Euromix series) with full rankings and round
scores, 268 player pages and the song list. The forum page is the archived
board index (31 forums with real counts and last posts), the wiki pages are the
archived MediaWiki articles, the gallery holds every photo the archive kept,
and the webshop lists the products from the archived shop front.

## What is faked

* The middle band of the header graphic (six image slices) was never archived
  and is drawn by `build.py` as a stand-in. Top and bottom slices are original.
* A few small layout images (dashed line, menu backgrounds) are generated.
* Forum emoticons were not archived; the text code (`:)`) is shown instead.
* Forum threads and user profiles were not rebuilt: author names link to the
  player's results page when the nick matches, comment links go to the forum
  index. Links to pages that were never archived are shown as plain text.
* Countdown boxes, vote buttons, logins and other dynamic bits are removed.
