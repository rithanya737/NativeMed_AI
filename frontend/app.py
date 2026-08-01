import os
import csv
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime
from database import get_connection
import requests
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Passwords already stored in the `users` table before this fix (if any)
# were plaintext -- check_password_hash() returns False (not a crash) for a
# string that isn't a valid werkzeug hash, so accounts created before this
# change will need their password reset rather than silently breaking.
MIN_PASSWORD_LENGTH = 8

BACKEND_URL = "http://127.0.0.1:8000"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")  # adjust if backend/ and frontend/ sit differently

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static"),
)
# Looks for an environment variable. If missing, falls back to a temporary test key.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_fallback_key_only")


CSV_PATH = os.path.join(BASE_DIR, "Explore_Herb_Report.csv")
IMAGES_DIR = os.path.join(FRONTEND_DIR, "static", "images")
CONTRIB_UPLOAD_DIR = os.path.join(FRONTEND_DIR, "static", "uploads", "contributions")


def load_herb_image_map():
    image_map = {}
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["Plant Name"].strip().lower()
                image_map[name] = row["Selected Image Filename"].strip()
    except FileNotFoundError:
        print(f"WARNING: {CSV_PATH} not found.")
    return image_map

HERB_IMAGE_MAP = load_herb_image_map()
CSV_KEYS = list(HERB_IMAGE_MAP.keys())


def load_actual_images_on_disk():
    disk_map = {}
    if os.path.isdir(IMAGES_DIR):
        for fname in os.listdir(IMAGES_DIR):
            name_no_ext, ext = os.path.splitext(fname)
            if ext.lower() in (".jpg", ".jpeg", ".png"):
                normalized = name_no_ext.strip().lower().replace("_", " ").replace("-", " ")
                disk_map[normalized] = fname
    return disk_map

IMAGES_ON_DISK = load_actual_images_on_disk()


def find_herb_image(plant_name: str) -> str:
    key = plant_name.strip().lower()

    if key in HERB_IMAGE_MAP:
        return HERB_IMAGE_MAP[key]

    for csv_key in CSV_KEYS:
        if csv_key in key or key in csv_key:
            return HERB_IMAGE_MAP[csv_key]

    key_words = set(key.split())
    for csv_key in CSV_KEYS:
        if key_words & set(csv_key.split()):
            return HERB_IMAGE_MAP[csv_key]

    normalized_key = key.replace("_", " ").replace("-", " ")
    if normalized_key in IMAGES_ON_DISK:
        return IMAGES_ON_DISK[normalized_key]

    return "placeholder.jpg"



   
@app.route("/chat")
def chat():
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    reply = generate_ai_reply(user_message)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ai_queries (query_text, response_text, created_at) VALUES (%s, %s, %s)",
            (user_message, reply, datetime.now()),
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Could not log ai_query:", e)

    return jsonify({"reply": reply})


def generate_ai_reply(user_message: str) -> str:
    return (
        "Thanks for your question! This is a placeholder reply — wire up "
        "generate_ai_reply() in app.py to your LLM of choice or your "
        "medicinal_plants database to return real answers."
    )

def _find_herb_image(*names: str | None) -> str:
    """Return the best-matching static image path for a plant, trying each
    given name (common name, then botanical name), or a generic fallback
    image if no photo matches."""
    for name in names:
        if not name:
            continue
        key = _normalize_image_key(name)
        if key in _HERB_IMAGE_INDEX:
            return _HERB_IMAGE_INDEX[key]
        if key in _HERB_IMAGE_ALIASES:
            return _HERB_IMAGE_ALIASES[key]
    return _FALLBACK_HERB_IMAGE


