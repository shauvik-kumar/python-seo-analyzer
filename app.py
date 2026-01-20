import os
from flask import Flask, redirect, request, jsonify, session
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)
@app.route("/ping")
def ping():
    return "OK"

app.secret_key = "gsc-secret"

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = os.environ["OAUTH_REDIRECT_URI"]

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

@app.route("/")
def home():
    return "GSC backend alive"

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

    session["credentials"] = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": creds.scopes,
}


    service = build("searchconsole", "v1", credentials=creds)
    sites = service.sites().list().execute()

    return jsonify(sites)

import requests

@app.route("/search-analytics", methods=["POST"])
def search_analytics():
    data = request.json

    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    creds = session.get("credentials")
    if not creds:
        return jsonify({"error": "Not authenticated"}), 401

    access_token = creds["token"]

    url = f"https://www.googleapis.com/webmasters/v3/sites/{site.replace('/', '%2F')}/searchAnalytics/query"

    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query"],
        "rowLimit": 50
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)

    return jsonify(r.json())

