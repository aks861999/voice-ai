from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from google.generativeai import GenerativeModel
import google.generativeai as genai
from flask import Flask, request
import os
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from gtts import gTTS
from pyngrok import ngrok

app = Flask(__name__)
# Your configurations
TWILIO_ACCOUNT_SID = '<TWILIO_ACCOUNT_SID>'
TWILIO_AUTH_TOKEN = '<TWILIO_AUTH_TOKEN>'
GOOGLE_API_KEY = '<Gemini_API_KEY>'
YOUR_TWILIO_NUMBER = '<YOUR_TWILIO_NUMBER>'
YOUR_PERSONAL_NUMBER = '<YOUR_PERSONAL_NUMBER>'

# Store ngrok URL globally
NGROK_URL = None

# Initialize clients
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# Initialize Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
# Gemini API setup




def init_ngrok():
    """Initialize ngrok tunnel"""
    ngrok.set_auth_token("<ngrok_auth_token>")
    print("i have set the auth token")
    tunnel = ngrok.connect(5000)
    print("i have connected to the tunnel")
    return tunnel.public_url







def upload_to_drive(file_path, file_name, folder_id='14OEkthNg46yrcK_sHQMdkU1RDKS5SZW4'):
    """Upload file to Google Drive and return public URL"""
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

def get_ai_response(user_input):
    """Get response from Gemini AI"""

    user_input = "please give answer in *one sentence*, possible in *few words*, to the following question,  " + user_input 
    response = model.generate_content(user_input)
    print(response.text)
    return response.text

def text_to_speech_and_upload(text):
    """Convert text to speech using gTTS and upload to Google Drive"""
    # Generate audio using gTTS
    tts = gTTS(text=text, lang='en')
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
        tts.save(temp_file.name)
        temp_path = temp_file.name
    
    # Upload to Google Drive
    file_name = f"response_{os.urandom(4).hex()}.mp3"
    public_url = upload_to_drive(temp_path, file_name)
    
    # Clean up temp file
    os.unlink(temp_path)
    
    return public_url

@app.route("/welcome", methods=['POST'])
def welcome():
    """Initial welcome message and prompt for user input"""
    response = VoiceResponse()
    response.say("Hi I am an AI assistant made by Akash. How can I help you today?")
    
    # Add gather for speech input
    gather = response.gather(
        input='speech',
        action='/handle_response',
        method='POST',
        timeout=3,
        speechTimeout='auto'
    )
    
    return str(response)

@app.route("/handle_response", methods=['POST'])
def handle_response():
    """Handle the user's speech input and return TwiML"""
    # Get speech input from Twilio
    user_message = request.values.get('SpeechResult', '')
    
    if not user_message:
        # If no speech detected, prompt again
        response = VoiceResponse()
        response.say("I didn't catch that. Could you please repeat?")
        gather = response.gather(
            input='speech',
            action='/handle_response',
            method='POST',
            timeout=3,
            speechTimeout='auto'
        )
        return str(response)
    
    # Get AI response
    ai_text = get_ai_response(user_message)
    
    # Convert to speech and upload
    audio_url = text_to_speech_and_upload(ai_text)
    
    # Create TwiML response
    response = VoiceResponse()
    response.play(audio_url)
    
    # Add gather for next input
    gather = response.gather(
        input='speech',
        action='/handle_response',
        method='POST',
        timeout=3,
        speechTimeout='auto'
    )
    
    return str(response)

def make_outbound_call():
    """Initiate an outbound call to your number using dynamic ngrok URL"""
    if not NGROK_URL:
        raise ValueError("ngrok URL not initialized")
        
    webhook_url = f"{NGROK_URL}/welcome"  # Changed to welcome endpoint
    call = twilio_client.calls.create(
        url=webhook_url,
        to=YOUR_PERSONAL_NUMBER,
        from_=YOUR_TWILIO_NUMBER
    )
    return call.sid

if __name__ == "__main__":
    # Initialize ngrok first
    NGROK_URL = init_ngrok()
    print(f" * ngrok tunnel \"{NGROK_URL}\" -> \"http://127.0.0.1:5000\"")
    
    # Make the initial call
    try:
        call_sid = make_outbound_call()
        print(f" * Initiated call with SID: {call_sid}")
    except Exception as e:
        print(f" * Failed to initiate call: {str(e)}")
    
    # Start Flask app without debug mode to prevent reloading
    app.run(port=5000)