def _plant_to_card(plant: dict) -> dict:
    """Adapt a backend plant record (common_name/botanical_name/...) into
    the field names exploreherb.html expects (plant_name/scientific_name/...),
    and attach a matching gallery image."""
    return {
        "plant_name": plant.get("common_name") or "Unknown plant",
        "scientific_name": plant.get("botanical_name") or "",
        "medicinal_properties": plant.get("medicinal_properties") or "No information available.",
        "traditional_uses": plant.get("traditional_uses") or "No information available.",
        "cultural_significance": plant.get("cultural_significance") or "No information available.",
        "diseases_treated": plant.get("diseases_treated") or "No information available.",
        "image": _find_herb_image(plant.get("common_name"), plant.get("botanical_name")),
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/signin")
def signin():
    return render_template("signin.html")


@app.route("/api/signin", methods=["POST"])
def api_signin():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id, full_name, password FROM users WHERE email = %s",
        (email,),
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    # Deliberately the same error whether the email doesn't exist or the
    # password is wrong -- distinguishing the two lets an attacker enumerate
    # which emails have accounts.
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session.clear()
    session["user_id"] = user["user_id"]
    session["user_name"] = user["full_name"]
    return jsonify({"success": True, "redirect": url_for("dashboard")})


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or ""
    country = (data.get("country") or "").strip()

    if not full_name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match"}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"error": "An account with that email already exists"}), 409

    cursor.execute(
        "INSERT INTO users (full_name, email, password, country, created_at) VALUES (%s, %s, %s, %s, %s)",
        (full_name, email, generate_password_hash(password), country, datetime.now()),
    )
    new_user_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    session.clear()
    session["user_id"] = new_user_id
    session["user_name"] = full_name
    return jsonify({"success": True, "redirect": url_for("dashboard")}), 201


@app.route("/logout")
def logout():
    # dashboard.js and settings.js's Sign Out buttons both navigate here
    # directly (window.location.href = "/logout"); this only clears the
    # server-side session -- it does NOT touch localStorage's
    # "loggedInUser" key that signin.js sets, since that's a separate,
    # client-side-only flag some other pages (e.g. identifyherb.js) check
    # instead. See the note on /settings below for why these two auth
    # mechanisms don't currently talk to each other.
    session.clear()
    return redirect(url_for("signin"))


@app.route("/identify-herb")
def identify_herb():
    return render_template("identifyherb.html")


@app.route("/explore-herbs")
def explore_herbs():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM medicinal_plants")
    herbs = cursor.fetchall()
    cursor.close()
    conn.close()

    for herb in herbs:
        herb["image_file"] = find_herb_image(herb["plant_name"])

    return render_template("exploreherb.html", herbs=herbs)


@app.route("/contribute")
def contribute():
    return render_template("contribute.html")


def _build_dashboard_context() -> dict:
    """Builds the data dashboard.html (and its 60s auto-refresh via
    /api/dashboard-data) needs. Shared by both so they can never drift out
    of sync with each other.

    Several fields are honest zeros/empty lists rather than real numbers:
    there's currently no per-user activity log wired up (ai_queries has no
    user_id column, and there's no contributions/identifications table at
    all -- /contribute and /api/identify-plant don't write to MySQL). Only
    total_queries (a sitewide count) and the herb-category breakdown are
    backed by real data. Wrapped in try/except so a missing/renamed table
    degrades to 0 instead of taking the whole dashboard down with it.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) total FROM ai_queries")
        total_queries = cursor.fetchone()["total"]
    except Exception as e:
        print("Could not count ai_queries:", e)
        total_queries = 0

    cursor.execute("SELECT medicinal_properties FROM medicinal_plants")
    rows = cursor.fetchall()

    category_counter: dict[str, int] = {}
    for row in rows:
        value = row["medicinal_properties"]
        if value:
            category = value.split(",")[0].strip()
            category_counter[category] = category_counter.get(category, 0) + 1

    cursor.close()
    conn.close()

    return {
        "total_queries": total_queries,
        # TODO: these stay 0 until there's an actual contributions table and
        # /api/identify-plant logs identifications -- see docstring above.
        "total_contributions": 0,
        "total_identifications": 0,
        "approved_contributions": 0,
        "activity_labels": [],
        "activity_queries": [],
        "activity_contributions": [],
        "category_labels": list(category_counter.keys()),
        "category_counts": list(category_counter.values()),
        "month_labels": [],
        "month_contribution_counts": [],
        "recent": [],
    }


@app.route("/dashboard")
def dashboard():
    context = _build_dashboard_context()
    return render_template("dashboard.html", user_name=session.get("user_name"), **context)


@app.route("/api/dashboard-data")
def api_dashboard_data():
    return jsonify(_build_dashboard_context())


@app.route("/garden-planner")
def garden_planner():
    return render_template("index.html")


@app.route("/conservation-map")
def conservation_map():
    return render_template("index.html")


@app.route("/help-center")
def help_center():
    return render_template("index.html")
@app.route("/test")
def test():
    return "Test route is working!"
@app.route("/api/identify-plant", methods=["POST"])
def identify_plant():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    image = request.files["image"]
    files={
        "file": (
            image.filename,
            image.stream,
            image.mimetype
        )
    }

    # Optional LIME explanation (see backend/explainability/lime_explain.py).
    # Off by default -- it reruns the model once per perturbed sample
    # (40 by default, see routers/plant_id.py's DEFAULT_LIME_NUM_SAMPLES), so
    # it's much slower than a plain identification, especially on CPU-only
    # setups. The frontend passes explain=true only when the user has the
    # "Show AI Explanation" checkbox on -- forwarded here as query params to
    # the FastAPI backend.
    explain = request.args.get("explain", "false").lower() == "true"
    params = {"explain": "true"} if explain else {}
    lime_num_samples = request.args.get("lime_num_samples")
    if lime_num_samples:
        params["lime_num_samples"] = lime_num_samples

    # On CPU-only machines a LIME explanation was measured taking well over
    # 120s at the old 150-sample default -- long enough that this proxy gave
    # up before the backend finished, which is exactly what surfaced as
    # "Unable to analyze image right now" even though identification itself
    # had already succeeded. 40 samples (the new default) should be much
    # faster, but 300s of headroom is kept here as a safety margin rather
    # than tuning this too tightly to one machine's speed.
    timeout = 300 if explain else 60

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/identify-plant",
            files=files,
            params=params,
            timeout=timeout,
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
  
# -----------------------------------------------------------------------
# Auth helper
#
# session["user_id"] is now set for real by /api/signin and /api/register
# (see above) rather than only by the old client-side-only
# localStorage.setItem("loggedInUser", ...) in signin.js. That JS has been
# updated to actually call /api/signin -- see static/js/signin.js.
# -----------------------------------------------------------------------

def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("signin"))
        return view_func(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------------
# Knowledge contribution form
#
# contribute.html POSTs here as multipart/form-data (text fields + optional
# file uploads). There was previously no route at all for this URL, so every
# submission hit Flask's default 404 page, which isn't JSON -- the frontend's
# `await response.json()` then threw a parse error, always landing in the
# generic "Something went wrong submitting your contribution" catch block
# regardless of what the user typed.
# -----------------------------------------------------------------------

def _insert_contribution(cursor, values):
    # Column names match the `contributions` table as it actually exists in
    # this project's MySQL database (contribution_id, user_id, plant_name,
    # scientific_name, medicinal_use, traditional_use, image_path, status,
    # submitted_at) -- discovered via SHOW COLUMNS after the first attempt
    # with guessed names (herb_name/attachments/created_at) failed with
    # "Unknown column". local_name/region/preparation_method/
    # cultural_significance/safety_notes are added by _ensure_contributions_table
    # below since the original table predates this richer form.
    cursor.execute(
        """
        INSERT INTO contributions
            (user_id, plant_name, local_name, region, traditional_use,
             preparation_method, cultural_significance, safety_notes,
             image_path, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        """,
        values,
    )


_CONTRIBUTIONS_EXTRA_COLUMNS = {
    "local_name": "VARCHAR(255)",
    "region": "VARCHAR(255)",
    "preparation_method": "TEXT",
    "cultural_significance": "TEXT",
    "safety_notes": "TEXT",
}


def _ensure_contributions_table(cursor):
    # Creates the table from scratch only if it's missing entirely (e.g. a
    # fresh database). In this project's actual database the table already
    # exists with a smaller, hand-created schema, so the CREATE is a no-op
    # here -- the real work is the ALTER TABLE loop below, which adds the
    # extra columns this form needs without touching existing rows.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS contributions (
            contribution_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            plant_name VARCHAR(255) NOT NULL,
            scientific_name VARCHAR(255),
            medicinal_use TEXT,
            traditional_use TEXT NOT NULL,
            image_path TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            submitted_at DATETIME NOT NULL
        )
        """
    )

    cursor.execute("SHOW COLUMNS FROM contributions")
    # api_contribute passes a plain cursor here (rows are tuples, so
    # row[0] is the column name), but api_list_contributions passes a
    # dictionary cursor (rows are dicts like {"Field": ..., "Type": ...}),
    # where row[0] raises KeyError(0) instead -- handle both shapes so this
    # works regardless of which caller it's invoked from.
    existing_columns = {
        (row["Field"] if isinstance(row, dict) else row[0])
        for row in cursor.fetchall()
    }
    for column, column_type in _CONTRIBUTIONS_EXTRA_COLUMNS.items():
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE contributions ADD COLUMN {column} {column_type}")


@app.route("/api/contribute", methods=["POST"])
@login_required
def api_contribute():
    herb_name = (request.form.get("herb-name") or "").strip()
    local_name = (request.form.get("local-name") or "").strip()
    region = (request.form.get("region") or "").strip()
    traditional_use = (request.form.get("traditional-use") or "").strip()
    prep = (request.form.get("prep") or "").strip()
    culture = (request.form.get("culture") or "").strip()
    safety = (request.form.get("safety") or "").strip()

    if not herb_name or not local_name or not region or not traditional_use:
        return jsonify({
            "success": False,
            "message": "Herb name, local name, region, and traditional use are required.",
        }), 400

    # Save any uploaded photos/documents to disk. Kept best-effort: a failed
    # attachment save shouldn't block the text submission from going through.
    saved_filenames = []
    for upload in request.files.getlist("files"):
        if not upload or not upload.filename:
            continue
        try:
            os.makedirs(CONTRIB_UPLOAD_DIR, exist_ok=True)
            safe_name = f"{session['user_id']}_{int(datetime.now().timestamp())}_{secure_filename(upload.filename)}"
            upload.save(os.path.join(CONTRIB_UPLOAD_DIR, safe_name))
            saved_filenames.append(safe_name)
        except Exception as e:
            print("Could not save contribution attachment:", e)

    values = (
        session["user_id"], herb_name, local_name, region, traditional_use,
        prep, culture, safety, ",".join(saved_filenames), datetime.now(),
    )

    conn = get_connection()
    cursor = conn.cursor()
    try:
        _insert_contribution(cursor, values)
    except Exception as e:
        # Covers both cases: the table is missing entirely, or it exists
        # (as it does in this project's real database) but is missing one
        # of the extra columns this form collects. _ensure_contributions_table
        # handles both via CREATE TABLE IF NOT EXISTS + ALTER TABLE ADD
        # COLUMN for whichever columns aren't there yet, then this retries once.
        conn.rollback()
        print("Contribution insert failed, syncing table schema and retrying:", e)
        try:
            _ensure_contributions_table(cursor)
            _insert_contribution(cursor, values)
        except Exception as e2:
            try:
                cursor.execute("SHOW COLUMNS FROM contributions")
                actual_columns = [row[0] for row in cursor.fetchall()]
            except Exception:
                actual_columns = None
            print(
                "Contribution insert still failing after schema sync:", e2,
                "| actual `contributions` columns:", actual_columns,
            )
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "message": f"Could not save your contribution: {e2}. Actual columns: {actual_columns}.",
            }), 500

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Thanks! Your contribution was submitted for review.",
    })


