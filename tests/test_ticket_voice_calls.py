import unittest
from unittest.mock import patch

from app import auth
from app import create_app
from app import mailer
from app.config import Config
from app.models import ticket as ticket_model
from app.models import user as user_model
from app import voice
from app.voice import place_ticket_call


class TicketVoiceCallTests(unittest.TestCase):
    def setUp(self):
        self.original_mongomock = Config.USE_MONGOMOCK
        Config.USE_MONGOMOCK = True
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            JWT_SECRET_KEY="test-jwt-secret",
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            user = user_model.create_user("agent@example.com", "password123", "Agent")
            token = auth.issue_access_token(user)
        self.client.set_cookie("access_token", token)

    def tearDown(self):
        Config.USE_MONGOMOCK = self.original_mongomock

    def test_ticket_without_call_consent_does_not_call_customer(self):
        with (
            patch("app.voice.place_ticket_call") as place_call,
            patch("app.mailer.send_ticket_created_email", return_value="sent") as send_email,
        ):
            response = self.client.post(
                "/tickets/new",
                data={
                    "customer_name": "Casey",
                    "customer_email": "casey@example.com",
                    "customer_phone": "+14155552671",
                    "subject": "Cannot sign in",
                    "description": "Login fails.",
                },
            )

        self.assertEqual(response.status_code, 302)
        place_call.assert_not_called()
        send_email.assert_called_once()
        ticket = ticket_model.list_tickets()[0]
        self.assertEqual(ticket["customer_phone"], "+14155552671")
        self.assertEqual(ticket["voice_call_status"], "not_requested")
        self.assertEqual(ticket["email_notification_status"], "sent")

    def test_ticket_with_consent_queues_call_and_saves_provider_sid(self):
        with patch("app.voice.place_ticket_call", return_value="CA123") as place_call:
            response = self.client.post(
                "/tickets/new",
                data={
                    "customer_name": "Casey",
                    "customer_email": "casey@example.com",
                    "customer_phone": "+14155552671",
                    "call_consent": "on",
                    "subject": "Cannot sign in",
                    "description": "Login fails.",
                },
            )

        self.assertEqual(response.status_code, 302)
        place_call.assert_called_once()
        ticket = ticket_model.list_tickets()[0]
        self.assertEqual(ticket["voice_call_status"], "queued")
        self.assertEqual(ticket["voice_call_sid"], "CA123")

    def test_api_opt_in_requires_e164_phone_number(self):
        response = self.client.post(
            "/api/tickets",
            json={
                "customer_name": "Casey",
                "customer_email": "casey@example.com",
                "customer_phone": "4155552671",
                "call_consent": True,
                "subject": "Cannot sign in",
                "description": "Login fails.",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ticket_model.list_tickets(), [])

    def test_api_ticket_creation_reports_email_delivery_status(self):
        with patch("app.mailer.send_ticket_created_email", return_value="sent"):
            response = self.client.post(
                "/api/tickets",
                json={
                    "customer_name": "Casey",
                    "customer_email": "casey@example.com",
                    "subject": "Cannot sign in",
                    "description": "Login fails.",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["email_notification_status"], "sent")
        self.assertEqual(
            ticket_model.list_tickets()[0]["email_notification_status"],
            "sent",
        )

    def test_failed_call_keeps_ticket_and_shows_follow_up_warning(self):
        with patch("app.voice.place_ticket_call", side_effect=voice.VoiceCallError):
            response = self.client.post(
                "/tickets/new",
                data={
                    "customer_name": "Casey",
                    "customer_email": "casey@example.com",
                    "customer_phone": "+14155552671",
                    "call_consent": "on",
                    "subject": "Cannot sign in",
                    "description": "Login fails.",
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please contact the customer directly", response.data)
        ticket = ticket_model.list_tickets()[0]
        self.assertEqual(ticket["voice_call_status"], "failed")

    def test_call_speaks_ticket_summary_without_full_description(self):
        self.app.config.update(
            TWILIO_ACCOUNT_SID="ACtest",
            TWILIO_AUTH_TOKEN="test-token",
            TWILIO_FROM_NUMBER="+14155550000",
        )
        ticket = {
            "ticket_id": "TKT-001",
            "customer_name": "Casey",
            "customer_phone": "+14155552671",
            "subject": "Cannot sign in",
            "description": "Private details that should not be read aloud.",
        }

        with self.app.app_context(), patch("app.voice.Client") as client_class:
            client_class.return_value.calls.create.return_value.sid = "CA123"
            call_sid = place_ticket_call(ticket)

        self.assertEqual(call_sid, "CA123")
        twiml = client_class.return_value.calls.create.call_args.kwargs["twiml"]
        self.assertIn("Cannot sign in", twiml)
        self.assertNotIn("Private details", twiml)
        self.assertIn("resolve it as soon as possible", twiml)

    def test_ticket_receipt_email_uses_configured_smtp(self):
        self.app.config.update(
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USE_TLS=True,
            SMTP_USERNAME="sender@example.com",
            SMTP_PASSWORD="smtp-password",
            MAIL_FROM="support@example.com",
        )
        ticket = {
            "ticket_id": "TKT-001",
            "customer_name": "Casey",
            "customer_email": "casey@example.com",
            "subject": "Cannot sign in",
            "description": "Private details are not needed in a receipt.",
        }

        with self.app.app_context(), patch("app.mailer.smtplib.SMTP") as smtp_factory:
            smtp = smtp_factory.return_value.__enter__.return_value
            status = mailer.send_ticket_created_email(ticket)

        self.assertEqual(status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "casey@example.com")
        self.assertIn("TKT-001", message.get_content())
        self.assertIn("Cannot sign in", message.get_content())
        self.assertNotIn("Private details", message.get_content())

    def test_password_recovery_sends_email_and_accepts_reset_token(self):
        with patch("app.routes.views.mailer.send_password_reset_email") as send_email:
            response = self.client.post(
                "/forgot-password",
                data={"email": "agent@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If that email exists", response.data)
        send_email.assert_called_once()
        email, reset_token = send_email.call_args.args
        self.assertEqual(email, "agent@example.com")

        response = self.client.post(
            "/reset-password",
            data={"token": reset_token, "password": "new-password-123"},
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(user_model.authenticate("agent@example.com", "password123"))
            self.assertTrue(user_model.authenticate("agent@example.com", "new-password-123"))


if __name__ == "__main__":
    unittest.main()
