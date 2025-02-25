from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
from datetime import datetime
import hashlib
import os
import time
import json
from gevent import monkey
from gevent.pywsgi import WSGIServer

monkey.patch_all()  # Needed for async SSE support

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a secure secret key

# Add CORS support
from flask_cors import CORS
CORS(app)

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
    username = request.args.get('username')  # Get username from query parameter
    if not username:
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
                time.sleep(0.5)  # Reduce sleep time
            except Exception as e:
                print(f"Error in SSE stream: {str(e)}")
                time.sleep(1)  # Reconnect delay

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
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
    # Use production server
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    http_server.serve_forever()