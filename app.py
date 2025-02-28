from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
from datetime import datetime
import hashlib
import os
import time
import json
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set up logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO)
handler = RotatingFileHandler(
    'logs/app.log', 
    maxBytes=1024 * 1024,  # 1MB
    backupCount=5
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(handler)

# Database functions
def create_connection():
    conn = sqlite3.connect('messages.db', check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging for better concurrency
    return conn

def create_tables():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender TEXT,
                        receiver TEXT,
                        message TEXT,
                        timestamp DATETIME)''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Routes
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('messaging'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?",
                      (username, hash_password(password)))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['username'] = username
            return redirect(url_for('messaging'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            conn = create_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                          (username, hash_password(password)))
            conn.commit()
            conn.close()
            session['username'] = username
            return redirect(url_for('messaging'))
        except sqlite3.IntegrityError:
            return render_template('signup.html', error='Username taken')
    return render_template('signup.html')

@app.route('/stream')
def stream():
    username = request.args.get('username')
    if not username:
        app.logger.error(f"Stream request without username")
        return {'status': 'error', 'message': 'Username is required'}, 400

    def event_stream():
        last_id = 0
        while True:
            try:
                conn = create_connection()
                cursor = conn.cursor()
                cursor.execute('''SELECT id, sender, receiver, message, timestamp FROM messages
                                WHERE id > ? AND (receiver = ? OR sender = ?)
                                ORDER BY timestamp ASC''',
                             (last_id, username, username))
                messages = cursor.fetchall()
                conn.close()

                for msg in messages:
                    last_id = msg[0]
                    data = {
                        'sender': msg[1],
                        'receiver': msg[2],
                        'message': msg[3],
                        'timestamp': msg[4]
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                time.sleep(0.5)
            except Exception as e:
                app.logger.error(f"Stream error for user {username}: {str(e)}")
                time.sleep(1)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

@app.route('/get_user_messages/<username>')
def get_user_messages(username):
    if 'username' not in session:
        return {'status': 'error'}, 401
    user = session['username']
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT sender, receiver, message, timestamp FROM messages
                    WHERE (receiver = ? AND sender = ?)
                    OR (receiver = ? AND sender = ?)
                    ORDER BY timestamp ASC''', 
                 (user, username, username, user))
    messages = [{
        'sender': msg[0],
        'receiver': msg[1],
        'message': msg[2],
        'timestamp': msg[3],
        'direction': 'sent' if msg[0] == user else 'received'
    } for msg in cursor.fetchall()]
    conn.close()
    return {'messages': messages}

@app.route('/messages')
def messaging():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('messages.html', username=session['username'])

@app.route('/send', methods=['POST'])
def send_message():
    if 'username' not in session:
        return {'status': 'error'}, 401
    sender = session['username']
    data = request.json
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO messages (sender, receiver, message, timestamp)
                    VALUES (?, ?, ?, ?)''',
                 (sender, data['receiver'], data['message'], datetime.now()))
    conn.commit()
    conn.close()
    return {'status': 'success'}

@app.route('/get_users')
def get_users():
    if 'username' not in session:
        return {'status': 'error'}, 401
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE username != ?",
                 (session['username'],))
    users = [u[0] for u in cursor.fetchall()]
    conn.close()
    return {'users': users}

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    create_tables()
    app.logger.info('Application startup: Database tables created')
    # Run with standard Flask development server
    app.run(host='0.0.0.0', port=5000, debug=True)