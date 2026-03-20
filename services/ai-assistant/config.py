"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8030

    # Company identity (configurable per locale)
    company_name_ja: str = "シンビジャパン"
    company_name_ko: str = "신비재팬"
    company_name_en: str = "Shinbee Japan"

    # GCP
    gcp_project: str = "your-gcp-project-id"
    gcp_location: str = "asia-northeast1"

    # Gemini
    gemini_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    gemini_image_model: str = "gemini-2.5-flash-image"

    # GCS buckets
    pii_raw_bucket: str = "your-project-pii-raw"
    ai_logs_bucket: str = "your-project-ai-logs"

    # PII masking
    pii_raw_retention_days: int = 7

    # Vikunja
    vikunja_url: str = "https://tasks.your-domain.com"
    vikunja_token: str = ""

    # Email
    superuser_email: str = "admin@your-domain.com"
    smtp_host: str = "localhost"
    smtp_port: int = 25

    # Context cache
    sop_bucket: str = "your-project-ai-sops"

    # LDAP (Samba AD — phone provisioning)
    ldap_server: str = "ldap://samba-ad-internal.shinbee.svc.cluster.local:389"
    ldap_base_dn: str = "DC=shinbee,DC=local"
    ldap_bind_dn: str = "CN=Administrator,CN=Users,DC=shinbee,DC=local"
    ldap_bind_password: str = ""

    # Faxapi (Asterisk extension management via SQLite + confgen)
    faxapi_url: str = "http://10.0.0.254:8010"
    faxapi_key: str = ""

    # Rakuten API key management
    rakuten_reminder_days: int = 80
    rakuten_deadline_days: int = 90
    rakuten_vikunja_project_id: int = 1

    # IAM
    iam_db_path: str = "/app/data/iam.db"

    # Seating / hot-desking
    seating_db_path: str = "/app/data/seating.db"
    floorplan_dir: str = "/app/data/floorplans"
    phone_admin_password: str = ""

    # Google Drive — fax review
    drive_folder_under_review: str = ""
    drive_folder_reviewed: str = ""

    # Phone auto-provisioning
    extension_range_start: int = 300
    extension_range_end: int = 399

    # Password sync (GSPS — AD + Google Workspace)
    gsps_sa_key_path: str = "/etc/gsps/key.json"
    gsps_admin_email: str = "admin@your-domain.com"

    model_config = {"env_prefix": "AI_"}

    def company_name(self, lang: str = "ja") -> str:
        """Get company name for a given language code."""
        return {
            "ja": self.company_name_ja,
            "ko": self.company_name_ko,
            "en": self.company_name_en,
        }.get(lang, self.company_name_en)


settings = Settings()
