import os
import requests
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# --------------------
# App setup
# --------------------
app = Flask(__name__)
app.secret_key = "gsc-secret"

# CORS (API-style, no cookies)
CORS(app)

# --------------------
# Env vars
# --------------------
CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = os.environ["OAUTH_REDIRECT_URI"]

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

# --------------------
# Health checks
# --------------------
@app.route("/ping")
def ping():
    return "OK"

@app.route("/")
def home():
    return "GSC backend alive"

# --------------------
# OAuth login
# --------------------
@app.route("/login")
def login():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )
    return redirect(auth_url)

# --------------------
# OAuth callback
# --------------------
@app.route("/oauth/callback")
def callback():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # TEMP: return token so you can test API calls
    # (Later you will store this securely per client)
    service = build("searchconsole", "v1", credentials=creds)
    sites = service.sites().list().execute()

    return jsonify({
        "access_token": creds.token,
        "sites": sites
    })

# --------------------
# Search Analytics API
# --------------------
@app.route("/search-analytics", methods=["POST"])
def search_analytics():
    data = request.json

    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    # Bearer token auth (NO sessions)
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401

    access_token = auth_header.replace("Bearer ", "")

    url = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        f"{site.replace('/', '%2F')}/searchAnalytics/query"
    )

    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query"],
        "rowLimit": 10
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)
    return jsonify(r.json())

@app.route("/export-to-sheet", methods=["GET", "POST"])
def export_to_sheet():
    if request.method == "GET":
        data = request.args
    else:
        data = request.json

    sheet_id = data["sheetId"]
    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    # Bearer token
    api_key = request.args.get("key") or request.headers.get("X-API-KEY")

    if api_key != os.environ.get("POC_API_KEY"):
        return jsonify({"error": "Invalid API key"}), 401

    # use YOUR stored access token here
    access_token = os.environ["GSC_ACCESS_TOKEN"]


    # 1️⃣ Fetch GSC data (reuse logic)
    gsc_url = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        f"{site.replace('/', '%2F')}/searchAnalytics/query"
    )

    gsc_payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query"],
        "rowLimit": 10
    }

    gsc_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    gsc_response = requests.post(gsc_url, json=gsc_payload, headers=gsc_headers)
    gsc_data = gsc_response.json()

    rows = gsc_data.get("rows", [])

    # 2️⃣ Prepare sheet rows
    sheet_rows = [
        ["Query", "Clicks", "Impressions", "CTR", "Position"]
    ]

    for row in rows:
        sheet_rows.append([
            row["keys"][0],
            row["clicks"],
            row["impressions"],
            row["ctr"],
            row["position"]
        ])

    # 3️⃣ Write to Google Sheet
    sheets_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:append?valueInputOption=RAW"

    sheets_payload = {
        "values": sheet_rows
    }

    sheets_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    sheets_response = requests.post(
        sheets_url,
        json=sheets_payload,
        headers=sheets_headers
    )

    return jsonify({
        "status": "success",
        "rows_written": len(sheet_rows) - 1
    })

