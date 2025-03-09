#!/usr/bin/env python
"""
Enhanced Socket.IO test client for VR Interview Server (v5)
"""

import socketio
import time
import argparse
import os
import base64
import wave
import numpy as np
from threading import Event, Lock, Thread

# Create Socket.IO client
sio = socketio.Client(logger=False, reconnection=True, reconnection_attempts=5)

# Global variables
session_id = None
current_state = "disconnected"
current_sample = 1
temp_monitor_active = True  # Control state monitoring activity
state_lock = Lock()
audio_sent_event = Event()
stop_speaking_sent_event = Event()
response_received_event = Event()
connected_event = Event()  # New event to track connection status

# Event handlers
@sio.event
def connect():
    print("Connected to server!")
    global current_state
    with state_lock:
        current_state = "connected"
    connected_event.set()  # Signal that connection is established

@sio.event
def connect_error(data):
    print(f"Connection error: {data}")
    connected_event.clear()

@sio.event
def disconnect():
    print("Disconnected from server!")
    global current_state
    with state_lock:
        current_state = "disconnected"
    connected_event.clear()

@sio.on('session_created')
def on_session_created(data):
    global session_id
    session_id = data['session_id']
    print(f"Session created: {session_id}")
    
    # Wait a bit before joining to ensure connection is stable
    time.sleep(2)
    
    # Wait until we're fully connected before joining
    if not connected_event.is_set():
        print("Waiting for connection to establish before joining session...")
        connected_event.wait(timeout=5)
    
    if sio.connected and connected_event.is_set():
        # Join the session
        join_session()
    else:
        print("Can't join session - not connected properly")

@sio.on('session_configured')
def on_session_configured(data):
    print(f"Session configured!")

@sio.on('state_update')
def on_state_update(data):
    global current_state
    state = data['state']
    turn = data.get('turn', 0)
    previous = data.get('previous_state', '')
    session = data.get('session_id', '')
    
    # Only log when state actually changes or when explicitly requested
    if previous != state or previous == "":
        print(f"State update: {previous} -> {state} (Turn: {turn}, Session: {session})")
    
    with state_lock:
        current_state = state
        
        # Print an obvious marker when waiting state is reached
        if state == "waiting":
            print("\n*** READY FOR NEXT QUESTION ***\n")
            # Also set response received event if it's not set
            if not response_received_event.is_set():
                response_received_event.set()

@sio.on('explicit_state_update')
def on_explicit_state_update(data):
    """Handle explicit state updates from the server."""
    global current_state
    state = data['state']
    turn = data.get('turn', 0)
    previous = data.get('previous_state', '')
    session = data.get('session_id', '')
    
    
    with state_lock:
        # Always update the state with explicit updates
        current_state = state
        
        # If we get an explicit update to 'waiting' or 'responding', set the response received event
        if state in ['waiting', 'responding']:
            if not response_received_event.is_set():
                print("Setting response_received_event based on explicit state update")
                response_received_event.set()
        
        # Print an obvious marker when waiting state is reached
        if state == "waiting":
            print("\n*** READY FOR NEXT QUESTION ***\n")
        
        # Request a refresh of the state in 2 seconds to confirm state is synchronized
        def _delayed_state_refresh():
            time.sleep(2)
            if sio.connected:
                get_server_state()
        
        # Start delayed refresh thread
        refresh_thread = Thread(target=_delayed_state_refresh, daemon=True)
        refresh_thread.start()

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
    print(f"DEBUG-STATE-FLOW: Received response_ready event from server")
    global current_state
    response_text = data.get('text', '')
    audio_url = data.get('audio_url', '')
    session = data.get('session_id', '')
    is_recovery = data.get('is_recovery', False)
    
    if is_recovery:
        print(f"\n========== AUTO-RECOVERY RESPONSE ==========\n{response_text}\n=========================================\n")
        print("The server automatically generated this response after detecting a stuck state.")
    else:
        print(f"\n========== INTERVIEWER RESPONSE ==========\n{response_text}\n=========================================\n")
        print(f"Audio URL: {audio_url}")
    
    # Signal that we received a response
    response_received_event.set()
    
    # Update the current state if it's still in processing
    with state_lock:
        if current_state == "processing":
            print("Updating state from 'processing' to 'waiting' after receiving response")
            current_state = "waiting"
        # Force a state update request to ensure synchronization
        get_server_state()
    
    print("\n*** READY FOR NEXT QUESTION ***\n")

