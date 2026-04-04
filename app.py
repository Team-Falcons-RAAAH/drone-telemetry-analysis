"""
Team Falcons — UAV Telemetry Analyser
======================================
Run:
    pip install flask pymavlink pandas
    python app.py
Open: http://localhost:5000
"""

import gc
import os
import uuid
import tempfile
from flask import Flask, render_template, request, jsonify, redirect, url_for
from parser import parser
from visualization import add_enu_columns

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory store — cleared on every server restart (fulfils "gone on reload")
# Structure: { session_id: { id, filename, size_kb, label, df_gps, df_imu } }
SESSIONS = {}


def _safe_unlink(path: str) -> None:
    """Delete a file, ignoring errors if it is already gone."""
    try:
        os.unlink(path)
    except OSError:
        pass


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/upload")
def upload_page():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def handle_upload():
    """
    1. Saves the uploaded .bin to a temp file.
    2. Runs parser.gpsData() and parser.imuData() on it.
    3. Runs add_enu_columns() on the GPS DataFrame.
    4. Stores both DataFrames in SESSIONS under a fresh session_id.
    5. Deletes the temp file — after gc.collect() so Windows releases
       the pymavlink file handle before we try to unlink.
    6. Returns the session_id so the frontend can redirect to the dashboard.
    """
    if "file" not in request.files:
        return jsonify(error="No file part"), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify(error="No file selected"), 400

    file_bytes = file.read()
    size_kb    = round(len(file_bytes) / 1024, 1)

    # Write bytes to a named temp file so pymavlink can open it by path.
    # We manage deletion manually (after gc.collect) instead of using
    # finally, because on Windows pymavlink holds the handle open until
    # the mavutil object is garbage-collected — unlink inside finally
    # runs before that and raises PermissionError: [WinError 32].
    tmp = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
    tmp_path = tmp.name
    tmp.write(file_bytes)
    tmp.close()

    try:
        df_gps = parser.gpsData(tmp_path)
        df_imu = parser.imuData(tmp_path)
    except Exception as e:
        gc.collect()
        _safe_unlink(tmp_path)
        return jsonify(error=f"Parsing failed: {e}"), 500

    # Release pymavlink's internal file handle before deleting the file.
    gc.collect()
    _safe_unlink(tmp_path)

    df_gps = add_enu_columns(df_gps)

    session_id = str(uuid.uuid4())[:8]
    SESSIONS[session_id] = {
        "id":       session_id,
        "filename": file.filename,
        "size_kb":  size_kb,
        "label":    file.filename.replace(".bin", "").upper(),
        "df_gps":   df_gps,   # columns: timestamp, lat, lon, alt, spd, E, N, U
        "df_imu":   df_imu,   # columns: timestamp, AccX, AccY, AccZ, dt
    }

    return jsonify(session_id=session_id)


@app.route("/dashboard")
def dashboard_home():
    """Dashboard with no active flight — shows empty state or last session."""
    return render_template("dashboard.html", session=None, all_sessions=list(SESSIONS.values()))


@app.route("/dashboard/<session_id>")
def dashboard_session(session_id):
    session = SESSIONS.get(session_id)
    if not session:
        return redirect(url_for("dashboard_home"))
    all_sessions = [s for s in SESSIONS.values() if s["id"] != session_id]
    return render_template("dashboard.html", session=session, all_sessions=all_sessions)


if __name__ == "__main__":
    app.run(debug=True, port=5000)