from flask import Flask, request, jsonify, Response, g
import sqlite3
import os
from functools import wraps

app = Flask(__name__)
DATABASE = 'blacklist.db'

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hwid TEXT UNIQUE NOT NULL,
                reason TEXT NOT NULL
            )
        ''')
        db.commit()

def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    return Response(
        'Authentication required', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@app.route('/check')
def check():
    hwid = request.args.get('hwid', '')
    if not hwid:
        return jsonify({'error': 'hwid param missing'}), 400

    cursor = get_db().cursor()
    cursor.execute('SELECT reason FROM blacklist WHERE hwid = ?', (hwid,))
    row = cursor.fetchone()
    if row:
        return jsonify({'blacklisted': True, 'reason': row['reason']})
    else:
        return jsonify({'blacklisted': False})

@app.route('/admin/blacklist/add', methods=['POST'])
@requires_auth
def add_hwid():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    hwid = data.get('hwid')
    reason = data.get('reason')

    if not hwid or not reason:
        return jsonify({'error': 'hwid and reason are required'}), 400

    try:
        cursor = get_db().cursor()
        cursor.execute("INSERT INTO blacklist (hwid, reason) VALUES (?, ?)", (hwid, reason))
        get_db().commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'HWID already blacklisted'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'message': 'HWID added to blacklist', 'hwid': hwid, 'reason': reason}), 201

@app.route('/admin')
@requires_auth
def admin_panel():
    cursor = get_db().cursor()
    cursor.execute('SELECT hwid, reason FROM blacklist ORDER BY hwid')
    rows = cursor.fetchall()

    html = "<h1>Blacklist Admin Panel</h1><ul>"
    for row in rows:
        html += f"<li>{row['hwid']} - {row['reason']}</li>"
    html += "</ul>"
    return html

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=10000)