@sio.on('ready_for_next_input')
def on_ready_for_next_input(data):
    print(f"DEBUG-STATE-FLOW: Received ready_for_next_input event from server")
    """Handle ready for next input event."""
    global current_state
    state = data.get('state', 'waiting')
    turn = data.get('turn', 0)
    session = data.get('session_id', '')
    
    print(f"\n*** SERVER READY FOR NEXT INPUT (Turn: {turn}) ***\n")
    
    with state_lock:
        current_state = state
        # Force the response received event to be set
        if not response_received_event.is_set():
            response_received_event.set()
            print("Set response_received_event based on ready_for_next_input event")

@sio.on('error')
def on_error(data):
    print(f"Error from server: {data['message']}")
    # If we get an error, try to move to waiting state to recover
    with state_lock:
        if current_state == "processing":
            current_state = "waiting"
            print("Forced state to 'waiting' after error")
            response_received_event.set()
@sio.on('audio_received')
def on_audio_received(data):
    """Handle audio received confirmation."""
    print("DEBUG-STATE-FLOW: Server confirmed audio data received.")
    print("Server confirmed audio data received.")
@sio.on('*')
def catch_all(event, data):
    """Catch all events that aren't handled specifically."""
    # Print only important events, ignore common events like ping/pong
    if event not in ['ping', 'pong', 'connect', 'disconnect', 'error', 'state_update', 
                    'session_created', 'session_configured', 'listening_started',
                    'processing_started', 'response_ready', 'explicit_state_update',
                    'ready_for_next_input']:
        print(f"Unhandled event received: {event}")

