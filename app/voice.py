"""Consent-based Twilio voice notifications for new support tickets."""

import re

from flask import current_app
from twilio.base.exceptions import TwilioException
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from app.models import ticket as ticket_model

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_CALL_FAILURE_MESSAGE = "The automated call could not be started. Please contact the customer directly."


class VoiceCallError(Exception):
    """Raised when a ticket's automated call cannot be started."""


def is_valid_e164(phone):
    return bool(_E164_RE.fullmatch(phone or ""))


def _ticket_message(ticket):
    name = ticket["customer_name"].strip() or "there"
    subject = ticket["subject"].strip()[:160]
    return (
        f"Hello {name}. This is an automated update from Dispatch Support. "
        f"We received your support request {ticket['ticket_id']} about {subject}. "
        "We understand this is causing difficulty. Our support team will review "
        "your request and work to resolve it as soon as possible."
    )


def place_ticket_call(ticket):
    config = current_app.config
    account_sid = config["TWILIO_ACCOUNT_SID"]
    auth_token = config["TWILIO_AUTH_TOKEN"]
    from_number = config["TWILIO_FROM_NUMBER"]
    if not all((account_sid, auth_token, from_number)):
        raise VoiceCallError("Twilio voice calling is not configured.")

    response = VoiceResponse()
    response.say(_ticket_message(ticket), voice="alice", language="en-US")
    response.hangup()

    try:
        client = Client(account_sid, auth_token)
        call = client.calls.create(
            to=ticket["customer_phone"],
            from_=from_number,
            twiml=str(response),
        )
    except TwilioException as exc:
        raise VoiceCallError("Twilio could not start the call.") from exc
    return call.sid


def notify_ticket_customer(ticket):
    if not ticket.get("call_consent"):
        return "not_requested"

    try:
        call_sid = place_ticket_call(ticket)
    except VoiceCallError:
        ticket_model.record_voice_call(ticket["ticket_id"], "failed")
        current_app.logger.warning("Automated call failed for ticket %s", ticket["ticket_id"])
        return "failed"

    ticket_model.record_voice_call(ticket["ticket_id"], "queued", call_sid=call_sid)
    return "queued"


def call_failure_message():
    return _CALL_FAILURE_MESSAGE
