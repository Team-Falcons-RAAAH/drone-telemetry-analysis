"""
Team Falcons — UAV Telemetry Analyser
======================================
Run:
    pip install flask pymavlink pandas plotly
    python app.py
Open: http://localhost:5000
"""

import gc
import os
import uuid
import tempfile
from flask import Flask, render_template, request, jsonify, redirect, url_for
from parser import parser
from visualization import add_enu_columns, get_plot_data

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory store — cleared on every server restart (fulfils "gone on reload")
# Structure: { session_id: { id, filename, size_kb, label, df_gps, df_imu, plot_json } }
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
    4. Builds the Plotly 3D JSON via build_3d_plot().
    5. Stores everything in SESSIONS under a fresh session_id.
    6. Deletes the temp file after gc.collect() releases pymavlink handle.
    7. Returns session_id so the frontend redirects to the dashboard.
    """
    if "file" not in request.files:
        return jsonify(error="No file part"), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify(error="No file selected"), 400

    file_bytes = file.read()
    size_kb    = round(len(file_bytes) / 1024, 1)

    # Write to a named temp file so pymavlink can open it by path.
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

    df_gps    = add_enu_columns(df_gps)
    plot_data = get_plot_data(df_gps)

    session_id = str(uuid.uuid4())[:8]
    SESSIONS[session_id] = {
        "id":        session_id,
        "filename":  file.filename,
        "size_kb":   size_kb,
        "label":     file.filename.replace(".bin", "").upper(),
        "df_gps":    df_gps,     # columns: timestamp, lat, lon, alt, spd, E, N, U
        "df_imu":    df_imu,     # columns: timestamp, AccX, AccY, AccZ, dt
        "plot_data": plot_data,  # Plotly JSON string — rendered in dashboard
    }

    return jsonify(session_id=session_id)


@app.route("/dashboard")
def dashboard_home():
    """Dashboard with no active flight — shows empty state."""
    return render_template(
        "dashboard.html",
        session=None,
        plot_data="null",
        all_sessions=list(SESSIONS.values()),
    )


@app.route("/dashboard/<session_id>")
def dashboard_session(session_id):
    session = SESSIONS.get(session_id)
    if not session:
        return redirect(url_for("dashboard_home"))
    all_sessions = [s for s in SESSIONS.values() if s["id"] != session_id]
    return render_template(
        "dashboard.html",
        session=session,
        plot_data=session.get("plot_data", "null"),
        all_sessions=all_sessions,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
