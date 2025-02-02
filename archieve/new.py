import os
os.environ['GOOGLE_API_KEY'] = 'AIzaSyC5_Vo3Qg5gFuoH0mhwdILCSJmFDK7jHYA'


from google import genai
client = genai.Client()
MODEL = "gemini-2.0-flash-exp"

import sounddevice as sd
import numpy as np
import asyncio
import websockets
import json

SAMPLE_RATE = 16000  # Gemini API's expected sample rate

async def record_audio(duration=5):
    print("Recording...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()
    print("Recording complete.")
    return audio.flatten()

async def send_audio_to_gemini(audio_data):
    uri = f"wss://genai.googleapis.com/v1alpha/{MODEL}:streamingPredict"
    async with websockets.connect(uri) as websocket:
        # Send initial configuration
        config = {
            "config": {
                "encoding": "LINEAR16",
                "sample_rate_hertz": SAMPLE_RATE,
                "language_code": "en-US",
                "audio_channel_count": 1
            }
        }
        await websocket.send(json.dumps(config))

        # Stream audio data
        await websocket.send(audio_data.tobytes())

        # Indicate end of input
        await websocket.send("")

        # Receive and process responses
        async for message in websocket:
            response = json.loads(message)
            if 'results' in response:
                print("Transcription:", response['results'][0]['alternatives'][0]['transcript'])
            if 'audio' in response:
                # Process the audio response as needed
                pass


async def main():
    while True:
        audio_data = await record_audio()
        await send_audio_to_gemini(audio_data)

if __name__ == "__main__":
    asyncio.run(main())
