import requests

try:
    print("Posting to RCA Run...")
    res = requests.post("http://localhost:8000/api/langfuse-monitor/rca/run?hours=24")
    print(f"Status: {res.status_code}")
    print(f"Response: {res.text}")
except Exception as e:
    print(f"Request failed: {e}")
