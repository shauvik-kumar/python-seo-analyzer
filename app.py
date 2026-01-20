@app.route("/export-to-sheet", methods=["GET"])
def export_to_sheet():
    data = request.args

    if data.get("key") != POC_API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    spreadsheet_id = data["sheetId"]
    sheet_id = int(os.environ["DATA_SHEET_ID"])  # numeric gid

    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    access_token = GSC_ACCESS_TOKEN

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 1️⃣ Fetch GSC data
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

    # 2️⃣ Build rows (header + data)
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

    # 3️⃣ Convert to batchUpdate requests (START AT ROW 6)
    requests_body = []

    for row_index, row in enumerate(values):
        requests_body.append({
            "updateCells": {
                "rows": [{
                    "values": [
                        {"userEnteredValue": {"stringValue": str(cell)}}
                        for cell in row
                    ]
                }],
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": 5 + row_index,   # row 6
                    "columnIndex": 0
                },
                "fields": "userEnteredValue"
            }
        })

    batch_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"

    batch_res = requests.post(
        batch_url,
        json={"requests": requests_body},
        headers=headers
    )

    return jsonify({
        "status": "success",
        "rows_written": len(values) - 1,
        "batch_status": batch_res.status_code,
        "batch_response": batch_res.text
    })
