"""Tests for the Weekly Evolution service."""

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from helpers import make_gemini_model, make_gcs_blob, make_gcs_bucket, make_gcs_client


def _patch_gcs(gcs_client):
    """Patch google.cloud.storage at sys.modules level for lazy imports."""
    mock_mod = MagicMock()
    mock_mod.Client.return_value = gcs_client
    return patch.dict("sys.modules", {
        "google.cloud.storage": mock_mod,
        "google.cloud": MagicMock(storage=mock_mod),
    })


class TestRunWeeklyAnalysis:
    async def test_full_cycle(self, evolution_service):
        now = datetime.now(timezone.utc)
        blob = make_gcs_blob("interactions/log1.json", "テストログ", time_created=now)
        bucket = make_gcs_bucket([blob])
        gcs_client = make_gcs_client(bucket)

        with _patch_gcs(gcs_client), \
             patch("evolution.service.smtplib.SMTP") as mock_smtp, \
             respx.mock:
            instance = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=instance)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            # Vikunja project list + task creation
            respx.get("https://vikunja.test/api/v1/projects").mock(
                return_value=httpx.Response(200, json=[{"id": 1}])
            )
            respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
                return_value=httpx.Response(201, json={"id": 10})
            )

            result = await evolution_service.run_weekly_analysis()

        assert "proposal" in result
        assert result["proposal"] != "ログがありません"

    async def test_no_logs(self, evolution_service):
        bucket = make_gcs_bucket([])
        gcs_client = make_gcs_client(bucket)

        with _patch_gcs(gcs_client):
            result = await evolution_service.run_weekly_analysis()

        assert result["proposal"] == "ログがありません"
        assert result["email_sent"] is False
        assert result["task_created"] is False


class TestFetchWeeklyLogs:
    async def test_success(self, evolution_service):
        now = datetime.now(timezone.utc)
        blobs = [
            make_gcs_blob("interactions/1.json", "ログ1", time_created=now),
            make_gcs_blob("interactions/2.json", "ログ2", time_created=now),
        ]
        bucket = make_gcs_bucket(blobs)
        gcs_client = make_gcs_client(bucket)

        with _patch_gcs(gcs_client):
            result = await evolution_service._fetch_weekly_logs()

        assert "ログ1" in result
        assert "ログ2" in result
        assert "---" in result

    async def test_no_blobs(self, evolution_service):
        bucket = make_gcs_bucket([])
        gcs_client = make_gcs_client(bucket)

        with _patch_gcs(gcs_client):
            result = await evolution_service._fetch_weekly_logs()

        assert result == ""

    async def test_gcs_error(self, evolution_service):
        mock_mod = MagicMock()
        mock_mod.Client.side_effect = Exception("GCS down")
        with patch.dict("sys.modules", {"google.cloud.storage": mock_mod, "google.cloud": MagicMock(storage=mock_mod)}):
            result = await evolution_service._fetch_weekly_logs()
        assert result == ""


class TestAnalyzeLogs:
    async def test_success(self, evolution_service):
        result = await evolution_service._analyze_logs("テストログデータ")
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_truncation(self, evolution_service):
        long_logs = "x" * 200_000
        await evolution_service._analyze_logs(long_logs)
        call_args = evolution_service._model.generate_content.call_args
        prompt_text = call_args[0][0][0]["parts"][0]["text"]
        assert "truncated" in prompt_text

    async def test_error(self, evolution_service):
        evolution_service._model.generate_content.side_effect = Exception("Model error")
        result = await evolution_service._analyze_logs("logs")
        assert "エラー" in result


class TestSendEmail:
    async def test_success(self, evolution_service):
        with patch("evolution.service.smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=instance)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = await evolution_service._send_email("テスト提案")
        assert result is True

    async def test_failure(self, evolution_service):
        with patch("evolution.service.smtplib.SMTP", side_effect=Exception("SMTP down")):
            result = await evolution_service._send_email("テスト提案")
        assert result is False

    async def test_subject_format(self, evolution_service):
        with patch("evolution.service.smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=instance)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            await evolution_service._send_email("提案")
            # Verify send_message was called
            instance.send_message.assert_called_once()


class TestCreateReviewTask:
    @respx.mock
    async def test_success(self, evolution_service):
        respx.get("https://vikunja.test/api/v1/projects").mock(
            return_value=httpx.Response(200, json=[{"id": 5}])
        )
        respx.put("https://vikunja.test/api/v1/projects/5/tasks").mock(
            return_value=httpx.Response(201, json={"id": 10})
        )
        result = await evolution_service._create_review_task("テスト提案")
        assert result is True

    @respx.mock
    async def test_no_projects(self, evolution_service):
        respx.get("https://vikunja.test/api/v1/projects").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await evolution_service._create_review_task("提案")
        assert result is False

    @respx.mock
    async def test_error(self, evolution_service):
        respx.get("https://vikunja.test/api/v1/projects").mock(
            return_value=httpx.Response(500)
        )
        result = await evolution_service._create_review_task("提案")
        assert result is False


class TestArchiveProposal:
    async def test_success(self, evolution_service):
        bucket = make_gcs_bucket()
        gcs_client = make_gcs_client(bucket)

        with _patch_gcs(gcs_client):
            await evolution_service._archive_proposal("テスト提案")

        bucket.blob.assert_called_once()
        blob = bucket.blob.return_value
        blob.upload_from_string.assert_called_once()

    async def test_error(self, evolution_service):
        mock_mod = MagicMock()
        mock_mod.Client.side_effect = Exception("GCS error")
        with patch.dict("sys.modules", {"google.cloud.storage": mock_mod, "google.cloud": MagicMock(storage=mock_mod)}):
            # Should not raise
            await evolution_service._archive_proposal("テスト提案")
