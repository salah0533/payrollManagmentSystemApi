import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.responses import api_success
from app.exceptions.base_exception import ConflictException
from app.exceptions.handlers import register_exception_handlers


class ValidationPayload(BaseModel):
    employee_id: int
    year_month: str


def build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/success")
    def success():
        return api_success({"ok": True}, message="created", status_code=201)

    @app.get("/app-error")
    def app_error():
        raise ConflictException("Vacation overlap", code="vacation_overlap")

    @app.get("/http-error")
    def http_error():
        raise HTTPException(status_code=404, detail="Employee not found")

    @app.get("/unexpected")
    def unexpected():
        raise RuntimeError("secret stack trace")

    @app.post("/validate")
    def validate(payload: ValidationPayload):
        return api_success(payload.model_dump())

    return app


class ResponseHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(build_test_app(), raise_server_exceptions=False)

    def test_success_response_helper_shape(self):
        response = self.client.get("/success")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            {
                "message": "created",
                "data": {"ok": True},
                "status": True,
            },
        )

    def test_app_exception_uses_standard_error_envelope(self):
        response = self.client.get("/app-error")
        body = response.json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(body["status"])
        self.assertEqual(body["message"], "Vacation overlap")
        self.assertEqual(body["detail"], "Vacation overlap")
        self.assertEqual(body["error_code"], "vacation_overlap")
        self.assertEqual(body["errors"], [])

    def test_http_exception_is_normalized(self):
        response = self.client.get("/http-error")
        body = response.json()

        self.assertEqual(response.status_code, 404)
        self.assertFalse(body["status"])
        self.assertEqual(body["message"], "Employee not found")
        self.assertEqual(body["error_code"], "not_found")

    def test_validation_errors_include_field_level_details(self):
        response = self.client.post("/validate", json={"year_month": "2026-05"})
        body = response.json()

        self.assertEqual(response.status_code, 422)
        self.assertFalse(body["status"])
        self.assertEqual(body["message"], "Validation failed")
        self.assertTrue(body["errors"])
        self.assertEqual(body["errors"][0]["field"], "employee_id")
        self.assertEqual(body["errors"][0]["location"], "body")

    def test_unexpected_exceptions_hide_internal_details(self):
        response = self.client.get("/unexpected")
        body = response.json()

        self.assertEqual(response.status_code, 500)
        self.assertFalse(body["status"])
        self.assertEqual(body["message"], "An unexpected server error occurred")
        self.assertNotIn("secret stack trace", response.text)


if __name__ == "__main__":
    unittest.main()
