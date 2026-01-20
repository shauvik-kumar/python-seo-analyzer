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
CORS(app)

# --------------------
# Env vars
# --------------------
CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = os.environ["OAUTH_REDIRECT_URI"]

POC_API_KEY = os.environ["POC_API_KEY"]
GSC_ACCESS_TOKEN = os.environ["GSC_ACCESS_TOKEN"]

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
# OAuth login (for YOU only)
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
# OAuth callback (YOU copy token to env)
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

    service = build("searchconsole", "v1", credentials=creds)
    sites = service.sites().list().execute()

    return jsonify({
        "access_token": creds.token,
        "sites": sites
    })

# --------------------
# EXPORT TO GOOGLE SHEET (PoC)
# --------------------
@app.route("/export-to-sheet", methods=["GET"])
def export_to_sheet():
    data = request.args

    # --- security ---
    api_key = data.get("key")
    if api_key != POC_API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    sheet_id = data["sheetId"]
    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    access_token = GSC_ACCESS_TOKEN

    # --------------------
    # 1. Fetch GSC data (LIMIT 10)
    # --------------------
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

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    gsc_response = requests.post(gsc_url, json=gsc_payload, headers=headers)
    gsc_data = gsc_response.json()

    rows = gsc_data.get("rows", [])

    # --------------------
    # 2. Prepare rows
    # --------------------
    values = [
        ["Query", "Clicks", "Impressions", "CTR", "Position"]
    ]

    for r in rows:
        values.append([
            r["keys"][0],
            r["clicks"],
            r["impressions"],
            r["ctr"],
            r["position"]
        ])

    # --------------------
    # 3. CLEAR old data (Data tab)
    # --------------------
    clear_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{sheet_id}/values/Data!A6:Z1000:clear"
    )

    requests.post(clear_url, headers=headers)

    # --------------------
    # 4. WRITE fresh data (Data tab)
    # --------------------
    write_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{sheet_id}/values/Data!A6?valueInputOption=RAW"
    )

    write_payload = {
        "values": values
    }

    write_response = requests.put(
        write_url,
        json=write_payload,
        headers=headers
    )

    return jsonify({
        "status": "success",
        "rows_written": len(values) - 1
    })
