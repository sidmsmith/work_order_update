# api/index.py
from flask import Flask, request, jsonify
import os
import re
import requests
from requests.auth import HTTPBasicAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# =============================================================================
# ENVIRONMENT VARIABLES (same as all other Manhattan apps - set in Vercel)
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
    """Authenticate with Manhattan WMS using MANHATTAN_PASSWORD and MANHATTAN_SECRET."""
    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        body = {}
    org = (body.get('org') or '').strip()
    if not org:
        return jsonify({"success": False, "error": "ORG required"})

    if not MANHATTAN_PASSWORD or not MANHATTAN_SECRET:
        log_to_console("Auth failed: MANHATTAN_PASSWORD or MANHATTAN_SECRET not set", prefix="[AUTH]")
        return jsonify({
            "success": False,
            "error": "Server configuration error: MANHATTAN_PASSWORD and MANHATTAN_SECRET must be set in Vercel environment variables."
        })

    log_to_console(f"Authenticating for ORG: {org}")
    token = get_manhattan_token(org)
    if token:
        log_to_console(f"Auth success for ORG: {org}")
        return jsonify({"success": True, "token": token})

    log_to_console(f"Auth failed for ORG: {org}")
    return jsonify({"success": False, "error": "Authentication failed"})


# Order search template (requested shape for /dcorder/api/dcorder/order/search)
ORDER_SEARCH_TEMPLATE = {
    "OrderId": None,
    "OrderProcessTypeId": None,
    "OrderType": None,
    "OrderLine": {
        "OrderLineId": None,
        "ItemId": None,
        "ItemDescription": None,
        "ProductTypeId": None,
        "PipelineStatus": None,
        "OrderedQuantity": None,
    },
}


def parse_work_order_input(raw):
    """Parse work order input: split by space, colon, semicolon; return (order_ids_list, use_wildcard)."""
    if not raw or not raw.strip():
        return [], False
    tokens = [t.strip() for t in re.split(r"[\s:;]+", raw) if t.strip()]
    use_wildcard = any(t.upper() == "*" for t in tokens)
    order_ids = [t for t in tokens if t.upper() != "*"]
    return order_ids, use_wildcard


@app.route("/api/orderSearch", methods=["POST"])
def order_search():
    """Search work orders via /dcorder/api/dcorder/order/search."""
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    org = (data.get("org") or "").strip()
    token = (data.get("token") or "").strip()
    work_order_input = (data.get("workOrderInput") or "").strip()

    if not org or not token:
        return jsonify({"success": False, "error": "ORG and token required"})

    if not work_order_input:
        return jsonify({"success": False, "error": "Work Order(s) required (or * for all)"})

    order_ids, use_wildcard = parse_work_order_input(work_order_input)

    if use_wildcard:
        query = "OrderProcessTypeId = 'Work Order'"
    else:
        if not order_ids:
            return jsonify({"success": False, "error": "Enter at least one Work Order ID or * for all"})
        quoted = "', '".join(order_ids)
        query = f"OrderProcessTypeId = 'Work Order' AND OrderId IN [ '{quoted}' ]"

    payload = {
        "Query": query,
        "Size": 1000,
        "Template": ORDER_SEARCH_TEMPLATE,
    }

    url = f"https://{API_HOST}/dcorder/api/dcorder/order/search"
    facility_id = f"{org.upper()}-DM1"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "FacilityId": facility_id,
        "selectedOrganization": org.upper(),
        "selectedLocation": facility_id,
    }

    log_to_console(f"Order search for ORG: {org}, wildcard={use_wildcard}, query={query[:80]}...")

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60, verify=False)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
        if not r.ok:
            return jsonify({"success": False, "error": body.get("message", r.text[:500]), "status": r.status_code})
        return jsonify({"success": True, "data": body})
    except Exception as e:
        log_to_console(f"Order search error: {e}", prefix="[ORDER_SEARCH]")
        return jsonify({"success": False, "error": str(e)})


# =============================================================================
# VERCEL HANDLER
# =============================================================================
def handler(request):
    return app(request.environ, lambda status, headers: None)


























