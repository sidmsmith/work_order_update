# api/index.py
from flask import Flask, request, jsonify
import os
import requests
from requests.auth import HTTPBasicAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================
MANHATTAN_PASSWORD = os.getenv("MANHATTAN_PASSWORD")
MANHATTAN_SECRET = os.getenv("MANHATTAN_SECRET")

# =============================================================================
# CONFIGURATION
# =============================================================================
AUTH_HOST = "salep-auth.sce.manh.com"
API_HOST = "salep.sce.manh.com"
USERNAME_BASE = "sdtadmin@"
CLIENT_ID = "omnicomponent.1.0.0"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_manhattan_token(org):
    """Get Manhattan WMS authentication token"""
    if not MANHATTAN_PASSWORD or not MANHATTAN_SECRET:
        return None
    
    url = f"https://{AUTH_HOST}/oauth/token"
    username = f"{USERNAME_BASE}{org.lower()}"
    data = {
        "grant_type": "password",
        "username": username,
        "password": MANHATTAN_PASSWORD
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = HTTPBasicAuth(CLIENT_ID, MANHATTAN_SECRET)
    try:
        r = requests.post(url, data=data, headers=headers, auth=auth, timeout=60, verify=False)
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception as e:
        print(f"[AUTH] Error: {e}")
    return None

def log_to_console(message, prefix="[API]"):
    """Log message for console output"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{timestamp} {prefix} {message}")

# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/api/auth', methods=['POST'])
def auth():
    """Authenticate with Manhattan WMS"""
    org = request.json.get('org', '').strip()
    if not org:
        return jsonify({"success": False, "error": "ORG required"})
    
    log_to_console(f"Authenticating for ORG: {org}")
    token = get_manhattan_token(org)
    if token:
        log_to_console(f"Auth success for ORG: {org}")
        return jsonify({"success": True, "token": token})
    
    log_to_console(f"Auth failed for ORG: {org}")
    return jsonify({"success": False, "error": "Authentication failed"})

# =============================================================================
# VERCEL HANDLER
# =============================================================================
def handler(request):
    return app(request.environ, lambda status, headers: None)


























