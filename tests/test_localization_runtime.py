import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.localization import (
    parse_accept_language,
    reset_current_language,
    resolve_request_language,
    set_current_language,
    translate,
    translate_validation_message,
)
from app.db.base import Base
from app.models.auth import User
from app.services.notification_service import NotificationService


class LocalizationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.service = NotificationService(self.db)

        self.user = User(
            username="localized-user",
            password_hash="hash",
            is_active=True,
            must_change_password=False,
            language="fr",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_accept_language_parser_prefers_supported_base_language(self):
        self.assertEqual(parse_accept_language("ar-DZ,fr-FR;q=0.8,en;q=0.6"), "ar")
        self.assertEqual(parse_accept_language("de-DE,en-US;q=0.9"), "en")

    def test_request_language_prefers_user_language_over_header(self):
        resolved = resolve_request_language(
            accept_language="ar-DZ,fr-FR;q=0.8",
            user_language="fr",
        )
        self.assertEqual(resolved, "fr")

    def test_system_notifications_render_in_the_active_language(self):
        self.service.notify_user(
            user_id=self.user.id,
            notification_type="system",
            title="",
            message="",
            title_key="notifications.password_changed_title",
            message_key="notifications.password_changed_message",
            is_system_content=True,
        )
        self.db.commit()

        token = set_current_language("fr")
        try:
            french_item = self.service.get_user_notifications(user_id=self.user.id).items[0]
            self.assertEqual(french_item.title, translate("notifications.password_changed_title"))
            self.assertEqual(french_item.message, translate("notifications.password_changed_message"))
        finally:
            reset_current_language(token)

        token = set_current_language("ar")
        try:
            arabic_item = self.service.get_user_notifications(user_id=self.user.id).items[0]
            self.assertEqual(arabic_item.title, translate("notifications.password_changed_title"))
            self.assertEqual(arabic_item.message, translate("notifications.password_changed_message"))
        finally:
            reset_current_language(token)

    def test_manual_notification_content_is_not_retranslated(self):
        self.service.notify_user(
            user_id=self.user.id,
            notification_type="general",
            title="Custom title",
            message="Custom body",
            is_system_content=False,
        )
        self.db.commit()

        token = set_current_language("ar")
        try:
            item = self.service.get_user_notifications(user_id=self.user.id).items[0]
            self.assertEqual(item.title, "Custom title")
            self.assertEqual(item.message, "Custom body")
        finally:
            reset_current_language(token)

    def test_validation_messages_translate_with_prefix_matching(self):
        token = set_current_language("fr")
        try:
            self.assertEqual(
                translate_validation_message("amount must be greater than zero"),
                translate("validation.amount_positive"),
            )
            self.assertEqual(
                translate_validation_message("adjustment_type must be one of ['bonus', 'deduction']"),
                translate("validation.adjustment_type_invalid"),
            )
        finally:
            reset_current_language(token)


if __name__ == "__main__":
    unittest.main()