@app.route("/api/contributions", methods=["GET"])
@login_required
def api_list_contributions():
    """Backs the "My Contributions" tab -- contribute.html previously had no
    JS that ever called this, so that tab always showed the static
    "you haven't submitted anything" placeholder regardless of what you'd
    actually submitted."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Make sure the schema is up to date (same self-heal as
        # api_contribute) so a fresh table/missing column here degrades to
        # an empty list instead of a 500.
        _ensure_contributions_table(cursor)
        cursor.execute(
            """
            SELECT contribution_id, plant_name, scientific_name, local_name,
                   region, traditional_use, preparation_method,
                   cultural_significance, safety_notes, image_path, status,
                   submitted_at
            FROM contributions
            WHERE user_id = %s
            ORDER BY submitted_at DESC
            """,
            (session["user_id"],),
        )
        rows = cursor.fetchall()
        conn.commit()
    except Exception as e:
        print("Could not fetch contributions:", e)
        rows = []
    finally:
        cursor.close()
        conn.close()

    for row in rows:
        if row.get("submitted_at") is not None:
            row["submitted_at"] = row["submitted_at"].isoformat()
        # Normalize missing/unset status to "pending" rather than showing
        # a blank badge -- new rows default to 'pending' anyway, but this
        # also covers any contributions that predate the status column.
        row["status"] = (row.get("status") or "pending").lower()

    return jsonify({"contributions": rows})


# -----------------------------------------------------------------------
# Settings page
# -----------------------------------------------------------------------

@app.route("/settings")
@login_required
def settings():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id, full_name, email, country, created_at FROM users WHERE user_id = %s",
        (session["user_id"],),
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        session.clear()
        return redirect(url_for("signin"))

    return render_template("settings.html", user=user)


@app.route("/api/update-profile", methods=["POST"])
@login_required
def api_update_profile():
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    country = (data.get("country") or "").strip()

    if not full_name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Make sure the email isn't already used by someone else
    cursor.execute(
        "SELECT user_id FROM users WHERE email = %s AND user_id != %s",
        (email, session["user_id"]),
    )
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"error": "That email is already in use by another account"}), 409

    cursor.execute(
        "UPDATE users SET full_name = %s, email = %s, country = %s WHERE user_id = %s",
        (full_name, email, country, session["user_id"]),
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Keep the session's display name in sync
    session["user_name"] = full_name

    return jsonify({"success": True, "message": "Profile updated successfully"})


@app.route("/api/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""

    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400
    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match"}), 400
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"New password must be at least {MIN_PASSWORD_LENGTH} characters"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT password FROM users WHERE user_id = %s", (session["user_id"],))
    row = cursor.fetchone()
    if not row or not check_password_hash(row["password"], current_password):
        cursor.close()
        conn.close()
        return jsonify({"error": "Current password is incorrect"}), 403

    cursor.execute(
        "UPDATE users SET password = %s WHERE user_id = %s",
        (generate_password_hash(new_password), session["user_id"]),
    )
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True, "message": "Password updated"})


@app.route("/api/delete-account", methods=["POST"])
@login_required
def api_delete_account():
    # settings.html's delete modal collects a password (deleteConfirmPassword)
    # specifically so a hijacked/left-open session can't be used to destroy
    # the account without re-proving identity -- require and verify it here.
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""

    if not password:
        return jsonify({"error": "Password is required to delete your account"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT password FROM users WHERE user_id = %s", (session["user_id"],))
    row = cursor.fetchone()
    if not row or not check_password_hash(row["password"], password):
        cursor.close()
        conn.close()
        return jsonify({"error": "Incorrect password"}), 403

    cursor.execute("DELETE FROM users WHERE user_id = %s", (session["user_id"],))
    conn.commit()
    cursor.close()
    conn.close()

    session.clear()
    return jsonify({"success": True, "redirect": url_for("home")})
  
if __name__ == "__main__":
    port = int(os.environ.get("FRONTEND_PORT", "5000"))
    app.run(debug=True, port=port)

