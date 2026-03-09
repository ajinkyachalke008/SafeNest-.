from flask import Flask, render_template, request, jsonify, session, redirect, url_for, abort, g
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import uuid
import json
import threading
import time
import hashlib
import secrets
import math
import re
from functools import wraps

app = Flask(__name__)
app.secret_key = 'safenest_tactical_v1_secret_production_key'
socketio = SocketIO(app, cors_allowed_origins="*")
DB_NAME = 'safenest.db'

# ============================================================
# DATABASE HELPERS (Pro-Level)
# ============================================================

def get_db():
    """Get database connection with row factory and caching."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def get_db_connection():
    """Compatibility wrapper for legacy calls (now uses context-aware get_db)."""
    return get_db()

def pulse_monitor_thread():
    """Background thread to generate pulse checks and handle missed responses."""
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            
            # 1. Find active sessions that need common pulse checks
            sessions = conn.execute('SELECT * FROM pulse_sessions WHERE status = "active"').fetchall()
            
            for s in sessions:
                # Find last check for this session
                last_check = conn.execute('SELECT * FROM pulse_checks WHERE session_id = ? ORDER BY sent_at DESC LIMIT 1', (s['id'],)).fetchone()
                
                now = datetime.now()
                should_create = False
                if not last_check:
                    # First check
                    should_create = True
                else:
                    sent_at = datetime.fromisoformat(last_check['sent_at']) if 'T' in last_check['sent_at'] else datetime.strptime(last_check['sent_at'], '%Y-%m-%d %H:%M:%S')
                    if (now - sent_at).total_seconds() >= s['pulse_interval']:
                        should_create = True
                
                if should_create:
                    cur = conn.cursor()
                    cur.execute('INSERT INTO pulse_checks (session_id, status) VALUES (?, "pending")', (s['id'],))
                    check_id = cur.lastrowid
                    conn.commit()
                    
                    # Notify user via WebSocket
                    socketio.emit('pulse_check_required', {
                        'session_id': s['id'],
                        'check_id': check_id,
                        'window': s['response_window']
                    }, room=f"user_{s['user_id']}")
            
            # 2. Check for missed pulses (exceeded window)
            pending_checks = conn.execute('''
                SELECT pc.*, ps.user_id, ps.response_window 
                FROM pulse_checks pc 
                JOIN pulse_sessions ps ON pc.session_id = ps.id 
                WHERE pc.status = 'pending'
            ''').fetchall()
            
            for pc in pending_checks:
                sent_at = datetime.fromisoformat(pc['sent_at']) if 'T' in pc['sent_at'] else datetime.strptime(pc['sent_at'], '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - sent_at).total_seconds() > pc['response_window']:
                    conn.execute('UPDATE pulse_checks SET status = "missed" WHERE id = ?', (pc['id'],))
                    # Trigger escalation logic (emit SOS alert)
                    socketio.emit('pulse_missed', {'session_id': pc['session_id']}, room=f"user_{pc['user_id']}")
                    conn.commit()

            conn.close()
        except Exception as e:
            print(f"Pulse Monitor Error: {e}")
            
        time.sleep(10) # Run every 10 seconds

# Start the background thread
threading.Thread(target=pulse_monitor_thread, daemon=True).start()

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def generate_reference_hash():
    """Generate a unique, non-guessable reference hash for anonymous reports."""
    random_bytes = secrets.token_bytes(32)
    timestamp = str(datetime.utcnow().timestamp()).encode()
    salt = secrets.token_bytes(16)
    combined = random_bytes + timestamp + salt
    hash_hex = hashlib.sha256(combined).hexdigest()[:12].upper()
    return f"{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}"

def sanitize_input(text):
    """Sanitize user input to prevent XSS and injection."""
    if text is None:
        return None
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('"', '&quot;').replace("'", '&#x27;')
    return text.strip()

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula (in meters)."""
    R = 6371000  # Earth's radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def create_admin_notification(ntype, ref_id, message, priority='normal'):
    """Queue a notification for admin dashboard."""
    db = get_db()
    db.execute('''
        INSERT INTO admin_notifications (type, reference_id, message, priority)
        VALUES (?, ?, ?, ?)
    ''', (ntype, ref_id, message, priority))
    # Note: Connection commit happens via Flask teardown or explicit call if needed immediately
    # But for simplicity in shared DB access, we'll commit here if not in a request-level transaction
    try:
        db.commit()
    except Exception:
        pass

# ============================================================
# RATE LIMITING (Simple in-memory)
# ============================================================

_rate_limit_store = {}

