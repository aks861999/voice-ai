import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ConversationState(Enum):
    GREETING = "greeting"
    GET_NAME = "get_name"
    GET_EMAIL = "get_email"
    CONFIRM = "confirm"
    COMPLETE = "complete"

class AppointmentScheduler(AudioLoop):
    def __init__(self, doctor_name: str):
        super().__init__(config={
            "generation_config": {
                "response_modalities": ["AUDIO", "TEXT"]
            }
        })
        self.doctor_name = doctor_name
        self.state = ConversationState.GREETING
        self.patient_name = None
        self.patient_email = None
        self.calendar_service = self._setup_calendar()
    
    def _setup_calendar(self):
        """Setup Google Calendar API with service account"""
        credentials = service_account.Credentials.from_service_account_file(
            'service-account.json',
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        return build('calendar', 'v3', credentials=credentials)

    def _schedule_appointment(self):
        """Schedule a fixed appointment time (30 minutes from now)"""
        start_time = datetime.now() + timedelta(minutes=30)
        end_time = start_time + timedelta(minutes=30)

        event = {
            'summary': f"Appointment with {self.patient_name}",
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': [
                {'email': self.patient_email},
            ]
        }

        event = self.calendar_service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        return event.get('htmlLink')

    async def process_voice_input(self, text: str) -> str:
        """Process voice input based on conversation state"""
        if self.state == ConversationState.GREETING:
            if "appointment" in text.lower():
                self.state = ConversationState.GET_NAME
                return f"Sure! May I have your name, please?"
            return f"Hello! You've reached Dr. {self.doctor_name}'s virtual assistant. How can I help you today?"

        elif self.state == ConversationState.GET_NAME:
            self.patient_name = text
            self.state = ConversationState.GET_EMAIL
            return f"Thank you, {text}. Could you please provide your email address?"

        elif self.state == ConversationState.GET_EMAIL:
            self.patient_email = text.lower().replace(" at ", "@").replace(" dot ", ".")
            self.state = ConversationState.CONFIRM
            return f"I'll schedule an appointment for you in 30 minutes. Please say 'yes' to confirm."

        elif self.state == ConversationState.CONFIRM:
            if "yes" in text.lower():
                calendar_link = self._schedule_appointment()
                self.state = ConversationState.COMPLETE
                return f"Perfect! Your appointment has been scheduled. You'll receive an email with the details. Have a great day!"
            return "Would you like to try again?"

        elif self.state == ConversationState.COMPLETE:
            return "Thank you for using our scheduling service. Goodbye!"

    async def send(self):
        """Override send to process voice input"""
        async for text in self._iter():
            logger.debug('send')
            response_text = await self.process_voice_input(text)
            await self.session.send(input=response_text, end_of_turn=True)
            logger.debug('sent')
            yield text

# Usage example
async def main():
    scheduler = AppointmentScheduler("Smith")
    await scheduler.run()

if __name__ == "__main__":
    asyncio.run(main())