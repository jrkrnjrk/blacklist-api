from flask import Flask, request, jsonify, g, render_template_string, Response
import sqlite3
from functools import wraps
import requests
import os

DATABASE = 'blacklist.db'

app = Flask(__name__)

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

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    if not os.path.isfile(DATABASE):
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

LOG_WEBHOOK_URL = "https://discord.com/api/webhooks/1381357433435324548/8Ui-kZ2oZDGrOEHRkOh2JS1mGczYQdIpxJuPX5XTfYiNNNu7Ey4EMZuEIjGMKZAyyWbn"

def log_blacklist_event(hwid, reason, username=None):
    content = f"⛔ **Blacklist update**\nHWID: `{hwid}`\nRaison: {reason}"
    if username:
        content += f"\nExécuté par: {username}"
    try:
        requests.post(LOG_WEBHOOK_URL, json={"content": content})
    except Exception as e:
        print(f"Erreur webhook: {e}")

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

ADMIN_PANEL_HTML = """<!DOCTYPE html>
<html>
<head><title>Panel Admin Blacklist HWID</title></head>
<body><h1>Admin Panel</h1></body>
</html>"""

@app.route('/admin', methods=['GET'])
@requires_auth
def admin_panel():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT hwid, reason FROM blacklist ORDER BY hwid')
    blacklist = cursor.fetchall()
    return render_template_string(ADMIN_PANEL_HTML, blacklist=blacklist, message=None)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
