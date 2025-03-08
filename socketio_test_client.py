#!/usr/bin/env python
"""
Test client for VR Interview Server using Socket.IO protocol.
Simulates the Unity client to test server functionality.
"""

import asyncio
import socketio
import time
import base64
import os
import wave
import argparse
from pydub import AudioSegment
from pydub.playback import play

class InterviewTestClient:
    def __init__(self, server_url="http://localhost:8081"):
        self.server_url = server_url
        self.session_id = None
        self.current_state = "disconnected"
        self.audio_chunk_size = 1024 * 4  # 4KB chunks
        
        # Create Socket.IO client
        self.sio = socketio.Client()
        
        # Register event handlers
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('session_created', self.on_session_created)
        self.sio.on('session_configured', self.on_session_configured)
        self.sio.on('state_update', self.on_state_update)
        self.sio.on('listening_started', self.on_listening_started)
        self.sio.on('processing_started', self.on_processing_started)
        self.sio.on('response_ready', self.on_response_ready)
        self.sio.on('error', self.on_error)
        
        # Create test audio directory if it doesn't exist
        os.makedirs("test_audio", exist_ok=True)
    
    def connect(self):
        """Connect to the Socket.IO server."""
        print(f"Connecting to {self.server_url}...")
        try:
            self.sio.connect(self.server_url)
            print("Connected successfully!")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the Socket.IO server."""
        if self.sio.connected:
            self.sio.disconnect()
            print("Disconnected from server")
    
    # Event handlers
    def on_connect(self):
        print("Socket.IO connected!")
        self.current_state = "connected"
    
    def on_disconnect(self):
        print("Socket.IO disconnected!")
        self.current_state = "disconnected"
    
    def on_session_created(self, data):
        self.session_id = data['session_id']
        print(f"Session created: {self.session_id}")
        self.join_session()
    
    def on_session_configured(self, data):
        print(f"Session configured: {data['session_id']}")
    
    def on_state_update(self, data):
        new_state = data['state']
        turn = data['turn']
        self.current_state = new_state
        print(f"State updated: {new_state}, Turn: {turn}")
    
    def on_listening_started(self, data):
        print("Listening started - simulating speech...")
        # Start sending test audio
        self.send_test_audio()
    
    def on_processing_started(self, data):
        print("Server is processing your speech...")
    
    def on_response_ready(self, data):
        response_text = data['text']
        audio_url = data['audio_url']
        print(f"Response: {response_text}")
        print(f"Audio URL: {audio_url}")
        
        # Download and play the audio response
        response_path = f"test_audio/response_{int(time.time())}.wav"
        try:
            self.download_audio(audio_url, response_path)
            print("Playing audio response...")
            audio = AudioSegment.from_wav(response_path)
            play(audio)
        except Exception as e:
            print(f"Error playing audio: {e}")
        
        print("\nReady for next turn. Press Enter to continue speaking...")
    
    def on_error(self, data):
        print(f"Error from server: {data['message']}")
    
    # Client actions
    def join_session(self):
        """Join the created session."""
        if not self.session_id:
            print("No session ID available")
            return
        
        self.sio.emit('join_session', {'session_id': self.session_id})
        print(f"Joined session: {self.session_id}")
        
        # Configure the session
        self.configure_session()
    
    def configure_session(self):
        """Configure the interview session."""
        if not self.session_id:
            print("No session ID available")
            return
        
        config_data = {
            'session_id': self.session_id,
            'config': {
                'position': 'Software Engineer',
                'interviewer_type': 'professional',
                'difficulty': 0.5
            }
        }
        
        self.sio.emit('configure_session', config_data)
        print("Session configuration sent")
    
    def start_speaking(self):
        """Simulate the user starting to speak."""
        if not self.sio.connected or not self.session_id:
            print("Not connected or no session")
            return
        
        if self.current_state not in ["idle", "waiting"]:
            print(f"Cannot start speaking in {self.current_state} state")
            return
        
        self.sio.emit('start_speaking', {'session_id': self.session_id})
        print("Start speaking command sent")
    
    def stop_speaking(self):
        """Simulate the user stopping speaking."""
        if not self.sio.connected or not self.session_id:
            print("Not connected or no session")
            return
        
        if self.current_state != "listening":
            print(f"Cannot stop speaking in {self.current_state} state")
            return
        
        self.sio.emit('stop_speaking', {'session_id': self.session_id})
        print("Stop speaking command sent")
    
    def send_test_audio(self, audio_file=None):
        """Send a test audio file to the server."""
        # Use default test file if none provided
        if audio_file is None:
            audio_file = "test_audio/test_sample.wav"
            
            # Create a test audio file if it doesn't exist
            if not os.path.exists(audio_file):
                self.create_test_audio_file(audio_file)
        
        print(f"Sending test audio: {audio_file}")
        
        try:
            # Read the audio file
            with wave.open(audio_file, 'rb') as wf:
                audio_data = wf.readframes(wf.getnframes())
            
            # Send audio in chunks
            chunk_size = self.audio_chunk_size
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i+chunk_size]
                base64_chunk = base64.b64encode(chunk).decode('utf-8')
                
                self.sio.emit('audio_data', {
                    'session_id': self.session_id,
                    'audio': base64_chunk
                })
                
                # Small delay between chunks to simulate streaming
                time.sleep(0.1)
            
            # Stop speaking after sending all audio
            self.stop_speaking()
            
        except Exception as e:
            print(f"Error sending audio: {e}")
    
    def create_test_audio_file(self, file_path):
        """Create a simple test audio file."""
        print("Creating test audio file...")
        
        # Parameters for the audio file
        sample_rate = 44100
        duration = 3  # seconds
        
        # Create a PyAudio instance
        import pyaudio
        p = pyaudio.PyAudio()
        
        # Create a test WAV file
        wf = wave.open(file_path, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        
        # Generate simple beep sound
        import numpy as np
        frequency = 440  # A4 note
        samples = (np.sin(2 * np.pi * np.arange(sample_rate * duration) * frequency / sample_rate) * 32767).astype(np.int16)
        wf.writeframes(samples.tobytes())
        
        wf.close()
        p.terminate()
        
        print(f"Test audio file created: {file_path}")
    
    def create_test_speech_file(self, file_path="test_audio/test_speech.wav"):
        """Create a test audio file with speech."""
        print("Creating test speech file...")
        try:
            from gtts import gTTS
            
            # Create a speech file
            tts = gTTS("Hello, I'm interested in the software engineering position. Could you tell me more about the role?", lang='en')
            tts.save(file_path)
            print(f"Test speech file created: {file_path}")
            return file_path
        except Exception as e:
            print(f"Error creating speech file: {e}")
            return None
    
    def download_audio(self, audio_url, output_path):
        """Download audio response from the server."""
        import requests
        
        # Construct full URL
        base_url = self.server_url
        # Remove 'socket.io' from URL if present
        base_url = base_url.replace('/socket.io', '')
        full_url = f"{base_url}{audio_url}"
        
        try:
            response = requests.get(full_url)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                print(f"Audio downloaded to: {output_path}")
                return True
            else:
                print(f"Download failed with status: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error downloading audio: {e}")
            return False
    
    def reset_session(self):
        """Reset the current session."""
        if not self.sio.connected or not self.session_id:
            print("Not connected or no session")
            return
        
        self.sio.emit('reset_session', {'session_id': self.session_id})
        print("Session reset command sent")
    
    def interactive_session(self):
        """Run an interactive test session."""
        if not self.connect():
            return
        
        try:
            print("\n=== VR Interview Test Client ===")
            print("Connected to server. Waiting for session creation...")
            
            # Keep the client running
            while self.sio.connected:
                user_input = input("\nPress Enter to start speaking, or 'q' to quit: ")
                
                if user_input.lower() == 'q':
                    break
                
                # Use a speech file instead of tone
                speech_file = self.create_test_speech_file()
                
                if self.current_state in ["idle", "waiting"]:
                    self.start_speaking()
                    # Audio will be sent automatically in the listening_started event handler
                
            print("Interactive session ended")
            
        except KeyboardInterrupt:
            print("\nSession interrupted by user")
        except Exception as e:
            print(f"Error in interactive session: {e}")
        finally:
            self.disconnect()

def main():
    parser = argparse.ArgumentParser(description='VR Interview Test Client')
    parser.add_argument('--url', default='http://localhost:8081', help='Socket.IO server URL')
    args = parser.parse_args()
    
    client = InterviewTestClient(server_url=args.url)
    client.interactive_session()

if __name__ == "__main__":
    try:
        # Required packages for this script
        import socketio
        import pyaudio
        import requests
        import numpy as np
        from pydub import AudioSegment
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Please install required packages with:")
        print("pip install python-socketio pyaudio requests numpy pydub")
        exit(1)
    
    main()