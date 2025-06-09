from flask import Flask, request, jsonify, render_template, Response
import sqlite3
import os
from functools import wraps
from base64 import b64decode

app = Flask(__name__)
DB_PATH = 'database.db'

# Init DB
def init_db():
    if not os.path.exists(DB_PATH):
        with sqlite3.connect(DB_PATH) as conn:
            with open('schema.sql', 'r') as f:
                conn.executescript(f.read())
init_db()

# Auth
def check_auth(auth_header):
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    decoded = b64decode(auth_header.split(" ")[1]).decode()
    username, password = decoded.split(":")
    return username == "admin" and password == "password"

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not check_auth(request.headers.get("Authorization")):
            return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login required"'})
        return f(*args, **kwargs)
    return decorated

@app.route("/check", methods=["GET"])
def check():
    hwid = request.args.get("hwid")
    if not hwid:
        return jsonify({"error": "Missing hwid"}), 400
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT reason FROM blacklist WHERE hwid = ?", (hwid,))
        row = cur.fetchone()
    if row:
        return jsonify({"blacklisted": True, "reason": row[0]})
    return jsonify({"blacklisted": False})

@app.route("/add", methods=["POST"])
@requires_auth
def add():
    data = request.json
    hwid = data.get("hwid")
    reason = data.get("reason", "No reason provided")
    if not hwid:
        return jsonify({"error": "Missing hwid"}), 400
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO blacklist (hwid, reason) VALUES (?, ?)", (hwid, reason))
        conn.commit()
    return jsonify({"status": "added", "hwid": hwid})

@app.route("/remove", methods=["POST"])
@requires_auth
def remove():
    data = request.json
    hwid = data.get("hwid")
    if not hwid:
        return jsonify({"error": "Missing hwid"}), 400
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM blacklist WHERE hwid = ?", (hwid,))
        conn.commit()
    return jsonify({"status": "removed", "hwid": hwid})

@app.route("/admin")
@requires_auth
def admin():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT hwid, reason FROM blacklist ORDER BY hwid")
        entries = cur.fetchall()
    return render_template("admin.html", entries=entries)

if __name__ == "__main__":
    app.run(debug=True)
