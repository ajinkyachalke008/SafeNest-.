import urllib.request
import urllib.parse
import json
import http.cookiejar

BASE_URL = "http://localhost:5005"

def test_endpoint(name, path, method="GET", data=None, headers=None, expect_json=True):
    print(f"Testing {name} [{path}]...")
    url = f"{BASE_URL}{path}"
    
    if data and isinstance(data, dict):
        data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data:
        req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            if expect_json:
                res_json = json.loads(body)
                print(f"  [SUCCESS] Status: {status}")
                return res_json
            else:
                print(f"  [SUCCESS] Status: {status}")
                return body
    except Exception as e:
        print(f"  [FAILURE] {e}")
        return None

# Setup Cookie Handler for session persistence
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
urllib.request.install_opener(opener)

def run_tests():
    print("=== SAFENEST COMPREHENSIVE TEST SUITE ===\n")

    # 1. Test Landing Page
    home = test_endpoint("Home Page", "/", expect_json=False)
    if home and "SafeNest" in home:
        print("  [PASS] Landing page contains 'SafeNest'")
        if "tactical-footer-marquee" in home:
            print("  [PASS] Tactical marquee found")
        if "Guardian Pulse" in home:
            print("  [PASS] Guardian Pulse card found")
    else:
        print("  [FAIL] Home page load failed or content incorrect")

    # 1.5 Register a new user
    import random
    test_user = f"user_{random.randint(1000, 9999)}"
    test_pass = "password123"
    print(f"\nRegistering new user: {test_user}...")
    reg_res = test_endpoint("Register API", "/api/register", method="POST", data={"username": test_user, "password": test_pass})
    if reg_res and reg_res.get("message") == "User registered successfully":
        print("  [PASS] Registration successful")
    else:
        print("  [FAIL] Registration failed")
        return

    # 2. Login with new user
    print(f"\nLogging in as {test_user}...")
    login_res = test_endpoint("Login API", "/api/login", method="POST", data={"username": test_user, "password": test_pass})
    if login_res and login_res.get("message") == "Login successful":
        print("  [PASS] Login successful")
    else:
        print("  [FAIL] Login failed")
        return

    # 3. Tactical Map Data
    print("\nVerifying Tactical Map Layers...")
    lighting = test_endpoint("Lighting Data", "/api/map/lighting")
    if lighting and len(lighting) > 0:
        print(f"  [PASS] Received {len(lighting)} lighting data points")
    else:
        print("  [FAIL] Lighting data empty")

    infra = test_endpoint("Infrastructure Data", "/api/map/infrastructure")
    if infra and any(i.get('type') == 'cctv_camera' for i in infra):
        print("  [PASS] CCTV cameras found in infrastructure")
    else:
        print("  [FAIL] Infrastructure data or CCTV missing")

    heatmap = test_endpoint("Heatmap Grid", "/api/heatmap/grid")
    if heatmap and len(heatmap) > 0:
        print(f"  [PASS] Received {len(heatmap)} heatmap grid cells")
    else:
        print("  [FAIL] Heatmap grid empty")

    # 4. SafePath Routing
    print("\nVerifying SafePath Routing Engine...")
    routes = test_endpoint("SafePath Routes", "/api/safepath/routes", method="POST", 
                           data={"origin": {"lat": 20.5937, "lng": 78.9629}, 
                                 "destination": {"lat": 20.5950, "lng": 78.9650}})
    if routes and len(routes) == 3:
        print("  [PASS] Routing engine returned 3 tactical options")
        safest = next((r for r in routes if r['type'] == 'safest'), None)
        if safest and safest['analytics']['cctv_count'] > 0:
            print(f"  [PASS] Safest route has CCTV analytics: {safest['analytics']['cctv_count']} units")
    else:
        print("  [FAIL] Routing engine failed or returned incorrect response")

    # 5. AI Triage
    print("\nVerifying AI Triage...")
    triage = test_endpoint("AI Triage", "/api/ai/triage", method="POST", data={"description": "blood and attack"})
    if triage and triage.get("priority") == "CRITICAL":
        print(f"  [PASS] AI correctly identified CRITICAL priority for 'attack'")
        print(f"  [INFO] AI Instructions: {triage.get('instructions')}")
    else:
        print("  [FAIL] AI Triage failed to prioritize correctly")

    # 6. Justice Analytics
    print("\nVerifying Justice Analytics...")
    justice = test_endpoint("Justice Stats", "/api/justice/analytics")
    if justice is not None:
        print("  [PASS] Justice analytics endpoint responsive")
    else:
        print("  [FAIL] Justice analytics unreachable")

    # 7. Squad Sync (Added)
    print("\nVerifying Squad Sync...")
    squad = test_endpoint("Create Squad", "/api/squads/create", method="POST", data={"squad_name": "Test Squad Alpha"})
    if squad and squad.get("invite_code"):
        print(f"  [PASS] Squad created. Invite code: {squad.get('invite_code')}")
        status = test_endpoint("Squad Status", "/api/squads/status")
        if status and isinstance(status, list) and status[0].get("squad_name") == "Test Squad Alpha":
            print("  [PASS] Squad status verified sync")
    else:
        print("  [FAIL] Squad creation failed")

    print("\n=== TEST SUITE COMPLETE ===")

if __name__ == "__main__":
    run_tests()
