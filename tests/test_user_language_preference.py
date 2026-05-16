import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.localization import LanguageCode
from app.db.base import Base
from app.models.auth import User
from app.schemas.auth import UpdateLanguageRequest
from app.services.auth_service import update_language
from app.services.user_service import ensure_user_language_schema, serialize_auth_me


class UserLanguagePreferenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_update_language_persists_account_preference(self):
        session = self.SessionLocal()
        try:
            user = User(
                username="admin",
                email="admin@example.com",
                password_hash="hashed",
                language="en",
                is_active=True,
                must_change_password=False,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            response = update_language(user, UpdateLanguageRequest(language=LanguageCode.ar), session)
            session.refresh(user)

            self.assertEqual(response.language.value, "ar")
            self.assertEqual(user.language, "ar")
        finally:
            session.close()

    def test_serialize_auth_me_normalizes_invalid_language(self):
        session = self.SessionLocal()
        try:
            user = User(
                username="operator",
                email="operator@example.com",
                password_hash="hashed",
                language="es",
                is_active=True,
                must_change_password=False,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            serialized = serialize_auth_me(user)
            self.assertEqual(serialized.language.value, "en")
        finally:
            session.close()

    def test_schema_helper_adds_language_column_for_existing_users_table(self):
        legacy_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        LegacySession = sessionmaker(bind=legacy_engine, autoflush=False, autocommit=False)

        with legacy_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        employee_id INTEGER NULL,
                        username VARCHAR(50) NOT NULL,
                        email VARCHAR(255) NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        must_change_password BOOLEAN NOT NULL DEFAULT 0,
                        last_login_at DATETIME NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        deleted_at DATETIME NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, username, email, password_hash, is_active, must_change_password, created_at, updated_at
                    ) VALUES (
                        1, 'legacy-admin', 'legacy@example.com', 'hashed', 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        session = LegacySession()
        try:
            ensure_user_language_schema(session)
            session.commit()

            columns = {column["name"] for column in inspect(legacy_engine).get_columns("users")}
            self.assertIn("language", columns)

            stored_language = session.execute(text("SELECT language FROM users WHERE id = 1")).scalar_one()
            self.assertEqual(stored_language, "en")
        finally:
            session.close()
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
