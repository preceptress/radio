#!/usr/bin/env python3
"""
capture.py — WFMU playlist scraper + Spotify matcher (CLI + importable)

- Accepts full WFMU URL or numeric show ID
- Scrapes artist/title robustly across several WFMU layouts
- Cleans titles (cuts '→', removes quotes & (...) )
- Skips non-music rows (Music behind DJ, IDs, PSAs, etc.)
- Searches Spotify and emits indicator + track URL
- Exposes scrape_and_match(url) for web usage; prints in CLI mode

Env (.env) for Spotify (optional):
  SPOTIFY_CLIENT_ID=...
  SPOTIFY_CLIENT_SECRET=...
"""

import os
import re
import sys
import time
import unicodedata
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------- Spotify (optional) ----------------
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except Exception:
    spotipy = None

load_dotenv()
CID  = os.getenv("SPOTIFY_CLIENT_ID")
CSEC = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = None
if spotipy and CID and CSEC:
    try:
        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(client_id=CID, client_secret=CSEC),
            requests_timeout=12
        )
    except Exception:
        sp = None  # fail soft; scraping still works

# ---------------- HTTP ----------------
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def fetch_html_bytes(url: str) -> bytes:
    """Return raw BYTES so BS4 can auto-detect charset (fixes Nilüfer mojibake)."""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    return r.content

def txt(el) -> str:
    return (el.get_text(" ", strip=True) if el else "").strip()

# ---------------- Cleaning / filters ----------------
def clean_title(title: str) -> str:
    """Drop text after '→', remove quotes & (...) blocks, collapse whitespace."""
    if "→" in title:
        title = title.split("→", 1)[0]
    title = title.replace('"', '').replace("“", "").replace("”", "")
    title = re.sub(r"\(.*?\)", "", title)              # remove (Live), etc.
    title = re.sub(r"\s+", " ", title).strip()         # collapse spaces
    title = title.strip(" -–—\u2013\u2014")
    return title

def should_skip(artist: str, title: str) -> bool:
    """Skip background beds, IDs, PSAs, empty rows, etc."""
    a = (artist or "").lower().strip(": ")
    t = (title  or "").lower()

    if not t:
        return True
    if a.startswith("music behind dj") or "behind dj" in a:
        return True

    bad_terms = [
        "station id","id break","underwriting","psa",
        "news","traffic","weather","promo","ad break",
        "mic break","dj break","talk break"
    ]
    if any(b in a for b in bad_terms) or any(b in t for b in bad_terms):
        return True

    # Specific example you mentioned
    if a.startswith("music behind dj") and "today in history" in t:
        return True

    return False

# ---------------- Robust parser ----------------
def parse_tracks(html_bytes: bytes):
    """
    Return list of {'artist','title'}.
    Tries (1) header-mapped tables, (2) class-based cells, (3) generic fallback.
    """
    soup = BeautifulSoup(html_bytes, "html.parser")
    tracks = []

    # (1) Header-mapped tables (Artist/Title columns in any order)
    for tbl in soup.select("table"):
        headers = [txt(th).lower() for th in tbl.select("tr th")]
        # Some pages use first row TDs as headers
        if not headers and tbl.find("tr"):
            headers = [txt(td).lower() for td in tbl.find("tr").find_all("td")]

        if headers:
            def idx(*keys):
                for i, h in enumerate(headers):
                    if any(k in h for k in keys):
                        return i
                return None

            a_i = idx("artist", "performer")
            t_i = idx("title", "song", "track")
            rows = tbl.select("tr")
            if rows and headers:
                rows = rows[1:]  # skip header row

            for tr in rows:
                tds = tr.find_all("td")
                if not tds:
                    continue
                artist = txt(tds[a_i]) if a_i is not None and a_i < len(tds) else ""
                title  = txt(tds[t_i]) if t_i is not None and t_i < len(tds) else ""
                if artist or title:
                    tracks.append({"artist": artist, "title": title})
    if tracks:
        return tracks

    # (2) Classic class names seen on many WFMU pages
    artists = soup.select(".playlist_artist, td.playlist_artist, .artist, td.artist")
    titles  = soup.select(".playlist_song,   td.playlist_song,   .song,   td.song, .title, td.title, .track, td.track")
    if artists and titles and len(artists) == len(titles):
        return [{"artist": txt(a), "title": txt(s)} for a, s in zip(artists, titles)]

    # (3) Fallback row grouping
    for row in soup.select(".playlist_row, .songrow, .trackrow, tr"):
        a_el = row.select_one(".playlist_artist, .artist, td.artist, td.playlist_artist")
        s_el = row.select_one(".playlist_song, .song, .title, .track, td.playlist_song, td.song, td.title, td.track")
        if a_el or s_el:
            tracks.append({"artist": txt(a_el), "title": txt(s_el)})

    return tracks

