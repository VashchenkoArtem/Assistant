import json
import os
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from django.test import SimpleTestCase

from core import views


class AssistantBackendTests(SimpleTestCase):
    def test_health_endpoint_reports_ready_backend(self) -> None:
        with patch.object(views, "_get_command", return_value=Mock()):
            response = self.client.get("/api/assistant/health/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_command_endpoint_returns_only_assistant_output(self) -> None:
        command = Mock()

        def process(text: str) -> None:
            print("Привіт, рада тебе бачити!")

        command.process_recognized_command.side_effect = process

        with patch.object(views, "_get_command", return_value=command):
            response = self.client.post(
                "/api/assistant/command/",
                data=json.dumps({"text": "привіт"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["output"], "Привіт, рада тебе бачити!")

    def test_command_endpoint_hides_internal_exception_details(self) -> None:
        command = Mock()
        command.process_recognized_command.side_effect = RuntimeError(
            "secret internal traceback detail"
        )

        with patch.object(views, "_get_command", return_value=command):
            response = self.client.post(
                "/api/assistant/command/",
                data=json.dumps({"text": "відкрий секрет"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertNotIn("secret internal traceback detail", payload["message"])

# Create your tests here.
