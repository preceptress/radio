#!/usr/bin/env python3
"""
capture.py — WFMU playlist scraper (CLI + stream-friendly)

Usage:
  python capture.py https://wfmu.org/playlists/shows/154876
  # or just: python capture.py   (it will prompt)

Behavior:
  - Scrapes a WFMU playlist page
  - Cleans titles: removes anything after '→', quotes, and (...) parts
  - Keeps artist + title format
  - Skips "Music behind DJ" and other non-track rows
  - Prints clean results, line-by-line, for CLI or Socket.IO streaming
"""

import sys
import time
import re
import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQ_TIMEOUT = 20

# --- Helpers ---------------------------------------------------------------

def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    return resp.text

def text(el) -> str:
    return (el.get_text(" ", strip=True) if el else "").strip()

def clean_title(title: str) -> str:
    """Clean track title for display."""
    if "→" in title:
        title = title.split("→", 1)[0]
    title = title.replace('"', "").replace("“", "").replace("”", "")
    title = re.sub(r"\(.*?\)", "", title)  # remove (content)
    title = re.sub(r"\s+", " ", title)     # collapse spaces
    return title.strip(" -–—\u2013\u2014").strip()

def should_skip(artist: str, title: str) -> bool:
    """Skip background, filler, or empty rows."""
    a = (artist or "").lower().strip(": ")
    t = (title or "").lower()

    if not t:
        return True

    if a.startswith("music behind dj") or "behind dj" in a:
        return True

    bad_terms = [
        "station id", "id break", "underwriting", "psa",
        "news", "traffic", "weather", "promo", "ad break",
        "mic break", "dj break", "talk break"
    ]
    if any(term in a for term in bad_terms) or any(term in t for term in bad_terms):
        return True

    if a.startswith("music behind dj") and "today in history" in t:
        return True

    return False

# --- Parsing ---------------------------------------------------------------

def parse_tracks(html: str):
    soup = BeautifulSoup(html, "html.parser")
    tracks = []

    # 1) Table with header columns
    for tbl in soup.select("table, .playlist, #playlist, .songtable"):
        headers = [text(th).lower() for th in tbl.select("tr th")]
        if not headers:
            continue

        def idx_of(*candidates):
            for i, h in enumerate(headers):
                if any(c in h for c in candidates):
                    return i
            return None

        a_idx = idx_of("artist", "performer")
        t_idx = idx_of("title", "song", "track")
        if a_idx is None and t_idx is None:
            continue

        for tr in tbl.select("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            artist = text(tds[a_idx]) if a_idx is not None and a_idx < len(tds) else ""
            title  = text(tds[t_idx]) if t_idx is not None and t_idx < len(tds) else ""
            if artist or title:
                tracks.append({"artist": artist, "title": title})

    if tracks:
        return tracks

    # 2) Class-based selectors
    artists = soup.select(".playlist_artist, .artist")
    titles  = soup.select(".playlist_song, .song, .title, .track")
    if artists and titles and len(artists) == len(titles):
        return [{"artist": text(a), "title": text(t)} for a, t in zip(artists, titles)]

    # 3) Fallback
    rows = []
    for row in soup.select(".playlist_row, .songrow, .trackrow, tr"):
        a_el = row.select_one(".playlist_artist, .artist")
        t_el = row.select_one(".playlist_song, .song, .title, .track")
        if a_el or t_el:
            rows.append({"artist": text(a_el), "title": text(t_el)})
    return rows

# --- Main ------------------------------------------------------------------

def capture_wfmu(url: str):
    print(f"🎙 Fetching playlist from {url}...")
    try:
        html = fetch_html(url)
    except Exception as e:
        print(f"❌ Error fetching URL: {e}")
        return

    raw_tracks = parse_tracks(html)
    if not raw_tracks:
        print("⚠️ No tracks found — page structure may have changed.")
        return

    cleaned = []
    for row in raw_tracks:
        artist = (row.get("artist") or "").strip()
        title  = clean_title((row.get("title") or "").strip())
        if should_skip(artist, title):
            continue
        if artist or title:
            cleaned.append(f"{artist} — {title}")

    if not cleaned:
        print("⚠️ No valid tracks after filtering.")
        return

    print(f"✅ Found {len(cleaned)} tracks:")
    for i, line in enumerate(cleaned, 1):
        print(f"{i:02d}. {line}", flush=True)
        time.sleep(0.01)  # helps streaming front-ends

if __name__ == "__main__":
    if len(sys.argv) > 1:
        wfmu_url = sys.argv[1].strip()
    else:
        wfmu_url = input("Enter WFMU playlist URL: ").strip()

    if not (wfmu_url.startswith("http://") or wfmu_url.startswith("https://")):
        print("❌ Please enter a valid WFMU URL (starts with http/https).")
        sys.exit(1)

    capture_wfmu(wfmu_url)