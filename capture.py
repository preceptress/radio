#!/usr/bin/env python3
"""
capture.py — WFMU playlist scraper (CLI + stream-friendly)
- Input: WFMU playlist URL (e.g. https://wfmu.org/playlists/shows/154876)
- Output: prints each track line-by-line so a Socket.IO listener can stream it.
"""

import sys
import time
import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    return resp.text

def text(el):
    return (el.get_text(" ", strip=True) if el else "").strip()

def parse_tracks(html: str):
    """
    Try multiple common WFMU playlist layouts.
    Returns a list of dicts like {"artist": "...", "title": "...", "extra": "..."}
    """
    soup = BeautifulSoup(html, "html.parser")
    tracks = []

    # 1) Table-based playlists with header columns (Artist / Title / etc.)
    tables = soup.select("table, .playlist, #playlist, .songtable")
    for tbl in tables:
        # find header mapping
        headers = [text(th).lower() for th in tbl.select("tr th")]
        if headers:
            try:
                a_idx = next(i for i, h in enumerate(headers) if "artist" in h or "performer" in h)
            except StopIteration:
                a_idx = None
            try:
                t_idx = next(i for i, h in enumerate(headers) if "title" in h or "song" in h or "track" in h)
            except StopIteration:
                t_idx = None

            if a_idx is not None or t_idx is not None:
                for tr in tbl.select("tr"):
                    tds = tr.find_all("td")
                    if not tds:
                        continue
                    artist = text(tds[a_idx]) if a_idx is not None and a_idx < len(tds) else ""
                    title  = text(tds[t_idx]) if t_idx is not None and t_idx < len(tds) else ""
                    if artist or title:
                        tracks.append({"artist": artist, "title": title, "extra": ""})

    if tracks:
        return tracks

    # 2) Cell-by-cell classes often used on WFMU pages
    # e.g. <td class="playlist_artist">, <td class="playlist_song">
    rows = []
    artists = soup.select(".playlist_artist, .artist")
    titles  = soup.select(".playlist_song, .song, .title, .track")
    if artists and titles and len(artists) == len(titles):
        for a_el, t_el in zip(artists, titles):
            rows.append({"artist": text(a_el), "title": text(t_el), "extra": ""})
    if rows:
        return rows

    # 3) Fallback: items grouped in rows with both artist/title inside
    for row in soup.select(".playlist_row, .songrow, .trackrow, tr"):
        a_el = row.select_one(".playlist_artist, .artist")
        t_el = row.select_one(".playlist_song, .song, .title, .track")
        if a_el or t_el:
            tracks.append({"artist": text(a_el), "title": text(t_el), "extra": ""})

    return tracks

def capture_wfmu(url: str):
    print(f"🎙 Fetching playlist from {url}...")
    try:
        html = fetch_html(url)
    except Exception as e:
        print(f"❌ Error fetching URL: {e}")
        return

    tracks = parse_tracks(html)

    if not tracks:
        print("⚠️ No tracks found — the page structure may differ. "
              "Try updating selectors in capture.py.")
        return

    print(f"✅ Found {len(tracks)} tracks:")
    # stream-friendly: print one line at a time
    for i, tr in enumerate(tracks, 1):
        artist = tr.get("artist", "")
        title  = tr.get("title", "")
        extra  = tr.get("extra", "")
        line = f"{i:02d}. {artist} — {title}".strip(" —")
        if extra:
            line += f" ({extra})"
        print(line, flush=True)
        time.sleep(0.01)  # tiny delay helps front-ends show gradual updates

if __name__ == "__main__":
    if len(sys.argv) > 1:
        wfmu_url = sys.argv[1].strip()
    else:
        wfmu_url = input("Enter WFMU playlist URL: ").strip()

    if not (wfmu_url.startswith("http://") or wfmu_url.startswith("https://")):
        print("❌ Please enter a valid WFMU URL (starts with http/https).")
        sys.exit(1)

    capture_wfmu(wfmu_url)