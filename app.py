"""
Team Falcons — UAV Telemetry Analyser
======================================
Run:
    pip install flask pymavlink pandas plotly flask-limiter
    python app.py

Open: http://localhost:5000
"""

import gc
import os
import uuid
import tempfile
from collections import OrderedDict

from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from limits.storage import MemoryStorage

from telemetry_parser import parser
from visualization import add_enu_columns, get_plot_data

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-only-for-local")

# 🔒 Максимальний розмір файлу — 16 MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 🔒 Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # явно вказуємо — попередження зникне
)

# ---------------------------------------------------------------------------
# Session store (in-memory, LRU, max 20 sessions)
# ---------------------------------------------------------------------------

MAX_SESSIONS = 20
SESSIONS: OrderedDict = OrderedDict()

# 🔒 Дозволені розширення файлів
ALLOWED_EXTENSIONS = {'bin'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    """Повертає True лише якщо файл має дозволене розширення."""
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def _add_session(session_id: str, data: dict) -> None:
    """Додає сесію і видаляє найстарішу якщо перевищено ліміт."""
    if len(SESSIONS) >= MAX_SESSIONS:
        oldest_id, oldest_data = SESSIONS.popitem(last=False)
        # Явно звільняємо пам'ять від великих об'єктів
        oldest_data.pop("df_gps", None)
        oldest_data.pop("df_imu", None)
        oldest_data.pop("plot_data", None)
        gc.collect()
        print(f"[sessions] evicted oldest session: {oldest_id}")
    SESSIONS[session_id] = data


def _safe_unlink(path: str) -> None:
    """Видаляє файл, ігноруючи помилки якщо він вже видалений."""
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    """Повертає JSON замість стандартної HTML сторінки при перевищенні розміру."""
    return jsonify(error="File is too large. Maximum allowed size is 16 MB"), 413


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify(error="Not found"), 404


@app.errorhandler(429)
def handle_rate_limit(e):
    return jsonify(error="Too many requests. Please slow down."), 429


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/upload")
def upload_page():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
@limiter.limit("10 per minute")  # 🔒 Максимум 10 uploads на хвилину
def handle_upload():
    """
    1. Перевіряє наявність та розширення файлу.
    2. Зберігає у temp файл.
    3. Парсить GPS та IMU дані.
    4. Будує Plotly 3D JSON.
    5. Зберігає у SESSIONS з LRU-обмеженням.
    6. Видаляє temp файл.
    7. Повертає session_id.
    """
    if "file" not in request.files:
        return jsonify(error="No file part"), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify(error="No file selected"), 400

    # 🔒 Перевірка розширення
    if not allowed_file(file.filename):
        return jsonify(error="Only .bin files are allowed"), 400

    # 🔒 Очищення імені файлу від небезпечних символів
    safe_name = secure_filename(file.filename)

    file_bytes = file.read()
    size_kb = round(len(file_bytes) / 1024, 1)

    # Записуємо у temp файл для pymavlink
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

    # Звільняємо handle pymavlink перед видаленням файлу
    gc.collect()
    _safe_unlink(tmp_path)

    df_gps = add_enu_columns(df_gps)
    plot_data = get_plot_data(df_gps)

    # 🔒 Повний UUID замість обрізаного — захист від брутфорсу
    session_id = str(uuid.uuid4())

    _add_session(session_id, {
        "id": session_id,
        "filename": safe_name,
        "size_kb": size_kb,
        "label": safe_name.replace(".bin", "").upper(),
        "df_gps": df_gps,
        "df_imu": df_imu,
        "plot_data": plot_data,
    })

    return jsonify(session_id=session_id)


@app.route("/dashboard")
def dashboard_home():
    """Dashboard без активного польоту — порожній стан."""
    return render_template(
        "dashboard.html",
        session=None,
        plot_data="null",
        all_sessions=list(SESSIONS.values()),
    )


@app.route("/dashboard/<session_id>")
@limiter.limit("60 per minute")  # 🔒 Захист від перебору session_id
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


@app.route("/session/<session_id>/delete", methods=["POST"])
def delete_session(session_id):
    """Дозволяє користувачу вручну видалити сесію і звільнити пам'ять."""
    session = SESSIONS.pop(session_id, None)
    if session:
        session.pop("df_gps", None)
        session.pop("df_imu", None)
        session.pop("plot_data", None)
        gc.collect()
    return redirect(url_for("dashboard_home"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 🔒 debug=True лише якщо явно вказано в змінній середовища
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(
        debug=debug_mode,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )