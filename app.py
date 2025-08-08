from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import subprocess

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # Production-ready CORS config

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@socketio.on("start_playlist")
def handle_start_playlist(data):
    show_id = data.get("show_id", "").strip()
    if not show_id:
        emit("error", {"message": "Invalid show ID"})
        return

    try:
        process = subprocess.Popen(
            ["python3", "capture.py", show_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            emit("track", {"line": line.strip()})

        process.wait()

        if process.returncode == 0:
            emit("done")
        else:
            error_msg = process.stderr.read().strip()
            emit("error", {"message": error_msg or "Unknown error occurred."})

    except Exception as e:
        emit("error", {"message": f"Exception: {e}"})

if __name__ == "__main__":
    # Dev only
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)