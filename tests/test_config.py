import os
import unittest
from unittest.mock import patch

from app.core.config import Settings


class SettingsConfigTests(unittest.TestCase):
    def test_defaults_match_current_runtime_expectations(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertEqual(settings.database_url, "sqlite:///./app.db")
        self.assertEqual(settings.api_host, "127.0.0.1")
        self.assertEqual(settings.api_port, 8000)
        self.assertEqual(settings.cors_origins, ("*",))

    def test_api_port_is_parsed_from_environment(self):
        with patch.dict(os.environ, {"API_PORT": "9001"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.api_port, 9001)

    def test_api_workers_is_parsed_from_environment(self):
        with patch.dict(os.environ, {"API_WORKERS": "4"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.api_workers, 4)

    def test_cors_origins_are_split_and_trimmed(self):
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": " http://localhost:3000 , http://127.0.0.1:8080 , "},
            clear=True,
        ):
            settings = Settings()

        self.assertEqual(
            settings.cors_origins,
            ("http://localhost:3000", "http://127.0.0.1:8080"),
        )


if __name__ == "__main__":
    unittest.main()
