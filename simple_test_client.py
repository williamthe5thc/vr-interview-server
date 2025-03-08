import socketio
import time

# Create Socket.IO client
sio = socketio.Client(logger=True)  # Enable logging for debugging

@sio.event
def connect():
    print("Connected to server!")

@sio.event
def disconnect():
    print("Disconnected from server!")

@sio.on('session_created')
def on_session_created(data):
    session_id = data['session_id']
    print(f"Session created: {session_id}")
    
    # Join the session
    print(f"Joining session: {session_id}")
    sio.emit('join_session', {'session_id': session_id})

@sio.on('error')
def on_error(data):
    print(f"Error from server: {data['message']}")

# Connect to the server
url = 'http://localhost:8081'
print(f"Connecting to {url}...")
try:
    sio.connect(url)
    print("Connected, waiting for events...")
    sio.wait()
except Exception as e:
    print(f"Connection error: {e}")