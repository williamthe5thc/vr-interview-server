#!/usr/bin/env python
"""
Improved Socket.IO test client for VR Interview Server (v4)
"""

import socketio
import time
import argparse
import os
import base64
import wave
import numpy as np
from threading import Event, Lock

# Create Socket.IO client
sio = socketio.Client(logger=False)

# Global variables
session_id = None
current_state = "disconnected"
current_sample = 1
state_lock = Lock()
audio_sent_event = Event()
stop_speaking_sent_event = Event()

# Event handlers
@sio.event
def connect():
    print("Connected to server!")
    global current_state
    with state_lock:
        current_state = "connected"

@sio.event
def connect_error(data):
    print(f"Connection error: {data}")

@sio.event
def disconnect():
    print("Disconnected from server!")
    global current_state
    with state_lock:
        current_state = "disconnected"

@sio.on('session_created')
def on_session_created(data):
    global session_id
    session_id = data['session_id']
    print(f"Session created: {session_id}")
    
    # Join the session
    join_session()

@sio.on('session_configured')
def on_session_configured(data):
    print(f"Session configured!")

@sio.on('state_update')
def on_state_update(data):
    global current_state
    state = data['state']
    turn = data.get('turn', 0)
    print(f"State updated: {state}, Turn: {turn}")
    
    with state_lock:
        current_state = state

@sio.on('listening_started')
def on_listening_started(data):
    print("Server is listening for audio...")
    # Reset the events
    audio_sent_event.clear()
    stop_speaking_sent_event.clear()
    
    # Send test audio file
    send_test_audio()

@sio.on('processing_started')
def on_processing_started(data):
    print("Server is processing audio...")

@sio.on('response_ready')
def on_response_ready(data):
    response_text = data['text']
    audio_url = data.get('audio_url', '')
    print(f"\nInterviewer response: {response_text}")
    print(f"Audio URL: {audio_url}")
    
    print("\nPress Enter to continue the conversation...")

@sio.on('error')
def on_error(data):
    print(f"Error from server: {data['message']}")

def join_session():
    """Join the created session."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return
    
    try:
        print(f"Joining session: {session_id}")
        sio.emit('join_session', {'session_id': session_id})
        time.sleep(1)  # Give server time to process
        
        # Configure the session
        configure_session()
    except Exception as e:
        print(f"Error joining session: {e}")

def configure_session():
    """Configure the interview session."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return
    
    try:
        print("Configuring session...")
        config_data = {
            'session_id': session_id,
            'config': {
                'position': 'Software Engineer',
                'interviewer_type': 'professional',
                'difficulty': 0.5
            }
        }
        
        sio.emit('configure_session', config_data)
    except Exception as e:
        print(f"Error configuring session: {e}")

def get_current_state():
    """Get the current state with thread safety."""
    with state_lock:
        return current_state

def start_speaking():
    """Start the speaking process."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return False
    
    state = get_current_state()
    if state not in ["idle", "waiting"]:
        print(f"Cannot start speaking in state: {state}")
        return False
    
    try:
        print("Starting to speak...")
        # Reset the events
        audio_sent_event.clear()
        stop_speaking_sent_event.clear()
        
        sio.emit('start_speaking', {'session_id': session_id})
        
        # Wait briefly to give the server time to respond
        time.sleep(1)
        return True
    except Exception as e:
        print(f"Error starting to speak: {e}")
        return False

def stop_speaking():
    """Stop the speaking process."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return False
    
    # Don't check state here - just try to stop speaking regardless
    # This is more robust against race conditions
    
    try:
        print("Stopping speaking...")
        sio.emit('stop_speaking', {'session_id': session_id})
        stop_speaking_sent_event.set()  # Signal that we've sent the stop command
        return True
    except Exception as e:
        print(f"Error stopping speaking: {e}")
        return False

def send_test_audio(file_path=None):
    """Send a test audio file to the server."""
    print("Starting the send test audio...")
    global session_id, current_sample
    
    if file_path is None:
        file_path = f"test_audio/speech_sample_{current_sample}.wav"
    
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
        
        print(f"Sending audio data ({len(audio_data)} bytes)...")
        sio.emit('audio_data', {
            'session_id': session_id,
            'audio': base64_audio
        })
        
        print("Audio data sent, waiting briefly...")
        audio_sent_event.set()  # Signal that audio has been sent
        
        # Wait a moment to ensure the server processes the audio
        time.sleep(1)
        
        # Always stop speaking after sending audio - don't check state
        print("Forcibly stopping speaking after audio send...")
        stop_speaking()
        
        # Wait for server to process
        time.sleep(2)
        
    except Exception as e:
        print(f"Error sending audio: {e}")
        # Try to stop speaking even on error
        stop_speaking()

def show_audio_samples():
    """Show available audio samples."""
    samples = []
    for i in range(1, 6):
        file_path = f"test_audio/speech_sample_{i}.wav"
        if os.path.exists(file_path):
            samples.append(i)
    
    print("\nAvailable speech samples:")
    if samples:
        for i in samples:
            try:
                with wave.open(f"test_audio/speech_sample_{i}.wav", 'rb') as wf:
                    duration = wf.getnframes() / wf.getframerate()
                print(f"  {i}. Speech sample {i} ({duration:.1f} seconds)")
            except:
                print(f"  {i}. Speech sample {i}")
    else:
        print("  No speech samples found. Run create_speech_sample.py first.")

def main():
    parser = argparse.ArgumentParser(description='Improved VR Interview Test Client')
    parser.add_argument('--url', default='http://localhost:8081', help='Socket.IO server URL')
    parser.add_argument('--sample', default='1', help='Sample number (1-5)')
    args = parser.parse_args()
    
    global current_sample
    current_sample = int(args.sample)
    if current_sample < 1 or current_sample > 5:
        current_sample = 1
    
    # Show audio samples
    show_audio_samples()
    
    print(f"\nUsing server URL: {args.url}")
    print(f"Using audio sample: test_audio/speech_sample_{current_sample}.wav")
    
    # Connect to the server
    try:
        print("Connecting to server...")
        sio.connect(args.url, wait_timeout=10)
        
        # Give some time for initial setup
        time.sleep(2)
        
        # Main interaction loop
        while sio.connected:
            try:
                user_input = input("\nPress Enter to speak, or 'q' to quit, or 1-5 to select a sample: ")
                
                if user_input.lower() == 'q':
                    break
                    
                if user_input.isdigit() and 1 <= int(user_input) <= 5:
                    # Use the specified sample
                    current_sample = int(user_input)
                    print(f"Using sample {current_sample}")
                
                # Get the current state from the server
                state = get_current_state()
                print(f"Current state: {state}")
                
                # Start speaking if in appropriate state
                if state in ["idle", "waiting"]:
                    start_speaking()
                else:
                    print(f"Waiting for server (current state: {state})...")
                
                # Wait a bit to avoid UI clutter
                time.sleep(1)
            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if sio.connected:
            try:
                sio.disconnect()
                print("Disconnected from server")
            except:
                pass

if __name__ == "__main__":
    main()