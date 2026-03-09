import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:5005"

def test_new_endpoints():
    print("Starting Pro-Level API Verification (urllib)...")
    
    # helper for POST
    def post_json(url, data):
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), 
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req) as f:
            return json.loads(f.read().decode('utf-8'))

    # helper for GET
    def get_json(url):
        with urllib.request.urlopen(url) as f:
            return json.loads(f.read().decode('utf-8'))

    # 1. Test Safety Hotspots
    print("\n[Testing Safety Hotspots]")
    try:
        data = get_json(f"{BASE_URL}/api/safety/hotspots")
        print(f"Hotspots Found: {len(data.get('hotspots', []))}")
    except Exception as e: print(f"Error: {e}")

    # 2. Test Emergency Directory
    print("\n[Testing Emergency Directory]")
    try:
        data = get_json(f"{BASE_URL}/api/directory/contacts")
        print(f"Contacts Seeded: {len(data.get('contacts', []))}")
    except Exception as e: print(f"Error: {e}")

    # 3. Test Whistleblower Submission
    print("\n[Testing Whistleblower Submission]")
    try:
        report_data = {
            "title": "Unsafe Lighting",
            "category": "safety_hazard",
            "urgency": "high",
            "description": "Flickering lights near library."
        }
        data = post_json(f"{BASE_URL}/api/whistleblower/submit", report_data)
        ref_hash = data.get('reference_hash')
        print(f"Report Ref: {ref_hash}")
        
        # 4. Test Whistleblower Tracking
        if ref_hash:
            print("\n[Testing Whistleblower Tracking]")
            data = get_json(f"{BASE_URL}/api/whistleblower/track/{ref_hash}")
            print(f"Status: {data.get('report', {}).get('status')}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    test_new_endpoints()
