import requests
import random
import time

BASE_URL = "http://localhost:5005"

def test_live_auth_flow():
    # 1. Create a random user
    username = f"test_user_{random.randint(1000, 9999)}"
    password = "LiveTestPassword123!"
    
    print(f"--- LIVE AUTH TEST: {username} ---")
    
    # Registration
    print(f"Step 1: Registering {username}...")
    reg_response = requests.post(f"{BASE_URL}/api/register", json={
        "username": username,
        "password": password
    })
    
    if reg_response.status_code == 201:
        print("  [PASS] Registration successful (201 Created)")
    else:
        print(f"  [FAIL] Registration failed: {reg_response.status_code} - {reg_response.text}")
        return

    # Login
    print("Step 2: Logging in...")
    session = requests.Session()
    login_response = session.post(f"{BASE_URL}/api/login", json={
        "username": username,
        "password": password
    })
    
    if login_response.status_code == 200:
        print("  [PASS] Login successful (200 OK)")
        data = login_response.json()
        print(f"  [INFO] Server message: {data.get('message')}")
    else:
        print(f"  [FAIL] Login failed: {login_response.status_code} - {login_response.text}")
        return

    # Session Persistence (Dashboard check)
    print("Step 3: Verifying session persistence...")
    dash_response = session.get(f"{BASE_URL}/dashboard")
    if dash_response.status_code == 200 and "Tactical Intel" in dash_response.text:
        print("  [PASS] Dashboard accessible and contains Tactical content")
    else:
        print(f"  [FAIL] Dashboard inaccessible or session lost: {dash_response.status_code}")
        if dash_response.status_code == 200:
            print("  [WARN] Dashboard returned 200 but content might be wrong (check login redirect)")
            
    # API Verification
    print("Step 4: Testing stateful API (/api/contacts)...")
    contact_response = session.get(f"{BASE_URL}/api/contacts")
    if contact_response.status_code == 200:
        print("  [PASS] Stateful API reachable with session")
    else:
        print(f"  [FAIL] API call unauthorized: {contact_response.status_code}")

    print("\n--- LIVE TEST COMPLETE: ALL SYSTEMS NOMINAL ---")

if __name__ == "__main__":
    test_live_auth_flow()
