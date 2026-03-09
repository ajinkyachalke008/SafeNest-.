import sqlite3
import random
from datetime import datetime, timedelta

def seed_tactical_data():
    conn = sqlite3.connect('safenest.db')
    c = conn.cursor()

    # Campus Center (approx coordinates based on common test locations)
    CENTER_LAT = 20.5937
    CENTER_LNG = 78.9629

    print("Clearing existing tactical data...")
    c.execute('DELETE FROM campus_lights')
    c.execute('DELETE FROM heatmap_grid')
    c.execute('DELETE FROM emergency_infrastructure')
    c.execute('DELETE FROM foot_traffic')
    c.execute('DELETE FROM path_segments')

    print("Seeding Campus Lights...")
    for i in range(20):
        lat = CENTER_LAT + random.uniform(-0.005, 0.005)
        lng = CENTER_LNG + random.uniform(-0.005, 0.005)
        status = random.choice(['operational', 'operational', 'malfunctioning', 'off'])
        c.execute('''
            INSERT INTO campus_lights (latitude, longitude, brightness_lumens, status)
            VALUES (?, ?, ?, ?)
        ''', (lat, lng, random.randint(1000, 3000), status))

    print("Seeding Heatmap Grid...")
    # Create a 5x5 grid of safety clusters
    for lat_off in range(-2, 3):
        for lng_off in range(-2, 3):
            lat = CENTER_LAT + (lat_off * 0.002)
            lng = CENTER_LNG + (lng_off * 0.002)
            
            # Random risk intensity
            intensity = random.uniform(0.1, 1.0)
            height = intensity * 500  # 3D Extrusion height
            
            # Color logic: Green to Red
            if intensity < 0.3: color = '#00FF88' # Safe
            elif intensity < 0.6: color = '#FFFF00' # Caution
            else: color = '#FF0077' # High Risk
            
            c.execute('''
                INSERT INTO heatmap_grid 
                (grid_lat, grid_lng, time_bucket, heat_intensity, extrusion_height, color_hex, composite_safety_score)
                VALUES (?, ?, 'night', ?, ?, ?, ?)
            ''', (lat, lng, intensity, height, color, (1 - intensity) * 100))

    print("Seeding Emergency Infrastructure...")
    infra_data = [
        ('blue_light_phone', 'B-101', 'South Entrance', '24/7', '777-101'),
        ('blue_light_phone', 'B-102', 'Library West', '24/7', '777-102'),
        ('security_booth', 'S-01', 'Main Admin Hub', '06:00-22:00', '777-001'),
        ('security_booth', 'S-02', 'Hostel C Gate', '24/7', '777-002'),
        ('cctv_camera', 'C-55', 'Parking Lot A', '24/7', None),
        ('aed_station', 'A-12', 'Gym Complex', '08:00-20:00', '777-911'),
        ('safe_building_entrance', 'H-09', 'Tech Block B', '24/7', None)
    ]
    
    for infra_type, station_id, zone_name, hours, phone in infra_data:
        lat = CENTER_LAT + random.uniform(-0.005, 0.005)
        lng = CENTER_LNG + random.uniform(-0.005, 0.005)
        c.execute('''
            INSERT INTO emergency_infrastructure 
            (type, station_id, name, latitude, longitude, operating_hours, phone_number, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        ''', (infra_type, station_id, zone_name, lat, lng, hours, phone))

    print("Seeding Sample Path Segments...")
    # Create a small network of paths
    segments = [
        (CENTER_LAT, CENTER_LNG, CENTER_LAT+0.002, CENTER_LNG, 'sidewalk', 1),
        (CENTER_LAT+0.002, CENTER_LNG, CENTER_LAT+0.002, CENTER_LNG+0.002, 'sidewalk', 1),
        (CENTER_LAT, CENTER_LNG, CENTER_LAT, CENTER_LNG+0.002, 'road', 0),
        (CENTER_LAT, CENTER_LNG+0.002, CENTER_LAT+0.002, CENTER_LNG+0.002, 'sidewalk', 1),
        (CENTER_LAT+0.002, CENTER_LNG, CENTER_LAT+0.004, CENTER_LNG+0.002, 'trail', 0)
    ]
    for s_lat, s_lng, e_lat, e_lng, p_type, has_cctv in segments:
        c.execute('''
            INSERT INTO path_segments (start_lat, start_lng, end_lat, end_lng, path_type, has_cctv, avg_lighting_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (s_lat, s_lng, e_lat, e_lng, p_type, has_cctv, random.uniform(50, 250)))

    print("Seeding Sample Incidents...")
    incident_types = ['suspicious_activity', 'vandalism', 'theft']
    for _ in range(5):
        lat = CENTER_LAT + random.uniform(-0.003, 0.003)
        lng = CENTER_LNG + random.uniform(-0.003, 0.003)
        c.execute('''
            INSERT INTO incidents (type, severity, description, latitude, longitude, is_verified, status)
            VALUES (?, ?, ?, ?, ?, 1, 'verified')
        ''', (random.choice(incident_types), random.choice(['low', 'medium']), "Sample tactical incident report", lat, lng))

    conn.commit()
    conn.close()
    print("Tactical seeding complete.")

if __name__ == '__main__':
    seed_tactical_data()
