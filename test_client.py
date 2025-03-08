#!/usr/bin/env python
"""
Test client for VR Interview Server.
Simulates the Unity client to test server functionality.
"""

import asyncio
import json
import websockets
import time
import base64
import os
import wave
import pyaudio
import argparse
from pydub import AudioSegment
from pydub.playback import play

class InterviewTestClient:
    def __init__(self, server_url="ws://localhost:8081"):
        self.server_url = server_url
        self.session_id = None
        self.websocket = None
        self.current_state = "disconnected"
        self.audio_chunk_size = 1024 * 4  # 4KB chunks
        
        # Create test audio directory if it doesn't exist
        os.makedirs("test_audio", exist_ok=True)
    
    async def connect(self):
        """Connect to the WebSocket server."""
        print(f"Connecting to {self.server_url}...")
        try:
            self.websocket = await websockets.connect(self.server_url)
            print("Connected successfully!")
            self.current_state = "connected"
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.current_state = "disconnected"
            print("Disconnected from server")
    
    async def receive_messages(self):
        """Listen for messages from the server."""
        while self.websocket:
            try:
                message = await self.websocket.recv()
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed")
                self.current_state = "disconnected"
                break
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
    
    async def handle_message(self, message):
        """Process messages from the server."""
        try:
            data = json.loads(message)
            
            # Pretty print the message
            print("\n=== Message Received ===")
            print(json.dumps(data, indent=2))
            print("========================\n")
            
            # Handle different message types
            if "session_created" in data:
                self.session_id = data["session_created"]["session_id"]
                print(f"Session created: {self.session_id}")
                await self.join_session()
                
            elif "state_update" in data:
                new_state = data["state_update"]["state"]
                turn = data["state_update"]["turn"]
                self.current_state = new_state
                print(f"State updated: {new_state}, Turn: {turn}")
                
            elif "listening_started" in data:
                print("Listening started - simulating speech...")
                # Wait a bit, then send the audio file
                await asyncio.sleep(1)
                await self.send_test_audio()
                
            elif "response_ready" in data:
                response_text = data["response_ready"]["text"]
                audio_url = data["response_ready"]["audio_url"]
                print(f"Response: {response_text}")
                print(f"Audio URL: {audio_url}")
                
                # Download and play the audio response
                response_path = f"test_audio/response_{int(time.time())}.wav"
                await self.download_audio(audio_url, response_path)
                
                print("Playing audio response...")
                try:
                    audio = AudioSegment.from_wav(response_path)
                    play(audio)
                except Exception as e:
                    print(f"Error playing audio: {e}")
                    
                # Once the audio is done, wait a bit then start speaking again
                await asyncio.sleep(3)
                if self.current_state == "waiting":
                    print("\nReady for next turn. Press Enter to continue speaking...")
                
        except Exception as e:
            print(f"Error handling message: {e}")
    
    async def join_session(self):
        """Join the created session."""
        if not self.session_id:
            print("No session ID available")
            return
        
        message = {
            "join_session": {
                "session_id": self.session_id
            }
        }
        await self.websocket.send(json.dumps(message))
        print(f"Joined session: {self.session_id}")
        
        # Configure the session
        await self.configure_session()
    
    async def configure_session(self):
        """Configure the interview session."""
        if not self.session_id:
            print("No session ID available")
            return
        
        message = {
            "configure_session": {
                "session_id": self.session_id,
                "config": {
                    "position": "Software Engineer",
                    "interviewer_type": "professional",
                    "difficulty": 0.5
                }
            }
        }
        await self.websocket.send(json.dumps(message))
        print("Session configured")
    
    async def start_speaking(self):
        """Simulate the user starting to speak."""
        if not self.websocket or not self.session_id:
            print("Not connected or no session")
            return
        
        if self.current_state not in ["idle", "waiting"]:
            print(f"Cannot start speaking in {self.current_state} state")
            return
        
        message = {
            "start_speaking": {
                "session_id": self.session_id
            }
        }
        await self.websocket.send(json.dumps(message))
        print("Start speaking command sent")
    
    async def stop_speaking(self):
        """Simulate the user stopping speaking."""
        if not self.websocket or not self.session_id:
            print("Not connected or no session")
            return
        
        if self.current_state != "listening":
            print(f"Cannot stop speaking in {self.current_state} state")
            return
        
        message = {
            "stop_speaking": {
                "session_id": self.session_id
            }
        }
        await self.websocket.send(json.dumps(message))
        print("Stop speaking command sent")
    
    async def send_test_audio(self, audio_file=None):
        """Send a test audio file to the server."""
        # Use default test file if none provided
        if audio_file is None:
            audio_file = "test_audio/test_sample.wav"
            
            # Create a test audio file if it doesn't exist
            if not os.path.exists(audio_file):
                await self.create_test_audio_file(audio_file)
        
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
                
                message = {
                    "audio_data": {
                        "session_id": self.session_id,
                        "audio": base64_chunk
                    }
                }
                await self.websocket.send(json.dumps(message))
                
                # Small delay between chunks to simulate streaming
                await asyncio.sleep(0.1)
            
            # Stop speaking after sending all audio
            await self.stop_speaking()
            
        except Exception as e:
            print(f"Error sending audio: {e}")
    
    async def create_test_audio_file(self, file_path):
        """Create a simple test audio file."""
        print("Creating test audio file...")
        
        # Parameters for the audio file
        sample_rate = 44100
        duration = 3  # seconds
        
        # Create a PyAudio instance
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
    
    async def download_audio(self, audio_url, output_path):
        """Download audio response from the server."""
        import aiohttp
        
        # Construct full URL
        base_url = self.server_url.replace("ws://", "http://")
        full_url = f"{base_url}{audio_url}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url) as response:
                    if response.status == 200:
                        with open(output_path, 'wb') as f:
                            f.write(await response.read())
                        print(f"Audio downloaded to: {output_path}")
                        return True
                    else:
                        print(f"Download failed with status: {response.status}")
                        return False
        except Exception as e:
            print(f"Error downloading audio: {e}")
            return False
    
    async def reset_session(self):
        """Reset the current session."""
        if not self.websocket or not self.session_id:
            print("Not connected or no session")
            return
        
        message = {
            "reset_session": {
                "session_id": self.session_id
            }
        }
        await self.websocket.send(json.dumps(message))
        print("Session reset command sent")
    
    async def interactive_session(self):
        """Run an interactive test session."""
        if not await self.connect():
            return
        
        # Start message receiver in background
        receiver_task = asyncio.create_task(self.receive_messages())
        
        try:
            print("\n=== VR Interview Test Client ===")
            print("Connected to server. Waiting for session creation...")
            
            # Wait for initial setup
            while not self.session_id or self.current_state not in ["idle", "waiting"]:
                await asyncio.sleep(0.5)
            
            # Interactive loop
            while self.websocket and self.current_state != "disconnected":
                if self.current_state in ["idle", "waiting"]:
                    user_input = input("\nPress Enter to start speaking, or 'q' to quit: ")
                    
                    if user_input.lower() == 'q':
                        break
                    
                    await self.start_speaking()
                
                elif self.current_state == "processing" or self.current_state == "responding":
                    print("Waiting for interviewer response...")
                    await asyncio.sleep(1)
                
                else:
                    await asyncio.sleep(0.5)
            
            print("Interactive session ended")
            
        except KeyboardInterrupt:
            print("\nSession interrupted by user")
        except Exception as e:
            print(f"Error in interactive session: {e}")
        finally:
            # Cancel receiver task
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
            
            await self.disconnect()

async def main():
    parser = argparse.ArgumentParser(description='VR Interview Test Client')
    parser.add_argument('--url', default='ws://localhost:8081', help='WebSocket server URL')
    args = parser.parse_args()
    
    client = InterviewTestClient(server_url=args.url)
    await client.interactive_session()

if __name__ == "__main__":
    try:
        # Required packages for this script
        import websockets
        import pyaudio
        import aiohttp
        from pydub import AudioSegment
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Please install required packages with:")
        print("pip install websockets pyaudio aiohttp pydub")
        exit(1)
    
    asyncio.run(main())