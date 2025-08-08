from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import subprocess, shlex

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # tighten later if you want

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@socketio.on("start_wfmu")
def start_wfmu(data):
    """
    Spawn capture.py with a WFMU playlist URL and stream stdout lines to client.
    """
    url = (data or {}).get("url", "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        emit("error", {"message": "Please enter a valid WFMU URL."})
        return

    try:
        # Use shlex.split to be safe with paths
        cmd = shlex.split(f"python3 capture.py {url}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,           # line-buffered
        )

        # Stream stdout
        for line in proc.stdout:
            emit("track", {"line": line.rstrip()})

        proc.wait()

        if proc.returncode == 0:
            emit("done")
        else:
            err = (proc.stderr.read() or "Unknown error").strip()
            emit("error", {"message": err})

    except Exception as e:
        emit("error", {"message": f"Exception: {e}"})

if __name__ == "__main__":
    # dev only; prod uses gunicorn --worker-class eventlet
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)