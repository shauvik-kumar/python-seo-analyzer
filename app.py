import os
import requests
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# =====================================================
# APP SETUP  (THIS MUST COME BEFORE ANY @app.route)
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
GSC_ACCESS_TOKEN = os.environ["GSC_ACCESS_TOKEN"]
DATA_SHEET_ID = int(os.environ["DATA_SHEET_ID"])  # gid, you set = 0

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

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
# OAUTH (FOR YOU ONLY – TOKEN GENERATION)
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
        prompt="consent"
    )
    return redirect(auth_url)

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

    # Copy access_token from here → put into Render env as GSC_ACCESS_TOKEN
    return jsonify({
        "access_token": creds.token,
        "sites": sites
    })

# =====================================================
# EXPORT TO GOOGLE SHEET (CLIENT-FACING, PoC)
# =====================================================
@app.route("/export-to-sheet", methods=["GET"])
def export_to_sheet():
    data = request.args

    # ---- API KEY CHECK ----
    if data.get("key") != POC_API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    spreadsheet_id = data["sheetId"]          # long spreadsheet ID
    sheet_id = DATA_SHEET_ID                  # numeric gid (0)

    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    headers = {
        "Authorization": f"Bearer {GSC_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # -------------------------------------------------
    # 1) FETCH GSC DATA (LIMIT 10)
    # -------------------------------------------------
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

    gsc_res = requests.post(gsc_url, json=gsc_payload, headers=headers)
    rows = gsc_res.json().get("rows", [])

    # -------------------------------------------------
    # 2) BUILD ROWS (HEADER + DATA)
    # -------------------------------------------------
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

    # -------------------------------------------------
    # 3) BATCH UPDATE (WRITE FROM ROW 6)
    # -------------------------------------------------
    batch_requests = []

    for row_index, row in enumerate(values):
        batch_requests.append({
            "updateCells": {
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": 5 + row_index,   # row 6 onward
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

    batch_res = requests.post(
        batch_url,
        json={"requests": batch_requests},
        headers=headers
    )

    return jsonify({
        "status": "success",
        "rows_written": len(values) - 1,
        "batch_status": batch_res.status_code,
        "batch_response": batch_res.text
    })
