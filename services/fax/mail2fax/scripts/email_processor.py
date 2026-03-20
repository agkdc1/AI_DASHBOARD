#!/usr/bin/env python3
"""Postfix pipe transport: extract PDF from email and POST to fax API."""

import email
import email.policy
import os
import re
import sys
import tempfile

import requests
import yaml

# Postfix exit codes
EX_OK = 0
EX_DATAERR = 65      # bad input data — permanent failure
EX_TEMPFAIL = 75     # temporary failure — Postfix will retry

CONFIG_PATH = "/app/config.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def extract_did(recipient):
    """Extract DID number from recipient address (e.g. 0312345678@fax)."""
    match = re.match(r"^(\d+)@", recipient)
    if not match:
        return None
    return match.group(1)


def extract_pdf(msg):
    """Return (filename, pdf_bytes) for the first PDF attachment, or None."""
    for part in msg.walk():
        content_type = part.get_content_type()
        filename = part.get_filename()

        if content_type == "application/pdf" or (
            filename and filename.lower().endswith(".pdf")
        ):
            payload = part.get_payload(decode=True)
            if payload:
                return (filename or "fax.pdf", payload)
    return None


def main():
    # Recipient is passed as command-line argument by Postfix
    if len(sys.argv) < 2:
        print("Usage: email_processor.py <recipient>", file=sys.stderr)
        sys.exit(EX_DATAERR)

    recipient = sys.argv[1]
    did = extract_did(recipient)
    if not did:
        print(f"Invalid recipient (no DID): {recipient}", file=sys.stderr)
        sys.exit(EX_DATAERR)

    # Read email from stdin
    raw = sys.stdin.buffer.read()
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    # Extract PDF
    pdf = extract_pdf(msg)
    if pdf is None:
        print("No PDF attachment found in email.", file=sys.stderr)
        sys.exit(EX_DATAERR)

    filename, pdf_bytes = pdf
    print(f"Sending fax to {did}, PDF: {filename} ({len(pdf_bytes)} bytes)",
          file=sys.stderr)

    # Load config for API details
    config = load_config()
    endpoint = config["fax_api"]["endpoint"]
    api_key = config["fax_api"]["api_key"]

    # POST to fax API
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            resp = requests.post(
                endpoint,
                files={"file": (filename, f, "application/pdf")},
                data={"number": did},
                headers={"X-API-Key": api_key},
                timeout=30,
            )

        os.unlink(tmp_path)

        if resp.status_code == 200:
            print(f"Fax queued successfully: {resp.json()}", file=sys.stderr)
            sys.exit(EX_OK)
        else:
            print(f"API error {resp.status_code}: {resp.text}", file=sys.stderr)
            # 4xx = permanent, 5xx = temporary
            if 400 <= resp.status_code < 500:
                sys.exit(EX_DATAERR)
            sys.exit(EX_TEMPFAIL)

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(EX_TEMPFAIL)


if __name__ == "__main__":
    main()
