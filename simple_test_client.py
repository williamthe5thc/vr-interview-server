#!/usr/bin/env python
"""
Simplified Socket.IO test client for VR Interview Server
"""

import socketio
import time
import argparse
import os
import base64
import wave
import numpy as np

# Create a Socket.IO client
sio = socketio.Client(logger=True)

# Global variables
session_id = None
current_state = "disconnected"

# Event handlers
@sio.event
def connect():
    print("Connected to server!")
    global current_state
    current_state = "connected"

@sio.event
def disconnect():
    print("Disconnected from server!")
    global current_state
    current_state = "disconnected"

@sio.on('session_created')
def on_session_created(data):
    global session_id
    session_id = data['session_id']
    print(f"Session created: {session_id}")
    
    # Join the session
    sio.emit('join_session', {'session_id': session_id})
    print("Joining session...")

@sio.on('session_configured')
def on_session_configured(data):
    print(f"Session configured!")

@sio.on('state_update')
def on_state_update(data):
    global current_state
    current_state = data['state']
    turn = data['turn']
    print(f"State updated: {current_state}, Turn: {turn}")

@sio.on('listening_started')
def on_listening_started(data):
    print("Server is listening for audio...")
    
    # Send test audio file
    send_test_audio()

@sio.on('processing_started')
def on_processing_started(data):
    print("Server is processing audio...")

@sio.on('response_ready')
def on_response_ready(data):
    response_text = data['text']
    audio_url = data['audio_url']
    print(f"\nInterviewer response: {response_text}")
    print(f"Audio URL: {audio_url}")
    
    print("\nPress Enter to continue the conversation...")

@sio.on('error')
def on_error(data):
    print(f"Error from server: {data['message']}")

def configure_session():
    """Configure the interview session."""
    if not session_id:
        print("No session ID available")
        return
    
    config_data = {
        'session_id': session_id,
        'config': {
            'position': 'Software Engineer',
            'interviewer_type': 'professional',
            'difficulty': 0.5
        }
    }
    
    sio.emit('configure_session', config_data)
    print("Configuring session...")

def start_speaking():
    """Start the speaking process."""
    if not session_id or current_state not in ["idle", "waiting"]:
        print(f"Cannot start speaking in state: {current_state}")
        return False
    
    sio.emit('start_speaking', {'session_id': session_id})
    print("Starting to speak...")
    return True

def stop_speaking():
    """Stop the speaking process."""
    if not session_id or current_state != "listening":
        print(f"Cannot stop speaking in state: {current_state}")
        return False
    
    sio.emit('stop_speaking', {'session_id': session_id})
    print("Stopping speaking...")
    return True

def send_test_audio(file_path="test_audio/speech_sample_1.wav"):
    """Send a test audio file to the server."""
    if not os.path.exists(file_path):
        print(f"Test audio file not found: {file_path}")
        stop_speaking()
        return
    
    print(f"Sending test audio: {file_path}")
    
    try:
        # Read the audio file
        with wave.open(file_path, 'rb') as wf:
            audio_data = wf.readframes(wf.getnframes())
        
        # Send the entire audio in one chunk
        base64_audio = base64.b64encode(audio_data).decode('utf-8')
        
        sio.emit('audio_data', {
            'session_id': session_id,
            'audio': base64_audio
        })
        
        print(f"Audio data sent ({len(audio_data)} bytes)")
        time.sleep(1)  # Give the server time to process
        
        # Stop speaking
        stop_speaking()
        
    except Exception as e:
        print(f"Error sending audio: {e}")
        stop_speaking()

def main():
    parser = argparse.ArgumentParser(description='Simple VR Interview Test Client')
    parser.add_argument('--url', default='http://localhost:8081', help='Socket.IO server URL')
    parser.add_argument('--sample', default='1', help='Sample number (1-5)')
    args = parser.parse_args()
    
    # Determine the audio sample to use
    sample_num = int(args.sample)
    if sample_num < 1 or sample_num > 5:
        sample_num = 1
    sample_file = f"test_audio/speech_sample_{sample_num}.wav"
    
    print(f"Using server URL: {args.url}")
    print(f"Using audio sample: {sample_file}")
    
    # Connect to the server
    try:
        sio.connect(args.url)
        print("Waiting for server to create session...")
        
        # Wait for session creation and state update
        while current_state == "connected":
            time.sleep(0.5)
        
        # Configure the session once we have a session ID
        if session_id:
            configure_session()
            
            # Main interaction loop
            while sio.connected:
                user_input = input("\nPress Enter to speak, or 'q' to quit: ")
                
                if user_input.lower() == 'q':
                    break
                    
                if user_input.isdigit() and 1 <= int(user_input) <= 5:
                    # Use the specified sample
                    sample_file = f"test_audio/speech_sample_{user_input}.wav"
                    print(f"Using sample {user_input}")
                
                # Start speaking
                if start_speaking():
                    # The audio will be sent when listening_started event is received
                    pass
                
                time.sleep(0.5)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    main()