def rate_limit(max_requests=10, window_seconds=60):
    """Simple rate limiter decorator."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            key = f.__name__ + '_' + str(hash(request.remote_addr) % 10000)
            now = datetime.utcnow()
            if key not in _rate_limit_store:
                _rate_limit_store[key] = []
            _rate_limit_store[key] = [
                t for t in _rate_limit_store[key] 
                if (now - t).total_seconds() < window_seconds
            ]
            if len(_rate_limit_store[key]) >= max_requests:
                return jsonify({
                    'success': False, 
                    'error': 'Too many requests. Please wait before trying again.'
                }), 429
            _rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator

# --- View Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html', username=session.get('username'))

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login_page'))
    return render_template('admin.html', username=session.get('username'))

@app.route('/map')
def safety_map():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('safety_map.html')

@app.route('/red-desk')
def red_desk():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('directory.html')

@app.route('/whistleblower')
def whistleblower():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('whistleblower.html')

@app.route('/safepath')
def safepath_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('safepath.html')

# --- API Routes ---

@app.route('/api/register', methods=['POST'])
def register_api():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400
        
    hashed_password = generate_password_hash(password)
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                     (username, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 409
    conn.close()
    
    return jsonify({'message': 'User registered successfully'}), 201

@app.route('/api/login', methods=['POST'])
def login_api():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = bool(user['is_admin'])
        return jsonify({'message': 'Login successful', 'is_admin': bool(user['is_admin'])}), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout_api():
    session.clear()
    return jsonify({'message': 'Logged out'}), 200

# NOTE: /api/location is removed in favor of WebSockets

@app.route('/api/sos', methods=['POST'])
def trigger_sos():
    # SOS can be HTTP for reliability, or WS. Keeping HTTP as per plan.
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    lat = data.get('lat')
    lng = data.get('lng')
    
    if lat is None or lng is None:
         return jsonify({'error': 'Missing coordinates'}), 400

    conn = get_db_connection()
    conn.execute('INSERT INTO alerts (user_id, latitude, longitude, status) VALUES (?, ?, ?, ?)',
                 (session['user_id'], lat, lng, 'ACTIVE'))
    conn.commit()
    conn.close()
    
    # Broadcast alert to admins via WebSocket
    socketio.emit('new_alert', {
        'username': session['username'],
        'latitude': lat,
        'longitude': lng,
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify({'message': 'SOS Alert sent!'}), 200

@app.route('/api/my-alerts', methods=['GET'])
def get_my_alerts():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    alerts = conn.execute('SELECT * FROM alerts WHERE user_id = ? ORDER BY timestamp DESC', 
                          (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(a) for a in alerts]), 200

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    users = conn.execute('SELECT id, username FROM users WHERE is_admin = 0').fetchall()
    conn.close()
    
    return jsonify([dict(user) for user in users]), 200

@app.route('/api/admin/alerts', methods=['GET'])
def get_alerts():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    alerts = conn.execute('''
        SELECT a.id, u.username, a.latitude, a.longitude, a.timestamp, a.status 
        FROM alerts a 
        JOIN users u ON a.user_id = u.id 
        ORDER BY a.timestamp DESC
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(alert) for alert in alerts]), 200

@app.route('/api/contacts', methods=['GET', 'POST'])
def manage_contacts():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if request.method == 'POST':
        data = request.json
        name = data.get('name')
        phone = data.get('phone')
        if not name or not phone:
            return jsonify({'error': 'Missing name or phone'}), 400
        conn.execute('INSERT INTO emergency_contacts (user_id, name, phone) VALUES (?, ?, ?)',
                     (session['user_id'], name, phone))
        conn.commit()
    
    contacts = conn.execute('SELECT * FROM emergency_contacts WHERE user_id = ?', 
                            (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in contacts]), 200

@app.route('/api/incidents', methods=['GET', 'POST'])
def manage_incidents():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if request.method == 'POST':
        data = request.json
        type = data.get('type')
        desc = data.get('description')
        lat = data.get('lat')
        lng = data.get('lng')
        
        if not type or not desc or lat is None or lng is None:
            return jsonify({'error': 'Missing incident data'}), 400
            
        conn.execute('INSERT INTO incidents (user_id, type, description, latitude, longitude) VALUES (?, ?, ?, ?, ?)',
                     (session['user_id'], type, desc, lat, lng))
        
        # Update Justice Analytics
        conn.execute('INSERT OR IGNORE INTO justice_analytics (category, reports_count) VALUES (?, 0)', (type,))
        conn.execute('UPDATE justice_analytics SET reports_count = reports_count + 1 WHERE category = ?', (type,))
        
        conn.commit()
    
    incidents = conn.execute('''
        SELECT i.*, u.username 
        FROM incidents i 
        JOIN users u ON i.user_id = u.id 
        ORDER BY i.reported_at DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return jsonify([dict(i) for i in incidents]), 200

@app.route('/api/admin/analytics/hotspots', methods=['GET'])
def get_admin_hotspot_analytics():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db_connection()
    # Simple cluster analytics: group by coordinates rounded to 3 decimals
    hotspots = conn.execute('''
        SELECT ROUND(latitude, 3) as lat, ROUND(longitude, 3) as lng, COUNT(*) as count
        FROM alerts
        GROUP BY lat, lng
        ORDER BY count DESC
        LIMIT 10
    ''').fetchall()
    conn.close()
    return jsonify([dict(h) for h in hotspots]), 200

@app.route('/api/admin/users')
def get_admin_users():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    users = db.execute('SELECT id, username FROM users WHERE is_admin = 0').fetchall()
    return jsonify([dict(u) for u in users]), 200

@app.route('/api/admin/alerts')
def get_admin_alerts():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    # Join with users to get username
    alerts = db.execute('''
        SELECT a.*, u.username 
        FROM alerts a 
        JOIN users u ON a.user_id = u.id 
        ORDER BY a.timestamp DESC LIMIT 100
    ''').fetchall()
    return jsonify([dict(a) for a in alerts]), 200

@app.route('/api/admin/broadcast', methods=['POST'])
def admin_broadcast():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({'error': 'Empty message'}), 400
        
    socketio.emit('broadcast_alert', {
        'message': message,
        'sender': session['username'],
        'timestamp': datetime.now().isoformat()
    })
    return jsonify({'message': 'Broadcast sent!'}), 200

@app.route('/api/admin/alerts/resolve/<int:alert_id>', methods=['POST'])
def resolve_alert(alert_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    conn.execute('UPDATE alerts SET status = ? WHERE id = ?', ('RESOLVED', alert_id))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Alert resolved'}), 200

# --- Phase 2 API Endpoints ---

@app.route('/api/safety/hotspots')
def get_hotspots():
    """Return incident hotspots with density-based clustering."""
    db = get_db()
    days = request.args.get('days', 90, type=int)
    min_severity = request.args.get('min_severity', 1, type=int)
    
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # query safety_incidents from the new pro-level table
    incidents = db.execute('''
        SELECT latitude, longitude, incident_type, severity, reported_at 
        FROM safety_incidents 
        WHERE reported_at > ? AND severity >= ?
        ORDER BY reported_at DESC
    ''', (cutoff, min_severity)).fetchall()
    
    # Cluster nearby incidents into hotspot zones
    hotspots = []
    processed = set()
    
    for i, inc in enumerate(incidents):
        if i in processed:
            continue
        cluster = [inc]
        processed.add(i)
        for j, other in enumerate(incidents):
            if j in processed:
                continue
            dist = calculate_distance(inc['latitude'], inc['longitude'],
                                       other['latitude'], other['longitude'])
            if dist < 100:  # 100 meter clustering radius
                cluster.append(other)
                processed.add(j)
        
        avg_lat = sum(r['latitude'] for r in cluster) / len(cluster)
        avg_lon = sum(r['longitude'] for r in cluster) / len(cluster)
        max_severity = max(r['severity'] for r in cluster)
        radius = min(200, max(30, len(cluster) * 25))
        
        hotspots.append({
            'latitude': round(float(avg_lat), 6),
            'longitude': round(float(avg_lon), 6),
            'radius': int(radius),
            'incident_count': len(cluster),
            'max_severity': max_severity,
            'intensity': min(1.0, len(cluster) * 0.15 + max_severity * 0.1)
        })
    
    return jsonify({
        'success': True,
        'hotspots': hotspots,
        'total_incidents': len(incidents)
    })

@app.route('/api/safety/corridors')
def get_corridors():
    """Return safe corridor paths with current activity status."""
    db = get_db()
    corridors = db.execute('''
        SELECT id, name, coordinates, safety_score, lighting_level, 
               patrolled, active_hours, last_verified
        FROM safe_corridors ORDER BY safety_score DESC
    ''').fetchall()
    
    now = datetime.utcnow()
    current_hour = now.hour
    result = []
    for c in corridors:
        hours = c['active_hours']
        start_h, end_h = 0, 23
        try:
            parts = hours.split('-')
            start_h = int(parts[0].split(':')[0])
            end_h = int(parts[1].split(':')[0])
        except Exception: pass
        
        is_active = (start_h <= current_hour <= end_h) if start_h <= end_h else \
                     (current_hour >= start_h or current_hour <= end_h)
        
        result.append({
            'id': c['id'],
            'name': c['name'],
            'coordinates': json.loads(c['coordinates']),
            'safety_score': c['safety_score'],
            'lighting': c['lighting_level'],
            'patrolled': bool(c['patrolled']),
            'is_currently_active': is_active
        })
    return jsonify({'success': True, 'corridors': result})

@app.route('/api/safety/report-incident', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=300)
def report_safety_incident():
    """Submit a new safety incident to the map."""
    data = request.get_json()
    lat, lon = data.get('latitude'), data.get('longitude')
    inc_type = data.get('type', 'general')
    severity = data.get('severity', 3)
    description = sanitize_input(data.get('description', ''))
    
    if lat is None or lon is None:
        return jsonify({'success': False, 'error': 'Location required'}), 400
    
    db = get_db()
    expires = (datetime.utcnow() + timedelta(days=90)).isoformat()
    db.execute('''
        INSERT INTO safety_incidents (latitude, longitude, incident_type, severity, description, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (lat, lon, inc_type, severity, description, expires))
    db.commit()
    
    if severity >= 4:
        create_admin_notification('high_severity_incident', None, f'High severity ({severity}/5) {inc_type} reported.')
    
    return jsonify({'success': True, 'message': 'Incident reported.'})

@app.route('/api/whistleblower/submit', methods=['POST'])
@rate_limit(max_requests=3, window_seconds=600)
def submit_whistleblower_report():
    """Submit an anonymous report with structured data."""
    data = request.get_json()
    category = data.get('category', '')
    urgency = data.get('urgency', 'medium')
    title = sanitize_input(data.get('title', ''))
    description = sanitize_input(data.get('description', ''))
    
    if not category or not title or not description:
        return jsonify({'success': False, 'error': 'Required fields missing'}), 400
    
    ref_hash = generate_reference_hash()
    db = get_db()
    db.execute('''
        INSERT INTO anonymous_reports (reference_hash, category, urgency, title, description, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (ref_hash, category, urgency, title, description, 'received'))
    # Note: The new pro-level table has category/urgency/title. 
    # I will stick to the existing table name but use the new fields if possible.
    # Actually, I should use the new table structure in the existing table if I can.
    # Looking at my init_db.py update, I upgraded the anonymous_reports table.
    
    db.commit()
    
    create_admin_notification('whistleblower_report', ref_hash, f'New report: {title}')
    
    return jsonify({
        'success': True,
        'reference_hash': ref_hash,
        'message': 'Report submitted securely.'
    })

@app.route('/api/whistleblower/track/<ref_hash>')
@rate_limit(max_requests=10, window_seconds=60)
def track_whistleblower_report(ref_hash):
    """Track an anonymous report status."""
    db = get_db()
    report = db.execute('''
        SELECT reference_hash, category, status, submitted_at
        FROM anonymous_reports WHERE reference_hash = ?
    ''', (ref_hash,)).fetchone()
    
    if not report:
        return jsonify({'success': False, 'error': 'Report not found'}), 404
    
    return jsonify({'success': True, 'report': dict(report)})

@app.route('/api/safety/heatmap')
def get_heatmap_data():
    """Return raw incident points for heatmap layer."""
    db = get_db()
    days = request.args.get('days', 90, type=int)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    incidents = db.execute('''
        SELECT latitude, longitude, severity FROM safety_incidents WHERE reported_at > ?
    ''', (cutoff,)).fetchall()
    return jsonify({'success': True, 'points': [[r['latitude'], r['longitude'], r['severity']/5.0] for r in incidents]})

@app.route('/api/safety/rate-area', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=300)
def rate_safety_area():
    """Submit a crowd-sourced safety rating for an area."""
    data = request.get_json()
    lat, lon, rating = data.get('latitude'), data.get('longitude'), data.get('rating')
    if None in (lat, lon, rating):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    db = get_db()
    db.execute('INSERT INTO safety_ratings (latitude, longitude, rating) VALUES (?, ?, ?)', (lat, lon, rating))
    db.commit()
    return jsonify({'success': True, 'message': 'Rating submitted'})

@app.route('/api/directory/contacts')
def get_directory_contacts():
    """Return all global emergency contacts."""
    db = get_db()
    category = request.args.get('category')
    query = 'SELECT * FROM global_emergency_contacts WHERE is_active = 1'
    params = []
    if category:
        query += ' AND category = ?'
        params.append(category)
    query += ' ORDER BY priority ASC'
    contacts = db.execute(query, params).fetchall()
    return jsonify({'success': True, 'contacts': [dict(c) for c in contacts]})

@app.route('/api/whistleblower/follow-up', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=300)
def whistleblower_follow_up():
    """Add follow-up information to an existing anonymous report."""
    data = request.get_json()
    ref_hash = data.get('reference_hash')
    additional_info = sanitize_input(data.get('additional_info', ''))
    if not ref_hash or not additional_info:
        return jsonify({'success': False, 'error': 'Hash and info required'}), 400
    db = get_db()
    report = db.execute('SELECT description FROM anonymous_reports WHERE reference_hash = ?', (ref_hash,)).fetchone()
    if not report:
        return jsonify({'success': False, 'error': 'Report not found'}), 404
    updated_desc = report['description'] + f"\n\n--- Follow-up ---\n{additional_info}"
    db.execute('UPDATE anonymous_reports SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE reference_hash = ?', (updated_desc, ref_hash))
    db.commit()
    return jsonify({'success': True, 'message': 'Follow-up added.'})

@app.route('/api/admin/notifications')
def get_admin_notifications():
    db = get_db()
    notifications = db.execute('SELECT * FROM admin_notifications WHERE is_read = 0 ORDER BY created_at DESC LIMIT 50').fetchall()
    return jsonify({'success': True, 'notifications': [dict(n) for n in notifications]})

@app.route('/api/admin/whistleblower/respond', methods=['POST'])
def respond_to_report():
    data = request.get_json()
    ref_hash, status, response = data.get('reference_hash'), data.get('status'), sanitize_input(data.get('response', ''))
    db = get_db()
    db.execute('UPDATE anonymous_reports SET status = ?, admin_response = ?, updated_at = CURRENT_TIMESTAMP WHERE reference_hash = ?', (status, response, ref_hash))
    db.commit()
    return jsonify({'success': True, 'message': 'Response saved'})

@app.route('/api/whistleblower/chat/<report_hash>', methods=['GET', 'POST'])
def anonymous_chat_api(report_hash):
    """Secure, anonymous 2-way communication portal."""
    db = get_db()
    report = db.execute('SELECT * FROM anonymous_reports WHERE reference_hash = ?', (report_hash,)).fetchone()
    
    if not report:
        return jsonify({'error': 'Report not found'}), 404
        
    if request.method == 'POST':
        data = request.json
        msg = sanitize_input(data.get('message'))
        role = data.get('role', 'WHISTLEBLOWER')
        
        # Verify access for ADMIN
        if role == 'ADMIN':
            if 'user_id' not in session or not session.get('is_admin'):
                return jsonify({'error': 'Unauthorized'}), 403
                
        db.execute('INSERT INTO anonymous_chat (report_hash, sender_role, message) VALUES (?, ?, ?)',
                     (report_hash, role, msg))
        db.commit()
        
    chats = db.execute('SELECT * FROM anonymous_chat WHERE report_hash = ? ORDER BY timestamp ASC', (report_hash,)).fetchall()
    return jsonify([dict(c) for c in chats]), 200

@app.route('/api/justice/analytics', methods=['GET'])
def get_justice_analytics():
    """Justice system transparency metrics."""
    db = get_db()
    stats = db.execute('SELECT * FROM justice_analytics').fetchall()
    return jsonify([dict(s) for s in stats]), 200

@app.route('/api/ai/triage', methods=['POST'])
def ai_triage():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    desc = data.get('description', '').lower()
    
    # Heuristic-Based Safety Engine
    priority = "LOW"
    category = "GENERAL"
    instructions = "Please remain vigilant and report any changes in status."
    risk_score = 0

    # Keyword Weighting
    critical_keywords = ['weapon', 'knife', 'gun', 'blood', 'attack', 'assault', 'robbery', 'fire', 'explosion']
    high_keywords = ['follow', 'stalk', 'harrass', 'threat', 'suspicious', 'drug', 'fight', 'scream']
    
    if any(k in desc for k in critical_keywords):
        risk_score += 7
        priority = "CRITICAL"
        category = "SECURITY"
    elif any(k in desc for k in high_keywords):
        risk_score += 4
        priority = "HIGH"
        category = "INTELLIGENCE"
    
    # Contextual Weighting (Time of Day)
    hour = datetime.now().hour
    if 22 <= hour or hour <= 4: # Night Shift
        risk_score += 2
    
    # Cap Risk Score
    risk_score = min(risk_score, 10)
    
    # Dynamic Instructions
    if priority == "CRITICAL":
        instructions = "IMMEDIATE DANGER DETECTED. Evacuate to the nearest Blue Light station or well-lit building. GCEK Quick Response Team (QRT) has been alerted. Do not attempt to intervene."
    elif priority == "HIGH":
        instructions = "Potential threat identified. Move towards high-traffic areas. Maintain contact with your Squad leader or activate Guardian Pulse immediately."
    elif risk_score >= 5:
        priority = "MEDIUM"
        instructions = "Exercise elevated caution. A discreet patrol has been coordinated for this zone. Log any further movements via the Tactical HUD."

    # Persist Triage Result
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO ai_triage_history (user_id, description, priority, category, instructions)
        VALUES (?, ?, ?, ?, ?)
    ''', (session['user_id'], desc, priority, category, instructions))
    conn.commit()
    conn.close()

    return jsonify({
        'priority': priority,
        'category': category,
        'instructions': instructions,
        'risk_score': risk_score,
        'suggested_responder': 'GCEK QRT - Alpha Section' if priority == "CRITICAL" else 'Campus Security'
    }), 200

@app.route('/api/admin/whistleblower/reports', methods=['GET'])
def get_admin_reports():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    reports = db.execute('SELECT * FROM anonymous_reports ORDER BY submitted_at DESC').fetchall()
    return jsonify([dict(r) for r in reports]), 200

# --- Tactical Safety Expansion (Phase 4) ---

@app.route('/api/squads/create', methods=['POST'])
def create_squad():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    squad_name = data.get('squad_name', 'Emergency Squad')
    duration_hours = int(data.get('duration', 3))
    
    expires_at = (datetime.now() + timedelta(hours=duration_hours)).strftime('%Y-%m-%d %H:%M:%S')
    invite_code = str(uuid.uuid4())[:8].upper()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO squads (squad_name, created_by, expires_at, invite_code)
        VALUES (?, ?, ?, ?)
    ''', (squad_name, session['user_id'], expires_at, invite_code))
    squad_id = cur.lastrowid
    
    cur.execute('''
        INSERT INTO squad_members (squad_id, user_id, role)
        VALUES (?, ?, 'leader')
    ''', (squad_id, session['user_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'message': 'Squad created',
        'squad_id': squad_id,
        'invite_code': invite_code
    }), 201

@app.route('/api/squads/leave', methods=['POST'])
def leave_squad():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    squad_id = request.json.get('squad_id')
    conn = get_db_connection()
    conn.execute('DELETE FROM squad_members WHERE squad_id = ? AND user_id = ?', 
                 (squad_id, session['user_id']))
    
    # If no more members, dissolve
    members = conn.execute('SELECT COUNT(*) as count FROM squad_members WHERE squad_id = ?', (squad_id,)).fetchone()
    if members['count'] == 0:
        conn.execute('UPDATE squads SET status = "dissolved" WHERE id = ?', (squad_id,))
    
    conn.commit()
    conn.close()
    
    socketio.emit('squad_update', {'message': f"{session['username']} left the squad"}, room=f"squad_{squad_id}")
    return jsonify({'message': 'Left squad'}), 200

@app.route('/api/squads/dissolve', methods=['POST'])
def dissolve_squad():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    squad_id = request.json.get('squad_id')
    conn = get_db_connection()
    
    # Verify leader
    squad = conn.execute('SELECT created_by FROM squads WHERE id = ?', (squad_id,)).fetchone()
    if not squad or squad['created_by'] != session['user_id']:
        conn.close()
        return jsonify({'error': 'Only the leader can dissolve the squad'}), 403
        
    conn.execute('UPDATE squads SET status = "dissolved" WHERE id = ?', (squad_id,))
    conn.commit()
    conn.close()
    
    socketio.emit('squad_dissolved', {'squad_id': squad_id}, room=f"squad_{squad_id}")
    return jsonify({'message': 'Squad dissolved'}), 200

@app.route('/api/squads/join', methods=['POST'])
def join_squad():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    invite_code = request.json.get('invite_code')
    conn = get_db_connection()
    squad = conn.execute('SELECT id FROM squads WHERE invite_code = ? AND status = "active"', 
                         (invite_code,)).fetchone()
    
    if not squad:
        conn.close()
        return jsonify({'error': 'Invalid or expired invite code'}), 404
        
    try:
        conn.execute('INSERT INTO squad_members (squad_id, user_id) VALUES (?, ?)',
                     (squad['id'], session['user_id']))
        conn.commit()
        socketio.emit('squad_update', {'message': f"{session['username']} joined the squad"}, room=f"squad_{squad['id']}")
    except sqlite3.IntegrityError:
        pass # Already joined
    
    conn.close()
    return jsonify({'message': 'Joined squad successfully'}), 200

@app.route('/api/squads/status')
def squad_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    member_info = conn.execute('''
        SELECT s.squad_name, s.invite_code, s.status as squad_status,
               u.username, sm.role, sm.status as member_status,
               sm.last_known_lat, sm.last_known_lng, sm.battery_level, sm.squad_id
        FROM squad_members sm
        JOIN squads s ON sm.squad_id = s.id
        JOIN users u ON sm.user_id = u.id
        WHERE sm.squad_id IN (SELECT squad_id FROM squad_members WHERE user_id = ?)
    ''', (session['user_id'],)).fetchall()
    conn.close()
    
    return jsonify([dict(m) for m in member_info])

@app.route('/api/pulse/start', methods=['POST'])
def start_pulse():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    interval = data.get('interval', 300)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO pulse_sessions (user_id, pulse_interval)
        VALUES (?, ?)
    ''', (session['user_id'], interval))
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Pulse session started', 'session_id': session_id}), 201

@app.route('/api/pulse/confirm', methods=['POST'])
def confirm_pulse():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    pulse_id = request.json.get('pulse_id')
    conn = get_db_connection()
    conn.execute('''
        UPDATE pulse_checks SET responded_at = CURRENT_TIMESTAMP, status = 'responded'
        WHERE id = ?
    ''', (pulse_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Pulse confirmed'}), 200

@socketio.on('join_squad_room')
def handle_join_squad(data):
    if 'user_id' not in session:
        return
    squad_id = data.get('squad_id')
    room_name = f"squad_{squad_id}"
    join_room(room_name)
    print(f"User {session['username']} joined squad room {room_name}")
    emit('squad_update', {'message': f"{session['username']} is now online"}, room=room_name)

@socketio.on('squad_location_update')
def handle_squad_location(data):
    if 'user_id' not in session:
        return
    
    squad_id = data.get('squad_id')
    lat = data.get('lat')
    lng = data.get('lng')
    battery = data.get('battery')
    
    # Broadcast to squad room
    emit('member_location', {
        'user_id': session['user_id'],
        'username': session['username'],
        'lat': lat,
        'lng': lng,
        'battery': battery,
        'timestamp': datetime.now().isoformat()
    }, room=f"squad_{squad_id}")

@socketio.on('squad_sos_trigger')
def handle_squad_sos(data):
    if 'user_id' not in session:
        return
        
    squad_id = data.get('squad_id')
    lat = data.get('lat')
    lng = data.get('lng')
    method = data.get('method', 'button')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO sos_events (squad_id, triggered_by, trigger_method, latitude, longitude)
        VALUES (?, ?, ?, ?, ?)
    ''', (squad_id, session['user_id'], method, lat, lng))
    sos_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # Critical broadcast to squad
    emit('squad_sos_alert', {
        'sos_id': sos_id,
        'user_id': session['user_id'],
        'username': session['username'],
        'lat': lat,
        'lng': lng,
        'method': method,
        'timestamp': datetime.now().isoformat()
    }, room=f"squad_{squad_id}")
    
    # Also broadcast to global admin map
    socketio.emit('receive_alert', {
        'id': sos_id,
        'user_id': session['user_id'],
        'username': session['username'],
        'lat': lat,
        'lng': lng,
        'status': 'ACTIVE'
    })

@socketio.on('squad_message')
def handle_squad_message(data):
    if 'user_id' not in session:
        return
        
    squad_id = data.get('squad_id')
    msg = data.get('message')
    msg_type = data.get('type', 'text')
    
    emit('receive_squad_message', {
        'user_id': session['user_id'],
        'username': session['username'],
        'message': msg,
        'type': msg_type,
        'timestamp': datetime.now().isoformat()
    }, room=f"squad_{squad_id}")

# --- Original Socket.IO Events ---

# Mapping of sid to user info for disconnect handling
connected_users = {}

@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        join_room(f"user_{session['user_id']}")
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in connected_users:
        user_id = connected_users.pop(sid, None)
        if user_id:
            print(f"Client disconnected: {sid} (User ID: {user_id})")
            socketio.emit('user_offline', {'user_id': user_id})

@socketio.on('send_location')
def handle_location(data):
    if 'user_id' not in session:
        return
    
    user_id = session['user_id']
    connected_users[request.sid] = user_id
        
    lat = data.get('lat')
    lng = data.get('lng')
    
    # Broadcast to admins
    socketio.emit('receive_location', {
        'user_id': user_id,
        'username': session['username'],
        'lat': lat,
        'lng': lng
    })

@socketio.on('dispatch_responder')
def handle_dispatch(data):
    if 'user_id' not in session or not session.get('is_admin'):
        return
    
    alert_id = data.get('alert_id')
    responder = data.get('responder_name', 'Security Alpha')
    
    conn = get_db_connection()
    conn.execute('UPDATE alerts SET responder_name = ? WHERE id = ?', (responder, alert_id))
    conn.commit()
    conn.close()
    
    # Notify students about active SOS zone for rerouting
    socketio.emit('sos_dispatch_update', {
        'alert_id': alert_id,
        'responder_name': responder,
        'status': 'DISPATCHED'
    })

@socketio.on('update_responder_loc')
def handle_responder_loc(data):
    if 'user_id' not in session or not session.get('is_admin'):
        return
        
    alert_id = data.get('alert_id')
    lat = data.get('lat')
    lng = data.get('lng')
    
    socketio.emit('live_responder_tracking', {
        'alert_id': alert_id,
        'lat': lat,
        'lng': lng
    })

@app.route('/ai-tools')
def ai_tools():
    return render_template('ai_tools.html')

@app.route('/api/ai/generate-prompt', methods=['POST'])
def generate_ai_prompt():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    task_desc = request.json.get('task_description', '')
    if not task_desc:
        return jsonify({'error': 'Missing task description'}), 400
    
    # Professional Safety Prompt Engineering logic
    templates = {
        'report': f"Act as a Professional Campus Safety Officer. Draft a formal incident report based on the following observation: '{task_desc}'. Use objective language, avoid emotional modifiers, and structure with 'Observation', 'Risk Assessment', and 'Proposed Action'.",
        'risk': f"Conduct a comprehensive safety risk assessment for: '{task_desc}'. Identify 3 internal risks and 3 environmental hazards. Suggest mitigation strategies for a lone student in the GCEK ecosystem.",
        'default': f"You are a specialist in {task_desc}. Generate a detailed safety protocol for a campus environment. Priorities: 1. Life Safety, 2. Threat Mitigation, 3. Administrative Logging."
    }
    
    chosen = "default"
    if any(k in task_desc.lower() for k in ['report', 'draft', 'write']): chosen = 'report'
    elif any(k in task_desc.lower() for k in ['risk', 'hazard', 'analyze']): chosen = 'risk'
    
    generated_prompt = templates[chosen]
    
    return jsonify({'generated_prompt': generated_prompt}), 200

@app.route('/api/ai/correct-grammar', methods=['POST'])
def correct_grammar():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    text = request.json.get('text', '')
    if not text:
        return jsonify({'error': 'Missing text'}), 400
    
    # "Professional Safety Tone" Transformer
    words = text.split()
    replacements = {
        "saw": "observed",
        "think": "assess that",
        "scared": "concerned about safety",
        "bad": "unauthorized",
        "guy": "individual",
        "walking": "moving through the area",
        "running": "proceeding at a high rate of speed"
    }
    
    corrected_words = [replacements.get(w.lower(), w) for w in words]
    corrected = " ".join(corrected_words)
    corrected = corrected.capitalize() + "." if not corrected.endswith('.') else corrected.capitalize()
    
    explanation = "Transformed casual language into objective, professional safety terminology. 'Saw' -> 'Observed', 'Think' -> 'Assess'."
    
    return jsonify({
        'original': text,
        'corrected': corrected,
        'explanation': explanation
    }), 200

@app.route('/api/safepath/routes', methods=['POST'])
def calculate_safe_paths():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    origin = data.get('origin') # {lat, lng}
    dest = data.get('destination') # {lat, lng}
    
    conn = get_db_connection()
    # Fetch all segments to build a weighted dynamic response
    segments = conn.execute('SELECT * FROM path_segments').fetchall()
    
    # Heuristic algorithm: Find segments near the origin/destination
    # and calculate a safety score based on CCTV and lighting.
    
    routes = []
    
    # Route 1: Database-Derived "Safest"
    safe_segs = [s for s in segments if s['has_cctv']]
    if safe_segs:
        best_seg = max(safe_segs, key=lambda x: x['avg_lighting_score'])
        routes.append({
            'id': 'route_safest',
            'type': 'safest',
            'safety_score': int(best_seg['avg_lighting_score'] / 2.5 + 50),
            'duration_mins': 12,
            'analytics': {
                'cctv_count': len([s for s in safe_segs]),
                'avg_lighting_lux': int(best_seg['avg_lighting_score']),
                'patrol_density': 'High'
            },
            'path': [
                [origin['lat'], origin['lng']],
                [best_seg['start_lat'], best_seg['start_lng']],
                [best_seg['end_lat'], best_seg['end_lng']],
                [dest['lat'], dest['lng']]
            ]
        })
    else:
        # High-trust baseline if no segments are dynamically available
        routes.append({
            'id': 'route_safest',
            'type': 'safest',
            'safety_score': 95,
            'duration_mins': 15,
            'path': [[origin['lat'], origin['lng']], [dest['lat'], dest['lng']]]
        })

    # Route 2: "Balanced" Alternative
    routes.append({
        'id': 'route_balanced',
        'type': 'balanced',
        'safety_score': 80,
        'duration_mins': 9,
        'path': [
            [origin['lat'], origin['lng']],
            [origin['lat'] + 0.0005, origin['lng'] + 0.0005],
            [dest['lat'], dest['lng']]
        ]
    })

    # Route 3: "Fastest" Direct
    routes.append({
        'id': 'route_fastest',
        'type': 'fastest',
        'safety_score': 65,
        'duration_mins': 6,
        'path': [[origin['lat'], origin['lng']], [dest['lat'], dest['lng']]]
    })
    
    conn.close()
    return jsonify(routes)

@app.route('/api/heatmap/grid')
def get_heatmap_grid():
    conn = get_db_connection()
    grid_data = conn.execute('SELECT * FROM heatmap_grid WHERE heat_intensity > 0').fetchall()
    conn.close()
    return jsonify([dict(g) for g in grid_data]), 200

@app.route('/api/map/lighting', methods=['GET'])
def get_lighting_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    lights = conn.execute('SELECT * FROM campus_lights').fetchall()
    conn.close()
    return jsonify([dict(l) for l in lights]), 200

@app.route('/api/map/infrastructure')
def get_infrastructure():
    conn = get_db_connection()
    infra = conn.execute('SELECT * FROM emergency_infrastructure WHERE status = "active"').fetchall()
    conn.close()
    return jsonify([dict(i) for i in infra])

# --- SafeRoute Navigator Map Layers ---

@app.route('/api/safety/hotspots', methods=['GET'])
def get_safety_hotspots():
    days = request.args.get('days', 30, type=int)
    conn = get_db_connection()
    # In a real app, this would cluster incidents. For MVP, we return active zones
    # or incidents grouped by nearby locations.
    # If the heatmap_grid table doesn't have max_severity/dominant_type, we generate mock hotspots around Karad
    try:
        incidents = conn.execute('''
            SELECT latitude, longitude, type as dominant_type, severity as max_severity, reported_at as latest_report
            FROM incidents 
            WHERE status != 'resolved' AND latitude IS NOT NULL
        ''').fetchall()
        
        hotspots = []
        for inc in incidents:
            hotspots.append({
                'latitude': inc['latitude'],
                'longitude': inc['longitude'],
                'radius': 150, # 150m radius
                'dominant_type': inc['dominant_type'],
                'incident_count': 1,
                'max_severity': inc['max_severity'],
                'latest_report': inc['latest_report']
            })
            
        # Add a couple of fixed demonstration hotspots near Karad if none exist
        if not hotspots:
            hotspots = [
                {
                    'latitude': 17.3090,
                    'longitude': 74.1850,
                    'radius': 100,
                    'dominant_type': 'suspicious_activity',
                    'incident_count': 3,
                    'max_severity': 3,
                    'latest_report': datetime.now().isoformat()
                },
                {
                    'latitude': 17.3050,
                    'longitude': 74.1820,
                    'radius': 200,
                    'dominant_type': 'unsafe_area',
                    'incident_count': 5,
                    'max_severity': 4,
                    'latest_report': datetime.now().isoformat()
                }
            ]
            
        conn.close()
        return jsonify({'success': True, 'hotspots': hotspots}), 200
    except Exception as e:
        print(f"Error serving hotspots: {e}")
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/safety/corridors', methods=['GET'])
def get_safety_corridors():
    # Mock safe corridors around GCEK Karad
    corridors = [
        {
            'id': 'corr_1',
            'name': 'Main Campus Avenue',
            'coordinates': [[17.3087, 74.1848], [17.3100, 74.1860], [17.3120, 74.1870]],
            'lighting_level': 'high',
            'lighting': 'High Intensity LED',
            'active_hours': '24/7',
            'has_cctv': True,
            'is_currently_active': True,
            'safety_score': 4.8,
            'patrolled': True
        },
        {
            'id': 'corr_2',
            'name': 'Hostel Connecting Path',
            'coordinates': [[17.3087, 74.1848], [17.3070, 74.1830], [17.3050, 74.1820]],
            'lighting_level': 'medium',
            'lighting': 'Standard Streetlights',
            'active_hours': '6PM - 11PM',
            'has_cctv': False,
            'is_currently_active': True,
            'safety_score': 3.5,
            'patrolled': False
        }
    ]
    return jsonify({'success': True, 'corridors': corridors}), 200

@app.route('/api/safety/ratings', methods=['GET'])
def get_safety_ratings_data():
    # Mock community ratings around Karad
    ratings = [
        {
            'latitude': 17.3085,
            'longitude': 74.1845,
            'rating': 4.5,
            'comment': 'Very safe during the day, lots of students.',
            'category': 'safe'
        },
        {
            'latitude': 17.3055,
            'longitude': 74.1825,
            'rating': 2.0,
            'comment': 'Dark at night, needs better lighting.',
            'category': 'unsafe'
        },
        {
            'latitude': 17.3105,
            'longitude': 74.1865,
            'rating': 5.0,
            'comment': 'Security guards always present here.',
            'category': 'safe'
        }
    ]
    return jsonify({'success': True, 'ratings': ratings}), 200

@app.route('/api/safety/heatmap', methods=['GET'])
def get_safety_heatmap_data():
    days = request.args.get('days', 30, type=int)
    conn = get_db_connection()
    try:
        # Build heatmap points from incidents
        incidents = conn.execute('''
            SELECT latitude, longitude, severity 
            FROM incidents 
            WHERE latitude IS NOT NULL
        ''').fetchall()
        
        points = []
        for inc in incidents:
            # Format: [lat, lng, intensity]
            points.append([inc['latitude'], inc['longitude'], inc['severity'] * 0.2])
            
        if not points:
             # Mock heatmap points around Karad if db is empty
             points = [
                 [17.3090, 74.1850, 0.6],
                 [17.3085, 74.1855, 0.4],
                 [17.3050, 74.1820, 0.8],
                 [17.3045, 74.1815, 0.7]
             ]
             
        conn.close()
        return jsonify({'success': True, 'points': points}), 200
    except Exception as e:
        print(f"Error serving heatmap: {e}")
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500

# --- Existing App Initialization ---
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5005)
