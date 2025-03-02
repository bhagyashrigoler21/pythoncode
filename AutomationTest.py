from flask import Flask, jsonify, request
import imaplib
import email
from email.header import decode_header
import pdfplumber
import pandas as pd
import os
import json
import requests

app = Flask(__name__)
app.config["DEBUG"] = True  # Enable debugging

# Root Route to Prevent 404
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Email processing API is running"}), 200

# Handle favicon.ico requests to prevent 404 spam in logs
@app.route("/favicon.ico")
def favicon():
    return "", 204

# API Route to Process Emails
@app.route("/fetch-emails", methods=["POST"])
def fetch_emails():
    try:
        # Get credentials from request
        data = request.json
        email_user = data.get("email_user")
        email_pass = data.get("email_pass")

        if not email_user or not email_pass:
            return jsonify({"error": "Email and password are required"}), 400

        # Connect to the mail server (Gmail example)
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        try:
            mail.login(email_user, email_pass)
        except imaplib.IMAP4.error:
            return jsonify({"error": "Login failed. Check email or password."}), 401

        mail.select("inbox")

        # Search for emails
        status, email_ids = mail.search(None, "ALL")

        # Fix: Initialize messages properly
        messages = email_ids[0].split() if status == "OK" else []

        if not messages:
            return jsonify({"message": "No emails with attachments found."}), 200

        all_data = []
        for num in messages:
            status, msg_data = mail.fetch(num, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")

                    # Check for attachments
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_disposition = str(part.get("Content-Disposition"))
                            if "attachment" in content_disposition:
                                filename = part.get_filename()
                                if filename and filename.endswith(".pdf"):
                                    pdf_path = os.path.join(os.getcwd(), filename)
                                    with open(pdf_path, "wb") as f:
                                        f.write(part.get_payload(decode=True))

                                    # Extract data from PDF
                                    try:
                                        with pdfplumber.open(pdf_path) as pdf:
                                            text = pdf.pages[0].extract_text()
                                        if not text:
                                            continue  # Skip empty PDFs
                                    except Exception as e:
                                        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500

                                    # Process PDF data
                                    data = [line.split() for line in text.split("\n") if len(line.split()) >= 2]
                                    num_cols = max(len(row) for row in data)  # Find max columns in extracted data
                                    column_names = [f"Col_{i+1}" for i in range(num_cols)]  # Generate column names

                                    # Create DataFrame
                                    df = pd.DataFrame(data, columns=column_names)

                                    # Convert DataFrame to JSON
                                    data_json = df.to_dict(orient="records")
                                    all_data.append({"subject": subject, "data": data_json})

                                    # Send Data to ERP API
                                    api_url = "http://192.168.0.1:80/endpoint"
                                    headers = {
                                        "Content-Type": "application/json",
                                        "Authorization": "Bearer YOUR_API_TOKEN",
                                        "Connection": "close"
                                    }
                                    #response = requests.post(api_url, data=json.dumps(data_json), headers=headers, verify=False)
                                    response = requests.post(api_url, data=json.dumps(data_json), headers=headers, verify=False)
                                    


                                    if response.status_code != 200:
                                        return jsonify({"error": "Failed to send data to ERP"}), 500

        mail.logout()
        return jsonify({"message": "Emails processed successfully", "data": all_data}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Run Flask App
"""if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)"""
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True, use_reloader=False)

