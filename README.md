# ddrnorway.no (2007) – static recreation

A static rebuild of the old DDR Norway community site as it looked in early
2007, assembled from Wayback Machine snapshots (2004–2007) and the Challenge
Cup score system at ccbs.sesse.net.

* `docs/` – the generated site (open `docs/index.html`, or serve the folder).
* `raw/` – the source material: archived pages and assets, plus the sesse.net
  tournament, player and song pages.
* `build.py` – rebuilds `docs/` from `raw/` (needs Python 3 and Pillow).

## What is real

Every content page in the left menu is the archived original: news, guides,
arcade locations, club pages, player profiles, reviews, rules, history, press,
contact, IRC quotes. Results come from CCBS: 61 tournaments (Challenge Cup
2003–2005, NM, European Cup, Euromix series) with full rankings and round
scores, 268 player pages and the song list.

## What is faked

* The middle band of the header graphic (six image slices) was never archived
  and is drawn by `build.py` as a stand-in. Top and bottom slices are original.
* A few small layout images (dashed line, menu backgrounds, wiki star) are
  generated placeholders.
* Forum emoticons were not archived; the text code (`:)`) is shown instead.
* Review photos and some documents that were never archived are dropped or
  linked to the Wayback Machine. Forum, gallery, wiki, webshop and all other
  external links point to the Wayback Machine.
* Countdown boxes, vote buttons and other dynamic bits are removed.
