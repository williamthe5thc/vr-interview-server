#!/usr/bin/env python
"""
Fixed Socket.IO test client for VR Interview Server
"""

import socketio
import time
import argparse
import os
import base64
import wave
import numpy as np

# Create Socket.IO client with proper namespace handling
sio = socketio.Client(logger=False)

# Global variables
session_id = None
current_state = "disconnected"
namespace_connected = False

# Event handlers
@sio.event
def connect():
    print("Connected to server!")

@sio.event
def connect_error(data):
    print(f"Connection error: {data}")

@sio.event
def disconnect():
    print("Disconnected from server!")
    global current_state, namespace_connected
    current_state = "disconnected"
    namespace_connected = False

# Handle namespace connection
@sio.on('*')
def catch_all(event, data):
    global namespace_connected
    if not namespace_connected:
        namespace_connected = True
        print("Namespace connection established")

@sio.on('session_created')
def on_session_created(data):
    global session_id
    session_id = data['session_id']
    print(f"Session created: {session_id}")
    
    # Wait for namespace connection before joining
    time.sleep(1)  # Give connection time to stabilize
    join_session()

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

def join_session():
    """Join the created session."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return
    
    try:
        # Only proceed if namespace is connected
        if namespace_connected:
            print(f"Joining session: {session_id}")
            sio.emit('join_session', {'session_id': session_id})
            time.sleep(0.5)  # Give server time to process
            configure_session()
        else:
            print("Namespace not connected yet, waiting...")
            time.sleep(1)
            join_session()  # Try again
    except Exception as e:
        print(f"Error joining session: {e}")
        time.sleep(1)
        join_session()  # Try again

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

def start_speaking():
    """Start the speaking process."""
    global session_id, current_state
    
    if not session_id:
        print("No session ID available")
        return False
    
    if current_state not in ["idle", "waiting"]:
        print(f"Cannot start speaking in state: {current_state}")
        return False
    
    try:
        print("Starting to speak...")
        sio.emit('start_speaking', {'session_id': session_id})
        return True
    except Exception as e:
        print(f"Error starting to speak: {e}")
        return False

def stop_speaking():
    """Stop the speaking process."""
    global session_id, current_state
    print("stoping the speaking entry function")
    if not session_id:
        print("No session ID available")
        return False
    
    if current_state != "listening":
        print(f"Cannot stop speaking in state: {current_state}")
        return False
    
    try:
        print("Stopping speaking...")
        sio.emit('stop_speaking', {'session_id': session_id})
        return True
    except Exception as e:
        print(f"Error stopping speaking: {e}")
        return False

def send_test_audio(file_path="test_audio/speech_sample_1.wav"):
    """Send a test audio file to the server."""
    global session_id
    
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
        
        print("Audio data sent")
        time.sleep(1)  # Give the server time to process
        print("slept")
        # Stop speaking
        stop_speaking()
        print("stop speaking")        
    except Exception as e:
        print(f"Error sending audio: {e}")
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
    parser = argparse.ArgumentParser(description='Fixed VR Interview Test Client')
    parser.add_argument('--url', default='http://localhost:8081', help='Socket.IO server URL')
    parser.add_argument('--sample', default='1', help='Sample number (1-5)')
    args = parser.parse_args()
    
    # Determine the audio sample to use
    sample_num = int(args.sample)
    if sample_num < 1 or sample_num > 5:
        sample_num = 1
    sample_file = f"test_audio/speech_sample_{sample_num}.wav"
    
    # Show audio samples
    show_audio_samples()
    
    print(f"\nUsing server URL: {args.url}")
    print(f"Using audio sample: {sample_file}")
    
    # Connect to the server
    try:
        # Use a connection timeout
        print("Connecting to server...")
        sio.connect(args.url, wait_timeout=10)
        print("Server connection established")
        
        # Main interaction loop
        while sio.connected:
            user_input = input("\nPress Enter to speak, or 'q' to quit, or 1-5 to select a sample: ")
            
            if user_input.lower() == 'q':
                break
                
            if user_input.isdigit() and 1 <= int(user_input) <= 5:
                # Use the specified sample
                sample_file = f"test_audio/speech_sample_{int(user_input)}.wav"
                print(f"Using sample {user_input}")
                
            # Start speaking
            if start_speaking():
                # The audio will be sent when listening_started event is received
                pass
            else:
                print("Failed to start speaking - check server state")
            
            # Wait a bit to avoid UI clutter
            time.sleep(1)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if sio.connected:
            sio.disconnect()
            print("Disconnected from server")

if __name__ == "__main__":
    main()