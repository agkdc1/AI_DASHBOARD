"""Shared test helper factories — imported by conftest.py and test modules."""

from unittest.mock import MagicMock


def make_gemini_response(text: str) -> MagicMock:
    """Create a mock Gemini response with .text attribute."""
    resp = MagicMock()
    resp.text = text
    return resp


def make_gemini_model(response_text: str = "テスト応答") -> MagicMock:
    """Create a mock GenerativeModel that returns a fixed text response."""
    model = MagicMock()
    model.generate_content = MagicMock(
        return_value=make_gemini_response(response_text)
    )
    return model


def make_speech_response(transcript: str = "テスト会議の内容です。") -> MagicMock:
    """Create a mock Speech-to-Text response."""
    alt = MagicMock()
    alt.transcript = transcript

    result = MagicMock()
    result.alternatives = [alt]

    response = MagicMock()
    response.results = [result]
    return response


def make_speech_client(transcript: str = "テスト会議の内容です。") -> MagicMock:
    """Create a mock SpeechClient that returns a fixed transcript."""
    client = MagicMock()
    client.recognize = MagicMock(return_value=make_speech_response(transcript))
    return client


def make_gcs_blob(name: str, content: str = "", time_created=None) -> MagicMock:
    """Create a mock GCS blob."""
    blob = MagicMock()
    blob.name = name
    blob.time_created = time_created
    blob.download_as_text = MagicMock(return_value=content)
    blob.upload_from_string = MagicMock()
    return blob


def make_gcs_bucket(blobs: list | None = None) -> MagicMock:
    """Create a mock GCS bucket."""
    bucket = MagicMock()
    bucket.list_blobs = MagicMock(return_value=blobs or [])
    bucket.blob = MagicMock(return_value=make_gcs_blob("test"))
    return bucket


def make_gcs_client(bucket: MagicMock | None = None) -> MagicMock:
    """Create a mock storage.Client."""
    client = MagicMock()
    client.bucket = MagicMock(return_value=bucket or make_gcs_bucket())
    return client


def make_ldap_conn() -> MagicMock:
    """Create a mock LDAP connection with standard methods."""
    conn = MagicMock()
    conn.simple_bind_s = MagicMock()
    conn.search_s = MagicMock(return_value=[])
    conn.add_s = MagicMock()
    conn.modify_s = MagicMock()
    conn.delete_s = MagicMock()
    return conn


def make_sm_client() -> MagicMock:
    """Create a mock Secret Manager client."""
    client = MagicMock()
    client.access_secret_version = MagicMock()
    client.add_secret_version = MagicMock()
    client.create_secret = MagicMock()
    return client