def join_session():
    """Join the created session."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return
    
    try:
        # Make sure we're connected
        if not connected_event.is_set() or not sio.connected:
            print("Not connected to server, cannot join session")
            return
            
        print(f"Joining session: {session_id}")
        sio.emit('join_session', {'session_id': session_id})
        
        # Wait a moment to ensure join is processed
        time.sleep(2)
        
        # Configure the session if still connected
        if sio.connected:
            configure_session()
        else:
            print("Lost connection after joining session")
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

def debug_state():
    """Debug the current state and status of various events."""
    with state_lock:
        state = current_state
    
    print("\n=== DEBUG STATE INFORMATION ===")
    print(f"Current state: {state}")
    print(f"Session ID: {session_id}")
    print(f"Connected: {sio.connected}")
    print(f"Connected event: {connected_event.is_set()}")
    print(f"Response received event: {response_received_event.is_set()}")
    print(f"Audio sent event: {audio_sent_event.is_set()}")
    print(f"Stop speaking sent event: {stop_speaking_sent_event.is_set()}")
    print("==============================\n")

def get_server_state():
    """Send a request to get the current server-side state."""
    global session_id
    if not session_id:
        print("=============================\nNO SESSION ID\n=============================")
        return
    try:
        sio.emit('get_state', {'session_id': session_id})
    except Exception as e:
        print(f"Error requesting server state: {e}")

def wait_for_state_change(target_states, timeout=60):
    """
    Wait for the state to change to one of the target states.
    
    Args:
        target_states (list): List of target states to wait for
        timeout (int): Maximum time to wait in seconds
        
    Returns:
        bool: True if state changed to target, False if timed out
    """
    start_time = time.time()
    check_interval = 5.0  # Check every 1 second
    
    # Add more frequent refreshes when waiting for response states
    if "waiting" in target_states or "responding" in target_states:
        refresh_interval = 5.0  # Ask for state refresh every 5 seconds
    else:
        refresh_interval = 10.0  # Otherwise less frequently
        
    next_refresh = start_time + refresh_interval
    
    while time.time() - start_time < timeout:
        current = get_current_state()
        
        # If we reached target state, success
        if current in target_states:
            print(f"State changed to {current}")
            return True
            
        # Time-based refreshes to help ensure state sync
        if time.time() > next_refresh:
            print(f"Requesting state refresh while waiting for {target_states}...")
            get_server_state()
            next_refresh = time.time() + refresh_interval
        
        # Special handling for waiting for response states
        if "waiting" in target_states or "responding" in target_states:
            elapsed = int(time.time() - start_time)
            
            # After 25 seconds, try more aggressively to recover
            if elapsed > 80 and current == "processing":
                print(f"\nWarning: Been in processing state for {elapsed}s - attempting recovery...")
                
                # Explicitly request state several times
                for i in range(3):
                    get_server_state()
                    time.sleep(5)
                
                # Force client to consider this successful after 80 seconds
                if elapsed > 80:
                    print(f"Force exit from wait loop after {elapsed}s in processing state")
                    
                    # Force state to waiting to recover client
                    with state_lock:
                        if current_state == "processing":
                            print("Force changing client state to 'waiting'")
                            current_state = "waiting"
                    
                    # Set response received event to unblock client
                    if not response_received_event.is_set():
                        print("Force setting response_received_event to unblock client")
                        response_received_event.set()
                    
                    return True
        
        # Sleep briefly to avoid busy waiting
        time.sleep(check_interval)
    
    # If we're here, we timed out
    print(f"Timed out waiting for state to change to {target_states}")
    
    # For these specific states, force success to avoid getting stuck
    if "waiting" in target_states or "responding" in target_states:
        print("Forcing success after timeout when waiting for response")
        
        # Force client state to waiting
        with state_lock:
            print("Force changing client state to 'waiting'")
            current_state = "waiting"
            
        # Force response received event
        if not response_received_event.is_set():
            print("Force setting response_received_event to unblock client")
            response_received_event.set()
            
        return True
        
    return False

def start_speaking():
    print(f"DEBUG-STATE-FLOW: Client attempting to start speaking")
    """Start the speaking process."""
    global session_id
    
    if not session_id:
        print("No session ID available")
        return False
    
    state = get_current_state()
    if state not in ["idle", "waiting"]:
        print(f"Cannot start speaking in state: {state}")
        
        # If we're in processing state for a long time, force transition to waiting
        if state == "processing":
            print("Forcing state transition from processing to waiting")
            with state_lock:
                current_state = "waiting"
                print("Forced state transition to waiting")
                # Also set response received event to avoid getting stuck
                if not response_received_event.is_set():
                    response_received_event.set()
                    print("Set response_received_event as part of force state transition")
        else:
            return False
    
    try:
        print("Starting to speak...")
        # Reset the events
        audio_sent_event.clear()
        stop_speaking_sent_event.clear()
        response_received_event.clear()
        
        sio.emit('start_speaking', {'session_id': session_id})
        
        # Wait briefly to give the server time to respond
        time.sleep(5)
        return True
    except Exception as e:
        print(f"Error starting to speak: {e}")
        return False

def stop_speaking():
    print(f"DEBUG-STATE-FLOW: Client attempting to stop speaking")
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
    print("Sending test audio...")
    global session_id, current_sample
    
    if file_path is None:
        file_path = f"test_audio/speech_sample_{current_sample}.wav"
    
    if not os.path.exists(file_path):
        print(f"Test audio file not found: {file_path}")
        stop_speaking()
        return
    
    print(f"Using audio file: {file_path}")
    
    try:
        # Read the audio file
        with wave.open(file_path, 'rb') as wf:
            audio_data = wf.readframes(wf.getnframes())
        
        # Send the entire audio in one chunk
        base64_audio = base64.b64encode(audio_data).decode('utf-8')
        
        print(f"Sending audio data ({len(audio_data)} bytes)")
        sio.emit('audio_data', {
            'session_id': session_id,
            'audio': base64_audio
        })
        
        print("Audio data sent successfully")
        audio_sent_event.set()  # Signal that audio has been sent
        
        # Wait a moment to ensure the server processes the audio
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

def state_monitoring_thread():
    """Thread function to periodically check the server state."""
    # Wait a bit before starting to check state
    time.sleep(5)  
    
    # Add flag for temporary pausing of monitoring
    global temp_monitor_active
    temp_monitor_active = True
    
    while True:
        try:
            # Only check if monitoring is active
            if temp_monitor_active and sio.connected and session_id and connected_event.is_set():
                # Request current state from server
                get_server_state()
            time.sleep(5)  # Check every 5 seconds
        except Exception as e:
            print(f"Error in state monitoring thread: {e}")
            time.sleep(5)  # Keep trying

def main():
    parser = argparse.ArgumentParser(description='Enhanced VR Interview Test Client')
    parser.add_argument('--url', default='http://localhost:8082', help='Socket.IO server URL')
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
        # Connect using standard namespace with improved reconnection settings
        sio.connect(args.url, wait_timeout=15, namespaces=['/'], 
                   socketio_path='socket.io', transports=['polling', 'websocket'])
        
        # Wait for the connection to be confirmed
        if not connected_event.wait(timeout=10):
            print("Error: Could not confirm connection. Exiting.")
            return
        
        # Start the state monitoring thread - but with much less frequency
        monitor_thread = Thread(target=state_monitoring_thread, daemon=True)
        monitor_thread.start()
        
        # Give some time for initial setup
        time.sleep(2)
        
        # Main interaction loop
        while sio.connected:
            try:
                user_input = input("\nPress Enter to speak, or 'q' to quit, 'd' to debug, 'r' to refresh state, or 1-5 to select a sample: ")
                
                if user_input.lower() == 'q':
                    break
                    
                if user_input.lower() == 'd':
                    debug_state()
                    continue
                    
                if user_input.lower() == 'r':
                    print("Refreshing server state...")
                    get_server_state()
                    time.sleep(5)
                    print(f"Current state: {get_current_state()}")
                    continue
                
                if user_input.isdigit() and 1 <= int(user_input) <= 5:
                    # Use the specified sample
                    current_sample = int(user_input)
                    print(f"Using sample {current_sample}")
                
                # Get the current state from the server
                state = get_current_state()
                print(f"Current state: {state}")
                
                # If we're in processing state but have been stuck there for a while,
                # force a transition to waiting
                if state == "processing":
                    print("Detected processing state - checking if we're stuck...")
                    # Request a state refresh explicitly
                    get_server_state()
                    time.sleep(5)
                    
                    # If still in processing, force a state change
                    state = get_current_state()
                    if state == "processing":
                        print("Still in processing state - forcing transition to waiting")
                        with state_lock:
                            current_state = "waiting"
                            print("Forced state to waiting")
                            
                        # Also set response received event
                        if not response_received_event.is_set():
                            response_received_event.set()
                            
                        # Update state variable
                        state = "waiting"
                
                # Pause the state monitoring thread temporarily
                temp_monitor_active = False
                
                # Start speaking if in appropriate state
                if state in ["idle", "waiting"]:
                    if start_speaking():
                        # Don't stop speaking immediately - let the audio finish
                        # The listening_started event handler will trigger the audio send
                        
                        # Wait for audio to be sent
                        print("Waiting for audio to be sent...")
                        audio_sent_event.wait(timeout=10)
                        
                        # If audio was sent, signal end of speech
                        if audio_sent_event.is_set():
                            print("\nPausing for 5 seconds to ensure audio processing...")
                            time.sleep(5)
                            print("\n\nSignaling end of speech to server...")
                            stop_speaking()
                            print("signal ran, now wait for acknowledment")
                            # Wait for stop speaking to be acknowledged
                            stop_speaking_sent_event.wait(timeout=5)
                            
                            print("Resuming client monitoring...")
                            
                            # Wait for processing state
                            if wait_for_state_change(["processing"], timeout=10):
                                print("State changed to processing")
                                
                                # Wait for response
                                wait_success = wait_for_state_change(["waiting", "responding"], timeout=45)
                                
                                # If no response after timeout, force recovery
                                if not wait_success:
                                    print("No state change to waiting/responding after timeout")
                                    print("Forcing client recovery...")
                                    
                                    # Force client state to waiting
                                    with state_lock:
                                        current_state = "waiting"
                                        
                                    # Force response received event
                                    if not response_received_event.is_set():
                                        response_received_event.set()
                            else:
                                print("Failed to transition to processing state")
                        else:
                            print("Audio wasn't sent successfully")
                            # Try to stop speaking anyway
                            stop_speaking()
                else:
                    print(f"Cannot start speaking in state: {state}")
                    print("Trying to force state to waiting...")
                    
                    # Force client state to waiting
                    with state_lock:
                        current_state = "waiting"
                        
                    # Force response received event
                    if not response_received_event.is_set():
                        response_received_event.set()
                
                # Re-enable state monitoring
                temp_monitor_active = True
                
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