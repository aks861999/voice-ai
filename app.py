import signal
import sys
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from google.generativeai import GenerativeModel
import google.generativeai as genai
from flask import Flask, request
from google.auth.transport.requests import Request
import os
import tempfile
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from gtts import gTTS
from pyngrok import ngrok
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID_akash.bsws') 
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN_akash.bsws')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
YOUR_TWILIO_NUMBER = os.getenv('YOUR_TWILIO_NUMBER_akash.bsws')
YOUR_PERSONAL_NUMBER = os.getenv('YOUR_PERSONAL_NUMBER_akash.bsws')

NGROK_AUTH_TOKEN = os.getenv('NGROK_AUTH_TOKEN')
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')

# Store ngrok URL globally
NGROK_URL = None

# Initialize Twilio Client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Initialize Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def init_ngrok():
    print("Initializing ngrok tunnel...")
    """Initialize ngrok tunnel"""
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    tunnel = ngrok.connect(5000)
    return tunnel.public_url

def cleanup(signum, frame):
    print("\nCleaning up resources...")
    """Cleanup resources on termination"""
    ngrok.disconnect(NGROK_URL)
    ngrok.kill()
    sys.exit(0)

def upload_to_drive(file_path, file_name, folder_id= GOOGLE_DRIVE_FOLDER_ID ):
    print("\nUploading file to Google Drive...")
    """Upload a file to Google Drive and return its public URL"""
    creds = service_account.Credentials.from_service_account_file(
        'secret/decoded-effect-447116-t7-d72a98f5362d.json', 
        scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {'name': file_name}
    if folder_id:
        file_metadata['parents'] = [folder_id]
    
    media = MediaFileUpload(file_path, mimetype='audio/mpeg')
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    file_id = file.get('id')
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return f"https://drive.google.com/uc?id={file_id}&export=download"

def text_to_speech_and_upload(text):
    print("\nConverting text to speech and uploading to Google Drive...")
    """Convert text to speech using gTTS and upload to Google Drive"""
    tts = gTTS(text=text, lang='en')
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
        tts.save(temp_file.name)
        temp_path = temp_file.name
    file_name = f"response_{os.urandom(4).hex()}.mp3"
    public_url = upload_to_drive(temp_path, file_name)
    os.unlink(temp_path)
    return public_url

def get_calendar_service():
    """Authenticate and return the Google Calendar API service."""
    creds = None
    if os.path.exists('secret/token.json'):
        creds = Credentials.from_authorized_user_file('secret/token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('secret/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('secret/token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def create_appointment(patient_name):
    print("\nCreating appointment...")
    """Create a 30-minute appointment starting now."""
    service = get_calendar_service()
    print(f"I got the service as {service}")
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=30)

    event = {
        'summary': f'Appointment with {patient_name}',
        'description': f'30-minute appointment with {patient_name}',
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [{'method': 'popup', 'minutes': 10}],
        },
    }

    try:
        event = service.events().insert(calendarId='primary', body=event).execute()
        print("it worked\n")
        return event.get('htmlLink')
    except Exception as error:
        print(f"An error occurred: {error}")
        return None

@app.route("/welcome", methods=['POST'])
def welcome():
    print("\nHandling welcome request...")
    """Welcome message and prompt for name"""
    response = VoiceResponse()
    response.say("Hi, I am Sarah from XYZ Salon. To book an appointment, please tell me your name.")
    response.gather(
        input='speech',
        action='/handle_user_name',
        method='POST',
        timeout=5,
        speechTimeout='auto'
    )
    return str(response)

@app.route("/handle_user_name", methods=['POST'])
def handle_user_name():
    print("\nHandling user name...")
    """Handle user's name input"""
    user_message = request.values.get('SpeechResult', '')
    print(f"User's message is : {user_message}")
    if not user_message:
        response = VoiceResponse()
        response.say("I didn't catch that. Could you please repeat your name?")
        gather = response.gather(
            input='speech',
            action='/handle_user_name',
            method='POST',
            timeout=5,
            speechTimeout='auto'
        )
        return str(response)
    
    gemini_prompt = f"Extract the name from this text:\n{user_message}\nProvide the output as: Name: <Name>"
    ai_response = model.generate_content(gemini_prompt).text
    name = None
    for line in ai_response.split('\n'):
        if line.startswith("Name:"):
            name = line.split("Name:")[1].strip()
    print(f"Extracted name is ....: {name}")
    if not name:
        response = VoiceResponse()
        response.say("Sorry, I couldn't understand your name. Could you repeat it?")
        gather = response.gather(
            input='speech',
            action='/handle_user_name',
            method='POST',
            timeout=5,
            speechTimeout='auto'
        )
        return str(response)
    
    event_link = create_appointment(name)
    response = VoiceResponse()
    response.say(f"Thank you, {name}. Your appointment is booked. You can check the details in your Google Calendar.")
    return str(response)

def make_outbound_call():
    print("\nInitiating outbound call...")
    """Initiate an outbound call"""
    if not NGROK_URL:
        raise ValueError("ngrok URL not initialized")
    webhook_url = f"{NGROK_URL}/welcome"
    call = twilio_client.calls.create(
        url=webhook_url,
        to=YOUR_PERSONAL_NUMBER,
        from_=YOUR_TWILIO_NUMBER
    )
    return call.sid

if __name__ == "__main__":
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    NGROK_URL = init_ngrok()
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    try:
        call_sid = make_outbound_call()
        print(f"Initiated call with SID: {call_sid}")
    except Exception as e:
        print(f"Failed to initiate call: {e}")
    app.run(port=5000)