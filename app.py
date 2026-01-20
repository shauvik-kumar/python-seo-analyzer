@app.route("/export-to-sheet", methods=["GET"])
def export_to_sheet():
    data = request.args

    # --- API key check ---
    if data.get("key") != POC_API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    sheet_id = data["sheetId"]
    site = data["site"]
    start_date = data["startDate"]
    end_date = data["endDate"]

    access_token = GSC_ACCESS_TOKEN

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    TAB_NAME = "Data"   # <-- THIS MUST MATCH THE SHEET TAB NAME EXACTLY

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

    gsc_res = requests.post(gsc_url, json=gsc_payload, headers=headers)
    gsc_data = gsc_res.json()
    rows = gsc_data.get("rows", [])

    # --------------------
    # 2. Prepare values
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
    # 3. CLEAR data area (safe, no overwrite of controls)
    # --------------------
    clear_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{sheet_id}/values/{TAB_NAME}!A6:Z1000:clear"
    )

    requests.post(clear_url, headers=headers)

    # --------------------
    # 4. WRITE data starting at A6
    # --------------------
    write_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{sheet_id}/values/{TAB_NAME}!A6?valueInputOption=RAW"
    )

    write_res = requests.put(
        write_url,
        json={"values": values},
        headers=headers
    )

    return jsonify({
        "status": "success",
        "rows_written": len(values) - 1,
        "sheets_write_status": write_res.status_code,
        "sheets_write_response": write_res.text
    })
