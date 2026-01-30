# api/index.py
from flask import Flask, request, jsonify
import io
import os
import re
import requests
from requests.auth import HTTPBasicAuth
import urllib3
from http.server import BaseHTTPRequestHandler

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
        log_to_console("get_manhattan_token: MANHATTAN_PASSWORD or MANHATTAN_SECRET missing (len set: pwd=%s, secret=%s)" % (
            "yes" if MANHATTAN_PASSWORD else "no", "yes" if MANHATTAN_SECRET else "no"), prefix="[AUTH]")
        return None

    url = f"https://{AUTH_HOST}/oauth/token"
    username = f"{USERNAME_BASE}{org.lower()}"
    log_to_console("get_manhattan_token: POST %s (username=%s)" % (url, username), prefix="[AUTH]")
    data = {
        "grant_type": "password",
        "username": username,
        "password": MANHATTAN_PASSWORD
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = HTTPBasicAuth(CLIENT_ID, MANHATTAN_SECRET)
    try:
        r = requests.post(url, data=data, headers=headers, auth=auth, timeout=60, verify=False)
        log_to_console("get_manhattan_token: response status=%s" % r.status_code, prefix="[AUTH]")
        if r.status_code == 200:
            token = r.json().get("access_token")
            if token:
                log_to_console("get_manhattan_token: token received (len=%s)" % len(token), prefix="[AUTH]")
            else:
                log_to_console("get_manhattan_token: 200 OK but no access_token in body", prefix="[AUTH]")
            return token
        try:
            err_body = r.text[:500] if r.text else "(empty)"
            log_to_console("get_manhattan_token: non-200 body: %s" % err_body, prefix="[AUTH]")
        except Exception:
            log_to_console("get_manhattan_token: non-200 (could not read body)", prefix="[AUTH]")
    except Exception as e:
        log_to_console("get_manhattan_token: exception: %s" % e, prefix="[AUTH]")
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

    log_to_console("Authenticating for ORG: %s (env vars set: pwd=%s, secret=%s)" % (
        org, "yes" if MANHATTAN_PASSWORD else "no", "yes" if MANHATTAN_SECRET else "no"), prefix="[API]")
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
# VERCEL: handler must be a class subclasses BaseHTTPRequestHandler
# =============================================================================
def _make_environ(handler):
    """Build WSGI environ from BaseHTTPRequestHandler."""
    path = handler.path.split("?")[0] if handler.path else "/"
    query = handler.path.split("?", 1)[1] if "?" in (handler.path or "") else ""
    content_length = handler.headers.get("Content-Length", 0)
    try:
        content_length = int(content_length)
    except ValueError:
        content_length = 0
    body = handler.rfile.read(content_length) if content_length else b""
    environ = {
        "REQUEST_METHOD": handler.command,
        "PATH_INFO": path,
        "SCRIPT_NAME": "",
        "QUERY_STRING": query,
        "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        "CONTENT_LENGTH": str(content_length),
        "wsgi.input": io.BytesIO(body),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "https",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": True,
    }
    for key, value in handler.headers.items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    return environ


class handler(BaseHTTPRequestHandler):
    """Vercel expects this class name; dispatches to Flask app."""

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_OPTIONS(self):
        self._dispatch()

    def _dispatch(self):
        environ = _make_environ(self)
        status_headers = []

        def start_response(status, headers):
            status_headers.append((status, headers))

        try:
            result = app(environ, start_response)
            status, headers = status_headers[0]
            code = int(status.split()[0])
            self.send_response(code)
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            for chunk in result:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                self.wfile.write(chunk)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"success":false,"error":"Internal server error"}')

    def log_message(self, format, *args):
        pass  # suppress default logging






















