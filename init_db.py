import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('safenest.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    
    # Create locations table
    c.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create alerts table with responder tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'ACTIVE',
            responder_name TEXT,
            responder_lat REAL,
            responder_lng REAL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Restore emergency_contacts for private user contacts
    c.execute('''
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Create incidents table (Upgraded for Tactical Expansion)
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            type TEXT CHECK(type IN ('theft', 'assault', 'harassment', 'stalking', 
                                   'vandalism', 'suspicious_activity', 'drug_activity',
                                   'sexual_assault', 'robbery', 'other')) NOT NULL,
            severity TEXT CHECK(severity IN ('low', 'medium', 'high', 'critical')) DEFAULT 'low',
            description TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_verified BOOLEAN DEFAULT 0,
            status TEXT CHECK(status IN ('reported', 'under_review', 'verified', 
                                       'resolved', 'false_report')) DEFAULT 'reported',
            anonymous BOOLEAN DEFAULT 1,
            reported_to_security BOOLEAN DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS route_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_lat REAL NOT NULL,
            start_lng REAL NOT NULL,
            end_lat REAL NOT NULL,
            end_lng REAL NOT NULL,
            route_type TEXT CHECK(route_type IN ('safest', 'balanced', 'fastest')) NOT NULL,
            safety_score REAL,
            distance_meters INTEGER,
            duration_seconds INTEGER,
            route_geometry TEXT, -- JSON
            segment_scores TEXT, -- JSON
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            valid_until DATETIME,
            conditions TEXT -- JSON
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS light_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            light_id INTEGER REFERENCES campus_lights(id),
            reported_by INTEGER REFERENCES users(id),
            latitude REAL,
            longitude REAL,
            report_type TEXT CHECK(report_type IN ('out', 'flickering', 'dim', 'new_needed')),
            description TEXT,
            photo_url TEXT,
            status TEXT CHECK(status IN ('reported', 'verified', 'in_progress', 'resolved')) DEFAULT 'reported',
            reported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    ''')

    # Create anonymous_reports table (PRO-LEVEL ZERO-KNOWLEDGE)
    c.execute('DROP TABLE IF EXISTS anonymous_reports') # Dropping to apply new structure
    c.execute('''
        CREATE TABLE anonymous_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_hash TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT,
            urgency TEXT NOT NULL DEFAULT 'medium',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            location_description TEXT,
            status TEXT DEFAULT 'received',
            admin_notes TEXT,
            admin_response TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            escalated INTEGER DEFAULT 0,
            escalated_at TIMESTAMP
        )
    ''')

    # Create anonymous_chat table
    c.execute('DROP TABLE IF EXISTS anonymous_chat')
    c.execute('''
        CREATE TABLE anonymous_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_hash TEXT NOT NULL,
            sender_role TEXT NOT NULL, -- 'ADMIN' or 'WHISTLEBLOWER'
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_hash) REFERENCES anonymous_reports (reference_hash)
        )
    ''')

    # Create justice_analytics table
    c.execute('''
        CREATE TABLE IF NOT EXISTS justice_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT UNIQUE NOT NULL,
            reports_count INTEGER DEFAULT 0,
            actions_taken INTEGER DEFAULT 0
        )
    ''')

    # ---- NEW PRO-LEVEL TABLES ----

    # ---- INCIDENT HOTSPOTS (aggregated from reports) ----
    c.execute('''
        CREATE TABLE IF NOT EXISTS safety_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            incident_type TEXT NOT NULL DEFAULT 'general',
            severity INTEGER NOT NULL DEFAULT 3 CHECK(severity BETWEEN 1 AND 5),
            description TEXT,
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            verified INTEGER DEFAULT 0,
            report_source TEXT DEFAULT 'user'
        )
    ''')
    
    # ---- SAFE CORRIDORS ----
    c.execute('''
        CREATE TABLE IF NOT EXISTS safe_corridors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            coordinates TEXT NOT NULL,
            safety_score INTEGER DEFAULT 5 CHECK(safety_score BETWEEN 1 AND 5),
            lighting_level TEXT DEFAULT 'well-lit',
            patrolled INTEGER DEFAULT 0,
            active_hours TEXT DEFAULT '00:00-23:59',
            last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ---- SAFETY RATINGS (crowd-sourced) ----
    c.execute('''
        CREATE TABLE IF NOT EXISTS safety_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            time_of_day TEXT DEFAULT 'day',
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ---- EMERGENCY CONTACTS (Global) ----
    c.execute('''
        CREATE TABLE IF NOT EXISTS global_emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT,
            phone TEXT,
            email TEXT,
            chat_url TEXT,
            category TEXT NOT NULL DEFAULT 'general',
            priority INTEGER DEFAULT 5,
            icon TEXT DEFAULT 'phone',
            description TEXT,
            available_hours TEXT DEFAULT '24/7',
            is_active INTEGER DEFAULT 1,
            latitude REAL,
            longitude REAL,
            response_time_avg TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ---- ADMIN NOTIFICATION QUEUE ----
    c.execute('''
        CREATE TABLE IF NOT EXISTS admin_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            reference_id TEXT,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'normal',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create ai_triage_history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_triage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            description TEXT NOT NULL,
            priority TEXT NOT NULL,
            category TEXT NOT NULL,
            instructions TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create safe_routes table (For corridors and hotspots)
    c.execute('''
        CREATE TABLE IF NOT EXISTS safe_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            coordinates_json TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'CORRIDOR'
        )
    ''')

    # --- SQUAD SYNC TABLES ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS squads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            squad_name TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            status TEXT CHECK(status IN ('active', 'dissolved', 'sos_active')) DEFAULT 'active',
            invite_code TEXT UNIQUE,
            max_members INTEGER DEFAULT 8,
            color_code TEXT DEFAULT '#00FF88'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS squad_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            squad_id INTEGER REFERENCES squads(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            role TEXT CHECK(role IN ('leader', 'member')) DEFAULT 'member',
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_known_lat REAL,
            last_known_lng REAL,
            last_location_at DATETIME,
            battery_level INTEGER,
            is_sharing_location BOOLEAN DEFAULT 0,
            status TEXT CHECK(status IN ('active', 'sos', 'disconnected', 'safe')) DEFAULT 'active'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS sos_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            squad_id INTEGER REFERENCES squads(id),
            triggered_by INTEGER REFERENCES users(id),
            trigger_method TEXT CHECK(trigger_method IN ('button', 'shake', 'voice', 'silent', 'auto_fall')) NOT NULL,
            triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            resolved_by INTEGER REFERENCES users(id),
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            status TEXT CHECK(status IN ('active', 'resolved', 'false_alarm', 'escalated')) DEFAULT 'active',
            audio_recording TEXT,
            reported_to_security BOOLEAN DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS sos_location_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sos_id INTEGER REFERENCES sos_events(id),
            user_id INTEGER REFERENCES users(id),
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            speed_kmh REAL,
            heading REAL,
            accuracy_meters REAL,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS squad_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            squad_id INTEGER REFERENCES squads(id),
            sos_id INTEGER REFERENCES sos_events(id),
            sender_id INTEGER REFERENCES users(id),
            message_type TEXT CHECK(message_type IN ('text', 'preset', 'audio', 'system')) NOT NULL,
            content TEXT NOT NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # --- GUARDIAN PULSE TABLES ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS pulse_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            status TEXT CHECK(status IN ('active', 'completed', 'escalated', 'cancelled')) DEFAULT 'active',
            pulse_interval INTEGER NOT NULL DEFAULT 300,
            response_window INTEGER NOT NULL DEFAULT 60,
            start_latitude REAL,
            start_longitude REAL,
            destination_lat REAL,
            destination_lng REAL,
            auto_activated BOOLEAN DEFAULT 0,
            total_pulses_sent INTEGER DEFAULT 0,
            total_pulses_responded INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS pulse_guardians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            guardian_user_id INTEGER REFERENCES users(id),
            guardian_name TEXT,
            guardian_phone TEXT,
            guardian_email TEXT,
            escalation_level INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS pulse_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES pulse_sessions(id),
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            responded_at DATETIME,
            response_method TEXT CHECK(response_method IN ('swipe', 'biometric', 'voice', 'motion', 'watch')),
            status TEXT CHECK(status IN ('pending', 'responded', 'missed', 'escalated')) DEFAULT 'pending',
            latitude_at_pulse REAL,
            longitude_at_pulse REAL,
            escalation_level_reached INTEGER DEFAULT 0
        )
    ''')

    # --- TACTICAL AWARENESS TABLES ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS campus_lights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            light_type TEXT CHECK(light_type IN ('led', 'sodium', 'fluorescent', 'solar')) DEFAULT 'led',
            brightness_lumens INTEGER NOT NULL,
            effective_radius INTEGER DEFAULT 30,
            operating_start TIME DEFAULT '18:00',
            operating_end TIME DEFAULT '06:00',
            status TEXT CHECK(status IN ('operational', 'malfunctioning', 'off', 'unknown')) DEFAULT 'operational',
            last_status_check DATETIME,
            zone TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS foot_traffic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER,
            timestamp_bucket DATETIME NOT NULL,
            user_count INTEGER DEFAULT 0,
            direction_ratio REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS path_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_lat REAL NOT NULL,
            start_lng REAL NOT NULL,
            end_lat REAL NOT NULL,
            end_lng REAL NOT NULL,
            length_meters REAL,
            path_type TEXT CHECK(path_type IN ('sidewalk', 'road', 'trail', 'indoor', 'parking_lot')),
            surface_type TEXT CHECK(surface_type IN ('paved', 'gravel', 'dirt', 'indoor')),
            wheelchair_accessible BOOLEAN DEFAULT 1,
            has_cctv BOOLEAN DEFAULT 0,
            cell_signal_strength INTEGER,
            avg_lighting_score REAL,
            last_calculated DATETIME
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS traffic_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER REFERENCES path_segments(id),
            day_of_week INTEGER NOT NULL,
            hour_of_day INTEGER NOT NULL,
            avg_user_count REAL,
            stddev_user_count REAL,
            sample_count INTEGER,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS emergency_infrastructure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT CHECK(type IN ('blue_light_phone', 'security_booth', 'cctv_camera', 
                                   'aed_station', 'fire_extinguisher', 'safe_building_entrance')),
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            station_id TEXT,
            name TEXT,
            status TEXT CHECK(status IN ('active', 'inactive', 'maintenance')) DEFAULT 'active',
            coverage_radius INTEGER,
            phone_number TEXT,
            operating_hours TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS heatmap_grid (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grid_lat REAL NOT NULL,
            grid_lng REAL NOT NULL,
            grid_size_meters INTEGER DEFAULT 50,
            time_bucket TEXT CHECK(time_bucket IN ('all', 'morning', 'afternoon', 'evening', 'night', 'late_night')),
            incident_count_7d INTEGER DEFAULT 0,
            incident_count_30d INTEGER DEFAULT 0,
            incident_count_90d INTEGER DEFAULT 0,
            incident_count_1y INTEGER DEFAULT 0,
            weighted_score_7d REAL DEFAULT 0,
            weighted_score_30d REAL DEFAULT 0,
            weighted_score_90d REAL DEFAULT 0,
            lighting_score REAL DEFAULT 0,
            traffic_score REAL DEFAULT 0,
            signal_strength INTEGER DEFAULT 0,
            infrastructure_score REAL DEFAULT 0,
            composite_safety_score REAL DEFAULT 0,
            risk_level TEXT CHECK(risk_level IN ('safe', 'caution', 'elevated', 'high', 'critical')) DEFAULT 'safe',
            extrusion_height REAL DEFAULT 0,
            heat_intensity REAL DEFAULT 0,
            color_hex TEXT DEFAULT '#00FF88',
            last_computed DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(grid_lat, grid_lng, grid_size_meters, time_bucket)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS cell_signal_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            signal_strength INTEGER NOT NULL,
            carrier TEXT,
            network_type TEXT CHECK(network_type IN ('5g', '4g_lte', '4g', '3g', 'edge', 'no_signal')),
            measured_by INTEGER REFERENCES users(id),
            measured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            device_model TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS zone_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            zone_center_lat REAL NOT NULL,
            zone_center_lng REAL NOT NULL,
            zone_radius INTEGER DEFAULT 200,
            zone_name TEXT,
            alert_on_new_incident BOOLEAN DEFAULT 1,
            alert_on_risk_change BOOLEAN DEFAULT 1,
            alert_threshold TEXT CHECK(alert_threshold IN ('any', 'elevated', 'high', 'critical')) DEFAULT 'elevated',
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if admin exists, if not create default admin
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        admin_password = generate_password_hash('admin123')
        c.execute('INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)', 
                  ('admin', admin_password, True))
        print("Default admin account created (admin/admin123).")
    
    conn.commit()
    
    # ---- SEEDING ----
    # Seed global emergency contacts if empty
    existing = c.execute('SELECT COUNT(*) FROM global_emergency_contacts').fetchone()[0]
    if existing == 0:
        seed_emergency_contacts(c)
    
    # Seed sample corridors if empty
    existing_corridors = c.execute('SELECT COUNT(*) FROM safe_corridors').fetchone()[0]
    if existing_corridors == 0:
        seed_safe_corridors(c)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def seed_emergency_contacts(db):
    """Seed the database with default emergency contacts."""
    contacts = [
        ('Campus Security - Emergency', 'Campus Police', '911', 'security@university.edu',
         None, 'emergency', 1, 'shield', 
         'Immediate response for active threats, violence, or life-threatening emergencies.',
         '24/7', 1, None, None, '< 3 minutes'),
        ('Campus Security - Non-Emergency', 'Campus Police', '555-0100', 'patrol@university.edu',
         None, 'emergency', 2, 'shield-check',
         'Escort services, suspicious activity reports, noise complaints.',
         '24/7', 1, None, None, '5-10 minutes'),
        ('University Medical Center', 'Health Services', '555-0200', 'health@university.edu',
         None, 'medical', 3, 'heart-pulse',
         'On-campus clinic for injuries, illness, and medical emergencies.',
         'Mon-Fri 8AM-10PM, Sat-Sun 10AM-6PM', 1, None, None, '< 5 minutes'),
        ('24/7 Crisis Hotline', 'Counseling Center', '988', 'crisis@university.edu',
         'https://chat.university.edu/crisis', 'mental_health', 1, 'brain',
         'Immediate support for suicidal thoughts, severe anxiety, or emotional crisis.',
         '24/7', 1, None, None, 'Immediate'),
    ]
    for contact in contacts:
        db.execute('''
            INSERT INTO global_emergency_contacts 
            (name, department, phone, email, chat_url, category, priority, 
             icon, description, available_hours, is_active, latitude, longitude, response_time_avg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', contact)

def seed_safe_corridors(db):
    import json
    corridors = [
        ('Main Academic Walkway', 
         json.dumps([[40.7128, -74.0060], [40.7135, -74.0055], [40.7140, -74.0048]]),
         5, 'well-lit', 1, '00:00-23:59'),
        ('Library to Student Center', 
         json.dumps([[40.7130, -74.0070], [40.7132, -74.0062], [40.7134, -74.0058]]),
         4, 'well-lit', 1, '06:00-02:00'),
    ]
    for corridor in corridors:
        db.execute('''
            INSERT INTO safe_corridors (name, coordinates, safety_score, lighting_level, patrolled, active_hours)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', corridor)

if __name__ == '__main__':
    init_db()
