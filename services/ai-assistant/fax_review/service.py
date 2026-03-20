"""Google Drive integration for fax review workflow."""

import logging
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


class FaxReviewService:
    def __init__(self) -> None:
        self._drive = None

    def _get_drive(self):
        if self._drive is None:
            creds = service_account.Credentials.from_service_account_file(
                "/etc/gcs/key.json", scopes=SCOPES,
            )
            self._drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._drive

    async def list_pending(self) -> list[dict]:
        """List PDF+Doc pairs in the 'under review' folder."""
        drive = self._get_drive()
        folder_id = settings.drive_folder_under_review

        # Fetch PDFs (uploaded files)
        pdf_resp = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
            fields="files(id,name,createdTime)",
            orderBy="createdTime desc",
            pageSize=100,
        ).execute()
        pdfs = {f["name"].rsplit(".", 1)[0]: f for f in pdf_resp.get("files", [])}

        # Fetch Google Docs (OCR output)
        doc_resp = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document' and trashed=false",
            fields="files(id,name,createdTime)",
            orderBy="createdTime desc",
            pageSize=100,
        ).execute()
        docs = {f["name"].rsplit(".", 1)[0]: f for f in doc_resp.get("files", [])}

        # Match pairs by base name
        pairs = []
        all_names = set(pdfs.keys()) | set(docs.keys())
        for name in sorted(all_names, key=lambda n: pdfs.get(n, docs.get(n, {})).get("createdTime", ""), reverse=True):
            pdf = pdfs.get(name)
            doc = docs.get(name)
            pairs.append({
                "name": name,
                "pdf_id": pdf["id"] if pdf else None,
                "doc_id": doc["id"] if doc else None,
                "pdf_url": f"https://drive.google.com/file/d/{pdf['id']}/preview" if pdf else None,
                "doc_url": f"https://docs.google.com/document/d/{doc['id']}/edit" if doc else None,
                "created_time": (pdf or doc or {}).get("createdTime"),
            })

        return pairs

    async def approve(self, doc_id: str | None, pdf_id: str | None) -> dict:
        """Move files from 'under review' to 'reviewed' folder."""
        drive = self._get_drive()
        under_review = settings.drive_folder_under_review
        reviewed = settings.drive_folder_reviewed
        moved = []

        for file_id in [pdf_id, doc_id]:
            if not file_id:
                continue
            drive.files().update(
                fileId=file_id,
                addParents=reviewed,
                removeParents=under_review,
            ).execute()
            moved.append(file_id)
            logger.info("Moved file %s to reviewed folder", file_id)

        return {"moved": moved, "status": "approved"}
