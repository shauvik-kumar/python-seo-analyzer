import os
import requests
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# =====================================================
# APP SETUP (MUST BE FIRST)
# =====================================================
app = Flask(__name__)
app.secret_key = "gsc-secret"
CORS(app)

# =====================================================
# ENV VARS
# =====================================================
CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = os.environ["OAUTH_REDIRECT_URI"]

POC_API_KEY = os.environ["POC_API_KEY"]
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
DATA_SHEET_ID = int(os.environ["DATA_SHEET_ID"])  # gid = 0

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

# =====================================================
# TOKEN REFRESH (CORE FIX)
# =====================================================
def get_access_token():
    token_url = "https://oauth2.googleapis.com/token"

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }

    response = requests.post(token_url, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

# =====================================================
# HEALTH
# =====================================================
@app.route("/ping")
def ping():
    return "OK"

@app.route("/")
def home():
    return "GSC backend alive"

# =====================================================
# OAUTH (YOU ONLY – ONE TIME)
# =====================================================
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
        prompt="consent",
        include_granted_scopes=False
    )

    return redirect(auth_url)

@app.route("/oauth/callback")
def oauth_callback():
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

    # Copy refresh_token ONCE and store in Render
    return jsonify({
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "sites": sites
    })

# =====================================================
# EXPORT TO GOOGLE SHEET (CLIENT-FACING)
# =====================================================
@app.route("/export-to-sheet", methods=["GET"])
def export_to_sheet():
    data = request.args

    if data.get("key") != POC_API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    spreadsheet_id = data["sheetId"]
    sheet_id = DATA_SHEET_ID

    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    access_token = get_access_token()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # ---- Fetch GSC data (limit 10) ----
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

    gsc_response = requests.post(gsc_url, json=gsc_payload, headers=headers)
    rows = gsc_response.json().get("rows", [])

    # ---- Prepare rows ----
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

    # ---- Batch update (row 6 onwards) ----
    batch_requests = []

    for i, row in enumerate(values):
        batch_requests.append({
            "updateCells": {
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": 5 + i,
                    "columnIndex": 0
                },
                "rows": [{
                    "values": [
                        {"userEnteredValue": {"stringValue": str(cell)}}
                        for cell in row
                    ]
                }],
                "fields": "userEnteredValue"
            }
        })

    batch_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"

    batch_response = requests.post(
        batch_url,
        json={"requests": batch_requests},
        headers=headers
    )

    return jsonify({
        "status": "success",
        "rows_written": len(values) - 1,
        "batch_status": batch_response.status_code,
        "batch_response": batch_response.text
    })
