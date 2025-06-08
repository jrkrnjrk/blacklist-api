from flask import Flask, request, jsonify, g, render_template_string, redirect, url_for, Response
import sqlite3
from functools import wraps
import requests

DATABASE = 'blacklist.db'

app = Flask(__name__)

# --- Auth Basic pour admin ---
ADMIN_USER = "leo"
ADMIN_PASS = "89294"

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS

def authenticate():
    return Response(
        'Authentification requise.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- DB utils ---

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                hwid TEXT PRIMARY KEY,
                reason TEXT NOT NULL
            )
        ''')
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- Webhook Discord pour logs ---

LOG_WEBHOOK_URL = "https://discord.com/api/webhooks/1381357433435324548/8Ui-kZ2oZDGrOEHRkOh2JS1mGczYQdIpxJuPX5XTfYiNNNu7Ey4EMZuEIjGMKZAyyWbn"

def log_blacklist_event(hwid, reason, username=None):
    content = f"⛔ **Blacklist update**\nHWID: `{hwid}`\nRaison: {reason}"
    if username:
        content += f"\nExécuté par: {username}"
    try:
        requests.post(LOG_WEBHOOK_URL, json={"content": content})
    except Exception as e:
        print(f"Erreur webhook: {e}")

# --- API endpoints ---

@app.route('/check_blacklist', methods=['GET'])
def check_blacklist():
    hwid = request.args.get('hwid')
    if not hwid:
        return jsonify({"error": "Missing 'hwid' parameter"}), 400
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT reason FROM blacklist WHERE hwid = ?', (hwid,))
    row = cursor.fetchone()
    
    if row:
        return jsonify({"blacklisted": True, "reason": row["reason"]})
    else:
        return jsonify({"blacklisted": False})

@app.route('/add_blacklist', methods=['POST'])
@requires_auth
def add_blacklist():
    data = request.get_json()
    hwid = data.get('hwid')
    reason = data.get('reason', 'Non spécifiée')
    if not hwid:
        return jsonify({"error": "Missing 'hwid' in request body"}), 400
    
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('INSERT INTO blacklist (hwid, reason) VALUES (?, ?)', (hwid, reason))
        db.commit()
        log_blacklist_event(hwid, reason, username=request.authorization.username)
        return jsonify({"success": True, "message": f"HWID {hwid} ajouté à la blacklist."})
    except sqlite3.IntegrityError:
        return jsonify({"error": "HWID déjà blacklisté."}), 409

@app.route('/remove_blacklist', methods=['POST'])
@requires_auth
def remove_blacklist():
    data = request.get_json()
    hwid = data.get('hwid')
    if not hwid:
        return jsonify({"error": "Missing 'hwid' in request body"}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM blacklist WHERE hwid = ?', (hwid,))
    db.commit()
    log_blacklist_event(hwid, "Retiré de la blacklist", username=request.authorization.username)
    return jsonify({"success": True, "message": f"HWID {hwid} retiré de la blacklist."})

# --- Admin panel web ---

ADMIN_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Panel Admin Blacklist HWID</title>
    <style>
        body { font-family: Arial, sans-serif; background: #222; color: #eee; margin: 20px; }
        h1 { color: #f44336; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { padding: 8px 12px; border: 1px solid #444; }
        th { background-color: #333; }
        tr:nth-child(even) { background-color: #2a2a2a; }
        form { margin-top: 20px; }
        input, textarea { padding: 8px; width: 100%; margin-bottom: 10px; background: #333; border: none; color: #eee; }
        button { background-color: #f44336; color: white; border: none; padding: 10px 15px; cursor: pointer; }
        button:hover { background-color: #e53935; }
        .msg { margin-top: 15px; padding: 10px; background: #4caf50; color: white; }
    </style>
</head>
<body>
    <h1>Panel Admin Blacklist HWID</h1>

    {% if message %}
    <div class="msg">{{ message }}</div>
    {% endif %}

    <h2>Blacklist actuelle</h2>
    <table>
        <tr><th>HWID</th><th>Raison</th><th>Action</th></tr>
        {% for row in blacklist %}
        <tr>
            <td>{{ row.hwid }}</td>
            <td>{{ row.reason }}</td>
            <td>
                <form method="POST" action="{{ url_for('remove_blacklist_web') }}" style="display:inline;">
                    <input type="hidden" name="hwid" value="{{ row.hwid }}">
                    <button type="submit">Supprimer</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>

    <h2>Ajouter HWID à la blacklist</h2>
    <form method="POST" action="{{ url_for('add_blacklist_web') }}">
        <input type="text" name="hwid" placeholder="HWID" required>
        <textarea name="reason" placeholder="Raison (optionnelle)"></textarea>
        <button type="submit">Ajouter</button>
    </form>
</body>
</html>
"""

@app.route('/admin', methods=['GET'])
@requires_auth
def admin_panel():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT hwid, reason FROM blacklist ORDER BY hwid')
    blacklist = cursor.fetchall()
    return render_template_string(ADMIN_PANEL_HTML, blacklist=blacklist, message=None)

@app.route('/admin/add', methods=['POST'])
@requires_auth
def add_blacklist_web():
    hwid = request.form.get('hwid')
    reason = request.form.get('reason', 'Non spécifiée')
    message = None

    if not hwid:
        message = "HWID manquant."
    else:
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO blacklist (hwid, reason) VALUES (?, ?)', (hwid, reason))
            db.commit()
            log_blacklist_event(hwid, reason, username=request.authorization.username)
            message = f"HWID {hwid} ajouté à la blacklist."
        except sqlite3.IntegrityError:
            message = f"HWID {hwid} est déjà blacklisté."

    cursor.execute('SELECT hwid, reason FROM blacklist ORDER BY hwid')
    blacklist = cursor.fetchall()
    return render_template_string(ADMIN_PANEL_HTML, blacklist=blacklist, message=message)

@app.route('/admin/remove', methods=['POST'])
@requires_auth
def remove_blacklist_web():
    hwid = request.form.get('hwid')
    message = None
    if not hwid:
        message = "HWID manquant."
    else:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM blacklist WHERE hwid = ?', (hwid,))
        db.commit()
        log_blacklist_event(hwid, "Retiré de la blacklist", username=request.authorization.username)
        message = f"HWID {hwid} retiré de la blacklist."

    cursor.execute('SELECT hwid, reason FROM blacklist ORDER BY hwid')
    blacklist = cursor.fetchall()
    return render_template_string(ADMIN_PANEL_HTML, blacklist=blacklist, message=message)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
