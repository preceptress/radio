from flask import Flask, render_template, request
import re
from capture import scrape_and_match  # uses the patched capture.py you have

app = Flask(__name__)

WFMU_RE = re.compile(r"^https?://(www\.)?wfmu\.org/playlists/shows/\d+$")

def normalize_wfmu_input(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return f"https://wfmu.org/playlists/shows/{raw}"
    if WFMU_RE.match(raw):
        return raw
    return None

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    items = []
    submitted = False

    if request.method == "POST":
        submitted = True
        url = normalize_wfmu_input(request.form.get("url_or_show"))
        if not url:
            error = "Please enter a valid WFMU URL or numeric show ID."
        else:
            data = scrape_and_match(url)
            if data.get("error"):
                error = data["error"]
            else:
                items = data.get("items", [])

    return render_template("index.html", items=items, error=error, submitted=submitted)

if __name__ == "__main__":
    # dev only; prod uses gunicorn
    app.run(host="0.0.0.0", port=5000, debug=True)