# ---------------- Spotify matching ----------------
_PUNCT = r"""!"#$%&'()*+,./:;<=>?@[\]^_`{|}~"""
TRANS = str.maketrans("", "", _PUNCT)

def fold_ascii(s: str) -> str:
    """ü → u, é → e, etc."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def norm(s: str) -> str:
    s = fold_ascii(s).lower().translate(TRANS)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def best_spotify_match(artist: str, title: str):
    """Return (indicator, url). Uses quoted, unquoted, then ASCII‑folded search."""
    if not sp:
        return ("", "")

    attempts = [
        f'track:"{title}" artist:"{artist}"',
        f"{artist} {title}",
        f'{fold_ascii(artist)} {fold_ascii(title)}',
    ]

    items = []
    for q in attempts:
        try:
            res = sp.search(q, type="track", limit=5, market="US")
            items = res.get("tracks", {}).get("items", [])
            if items:
                break
        except Exception:
            continue

    if not items:
        return ("❌", "")

    na, nt = norm(artist), norm(title)

    def score(it):
        ia = ", ".join(a["name"] for a in it.get("artists", []))
        ititle = it.get("name", "")
        a, t = norm(ia), norm(ititle)
        s = 0
        if t == nt or nt in t or t in nt: s += 2
        if na in a or a in na:            s += 2
        # tiny bonus if first 2 words of title appear
        words = nt.split()
        if len(words) >= 1 and words[0] in t: s += 1
        if len(words) >= 2 and words[1] in t: s += 1
        return s, it

    best_s, best = sorted((score(i) for i in items), key=lambda x: x[0], reverse=True)[0]
    url = f'https://open.spotify.com/track/{best.get("id")}' if best.get("id") else ""
    if best_s >= 4: return ("✅", url)
    if best_s >= 2: return ("~", url)
    return ("❌", url or "")

# ---------------- Public API for Flask ----------------
def scrape_and_match(url: str):
    """Return {'error': str, 'items': [{'artist','title','indicator','spotify_url'}]}"""
    try:
        html_bytes = fetch_html_bytes(url)
    except Exception as e:
        return {"error": f"Error fetching URL: {e}", "items": []}

    rows = parse_tracks(html_bytes)
    if not rows:
        return {"error": "No tracks found — page structure may have changed.", "items": []}

    items = []
    for row in rows:
        artist = (row.get("artist") or "").strip()
        title  = clean_title((row.get("title") or "").strip())
        if should_skip(artist, title):
            continue
        if not (artist and title):
            continue
        ind, link = best_spotify_match(artist, title)
        items.append({"artist": artist, "title": title, "indicator": ind, "spotify_url": link})

    return {"error": "", "items": items}

# ---------------- CLI ----------------
if __name__ == "__main__":
    user_in = sys.argv[1].strip() if len(sys.argv) > 1 else input("Enter WFMU playlist URL or Show ID: ").strip()
    if user_in.isdigit():
        user_in = f"https://wfmu.org/playlists/shows/{user_in}"
    if not (user_in.startswith("http://") or user_in.startswith("https://")):
        print("❌ Please enter a valid WFMU URL or numeric show ID.")
        sys.exit(1)

    data = scrape_and_match(user_in)
    if data["error"]:
        print(f"❌ {data['error']}")
        sys.exit(1)

    items = data["items"]
    if not items:
        print("⚠️ No valid tracks after filtering.")
        sys.exit(0)

    print(f"✅ Found {len(items)} tracks:")
    for i, it in enumerate(items, 1):
        line = f"{i:02d}. {it['artist']} — {it['title']}"
        if it["indicator"]:
            line += f"  {it['indicator']}"
        if it["spotify_url"]:
            line += f" {it['spotify_url']}"
        print(line, flush=True)
        time.sleep(0.02)  # helps streaming UIs