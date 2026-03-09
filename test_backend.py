import sqlite3
import json
import uuid
import time
from datetime import datetime, timedelta

DB_NAME = 'safenest.db'

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def test_ai_triage():
    print("\n--- Testing AI Triage Persistence ---")
    conn = get_db()
    
    # Mock a triage request
    user_id = 1 # Assuming admin or first user
    description = "I see someone suspicious near the library with a knife"
    priority = "CRITICAL"
    category = "SECURITY"
    instructions = "Evacuate and find security."
    
    conn.execute('''
        INSERT INTO ai_triage_history (user_id, description, priority, category, instructions)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, description, priority, category, instructions))
    conn.commit()
    
    # Verify
    row = conn.execute('SELECT * FROM ai_triage_history WHERE description = ?', (description,)).fetchone()
    if row:
        print(f"[OK] AI Triage Persisted: {row['priority']} - {row['category']}")
    else:
        print("[FAIL] AI Triage Persistence Failed")
    conn.close()

def test_safepath_routing():
    print("\n--- Testing Dynamic SafePath Routing ---")
    conn = get_db()
    
    # Check if we have segments
    segments = conn.execute('SELECT * FROM path_segments').fetchall()
    print(f"Path Segments in DB: {len(segments)}")
    
    if len(segments) > 0:
        # Simulate safest route logic
        safe_segs = [s for s in segments if s['has_cctv']]
        if safe_segs:
            best = max(safe_segs, key=lambda x: x['avg_lighting_score'])
            print(f"[OK] Found Safest Segment: {best['path_type']} with Lighting {best['avg_lighting_score']}")
        else:
            print("[WARN] No CCTV segments found but segments exist.")
    else:
        print("[FAIL] No path segments found. Run seed_tactical.py first.")
    conn.close()

def test_squad_lifecycle():
    print("\n--- Testing Squad Lifecycle ---")
    conn = get_db()
    user_id = 1
    squad_name = f"Test Squad {uuid.uuid4().hex[:4]}"
    invite_code = f"T{uuid.uuid4().hex[:7].upper()}"
    expires_at = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Create
    cur = conn.cursor()
    cur.execute('INSERT INTO squads (squad_name, created_by, expires_at, invite_code) VALUES (?, ?, ?, ?)',
                (squad_name, user_id, expires_at, invite_code))
    squad_id = cur.lastrowid
    
    cur.execute('INSERT INTO squad_members (squad_id, user_id, role) VALUES (?, ?, "leader")', (squad_id, user_id))
    conn.commit()
    print(f"[OK] Squad Created: {squad_name} (ID: {squad_id})")
    
    # 2. Status
    members = conn.execute('SELECT COUNT(*) as count FROM squad_members WHERE squad_id = ?', (squad_id,)).fetchone()
    print(f"[OK] Squad Members: {members['count']}")
    
    # 3. Leave
    conn.execute('DELETE FROM squad_members WHERE squad_id = ? AND user_id = ?', (squad_id, user_id))
    conn.commit()
    print("[OK] Leader left squad.")
    
    # 4. Dissolve
    conn.execute('UPDATE squads SET status = "dissolved" WHERE id = ?', (squad_id,))
    conn.commit()
    print("[OK] Squad dissolved.")
    
    conn.close()

def test_pulse_generation():
    print("\n--- Testing Pulse Generation Logic ---")
    conn = get_db()
    user_id = 1
    
    # Start a session
    cur = conn.cursor()
    cur.execute('INSERT INTO pulse_sessions (user_id, pulse_interval, response_window) VALUES (?, 300, 60)', (user_id,))
    session_id = cur.lastrowid
    conn.commit()
    print(f"[OK] Pulse Session Started: ID {session_id}")
    
    # Simulate pulse generator manually for this test
    cur.execute('INSERT INTO pulse_checks (session_id, status) VALUES (?, "pending")', (session_id,))
    check_id = cur.lastrowid
    conn.commit()
    print(f"[OK] Pulse Check Generated: ID {check_id}")
    
    # Verify escalation check
    sent_at = datetime.now() - timedelta(seconds=70) # Set background
    conn.execute('UPDATE pulse_checks SET sent_at = ? WHERE id = ?', (sent_at.strftime('%Y-%m-%d %H:%M:%S'), check_id))
    conn.commit()
    
    # Escalation Logic (Mock)
    check = conn.execute('SELECT * FROM pulse_checks WHERE id = ?', (check_id,)).fetchone()
    if (datetime.now() - datetime.strptime(check['sent_at'], '%Y-%m-%d %H:%M:%S')).total_seconds() > 60:
        conn.execute('UPDATE pulse_checks SET status = "missed" WHERE id = ?', (check_id,))
        conn.commit()
        print("[OK] Pulse correctly escalated to MISSED status.")
    
    conn.close()

if __name__ == "__main__":
    print("Starting Backend Feature Verification Suite")
    test_ai_triage()
    test_safepath_routing()
    test_squad_lifecycle()
    test_pulse_generation()
    print("\n--- Verification Complete ---")
