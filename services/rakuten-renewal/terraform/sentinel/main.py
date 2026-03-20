"""Rakuten Email Sentinel — GCP Cloud Function.

Receives inbound emails via SendGrid Inbound Parse webhook,
classifies them with Gemini, and stores 2FA codes or manual keys
in Firestore for the local renewal agent to consume.
"""

import json
import os
import logging

import functions_framework
from google.cloud import firestore
from google.cloud import aiplatform
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@your-domain.com")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

db = firestore.Client(project=PROJECT)

# Gemini model for email classification
CLASSIFICATION_PROMPT = """Classify this email. Determine if it is:
1. A Rakuten 2FA verification code email
2. A reply containing API keys (from a human operator)
3. An unrelated email

If it contains a verification code, extract the numeric code.
If it contains API keys, extract the service_secret and license_key.

You MUST respond with ONLY a JSON object:
{
  "type": "2fa_code" | "api_key" | "irrelevant",
  "value": "<extracted code or null>",
  "service_secret": "<extracted key or null>",
  "license_key": "<extracted key or null>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence explanation>"
}"""


def _classify_email(subject: str, body: str) -> dict:
    """Use Gemini to classify the email content."""
    from vertexai.generative_models import GenerativeModel

    aiplatform.init(project=PROJECT)
    model = GenerativeModel("gemini-3.0-flash")

    response = model.generate_content(
        [
            CLASSIFICATION_PROMPT,
            f"Subject: {subject}\n\nBody:\n{body}",
        ],
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "max_output_tokens": 512,
        },
    )
    return json.loads(response.text)


def _store_2fa_code(code: str) -> None:
    """Store 2FA code in Firestore for the agent to poll."""
    doc_ref = db.collection("auth").document("rakuten").collection("data").document("current_2fa")
    doc_ref.set({
        "code": code,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "consumed": False,
        "consumed_at": None,
    })
    log.info("Stored 2FA code in Firestore")


def _store_manual_key(service_secret: str, license_key: str) -> None:
    """Store manually-submitted API keys in Firestore."""
    doc_ref = db.collection("auth").document("rakuten").collection("data").document("manual_key")
    doc_ref.set({
        "service_secret": service_secret,
        "license_key": license_key,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "consumed": False,
        "consumed_at": None,
    })
    log.info("Stored manual API key in Firestore")


def _forward_email(sender: str, subject: str, body: str) -> None:
    """Forward irrelevant email to admin."""
    log.info("Forwarding irrelevant email from %s: %s", sender, subject)
    # Forward via SendGrid would require a SendGrid API key in env
    # For now, just log it


@functions_framework.http
def handle_inbound_email(request):
    """HTTP entry point for SendGrid Inbound Parse webhook."""
    # Basic webhook validation
    if WEBHOOK_SECRET:
        provided = request.args.get("secret", "")
        if provided != WEBHOOK_SECRET:
            log.warning("Invalid webhook secret")
            return ("Unauthorized", 401)

    # Parse SendGrid Inbound Parse multipart form
    sender = request.form.get("from", "")
    subject = request.form.get("subject", "")
    text_body = request.form.get("text", "")
    html_body = request.form.get("html", "")

    # Prefer text body, fall back to HTML
    body = text_body or html_body
    if not body:
        log.warning("Empty email body from %s", sender)
        return ("OK", 200)

    log.info("Received email from %s, subject: %s", sender, subject)

    try:
        classification = _classify_email(subject, body)
    except Exception:
        log.exception("Gemini classification failed")
        return ("Internal error", 500)

    email_type = classification.get("type", "irrelevant")
    confidence = classification.get("confidence", 0)

    log.info("Classification: type=%s confidence=%.2f", email_type, confidence)

    if email_type == "2fa_code" and confidence > 0.5:
        code = classification.get("value")
        if code:
            _store_2fa_code(code)
        else:
            log.warning("2FA email detected but no code extracted")

    elif email_type == "api_key" and confidence > 0.5:
        ss = classification.get("service_secret", "")
        lk = classification.get("license_key", "")
        if ss or lk:
            _store_manual_key(ss, lk)
        else:
            log.warning("API key email detected but no keys extracted")

    else:
        _forward_email(sender, subject, body)

    return ("OK", 200)
