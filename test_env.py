# test_env.py
import flask
import eventlet
import socketio
import flask_socketio
import torch
try:
    import whisper
    whisper_imported = True
except ImportError:
    whisper_imported = False
try:
    import transformers
    transformers_imported = True
except ImportError:
    transformers_imported = False
try:
    import gtts
    gtts_imported = True
except ImportError:
    gtts_imported = False

print(f"Flask version: {flask.__version__}")
print(f"Eventlet version: {eventlet.__version__}")
print(f"SocketIO package imported: {socketio is not None}")
print(f"Flask-SocketIO package imported: {flask_socketio is not None}")
print(f"PyTorch version: {torch.__version__}")
print(f"Whisper imported: {whisper_imported}")
print(f"Transformers imported: {transformers_imported}")
print(f"gTTS imported: {gtts_imported}")

# Test creating a minimal Flask-SocketIO app to verify integration
try:
    app = flask.Flask(__name__)
    socketio_app = flask_socketio.SocketIO(app)
    print("Successfully created Flask-SocketIO app!")
except Exception as e:
    print(f"Error creating Flask-SocketIO app: {e}")

print("Basic environment test complete!")