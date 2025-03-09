"""
Flask application factory module for VR Interview Server.
Creates and configures the Flask app and SocketIO instance.
"""

import os
import logging
from flask import Flask
from flask_socketio import SocketIO

# Create SocketIO instance
socketio = SocketIO()
logger = logging.getLogger("interview-server")

def create_app(config=None):
    """
    Create and configure the Flask application.
    
    Args:
        config (dict, optional): Configuration dictionary.
    
    Returns:
        tuple: (Flask app, SocketIO instance)
    """
    # Create Flask app
    app = Flask(__name__)
    
    # Set default configuration
    app.config.update(
        SECRET_KEY=os.urandom(24),
        SESSION_TYPE="filesystem",
        UPLOAD_FOLDER="data/audio/uploads",
        RESPONSE_FOLDER="data/audio/responses",
        CONVERSATION_FOLDER="data/conversations",
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max upload size
        SESSION_TIMEOUT=1800  # 30 minutes
    )
    
    # Update with provided configuration
    if config:
        # Update session timeout
        if 'interview' in config and 'session_timeout' in config['interview']:
            app.config['SESSION_TIMEOUT'] = config['interview']['session_timeout']
        
        # Update path configurations
        if 'paths' in config:
            if 'uploads' in config['paths']:
                app.config['UPLOAD_FOLDER'] = config['paths']['uploads']
            if 'responses' in config['paths']:
                app.config['RESPONSE_FOLDER'] = config['paths']['responses']
            if 'conversations' in config['paths']:
                app.config['CONVERSATION_FOLDER'] = config['paths']['conversations']
        
        # Store complete config
        app.config['APP_CONFIG'] = config
    
    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESPONSE_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CONVERSATION_FOLDER'], exist_ok=True)
    
    # Initialize SocketIO with the app - handle compatibility with different versions
    try:
        # Full configuration with all optimizations
        socketio_kwargs = {
            'cors_allowed_origins': '*',  # Allow connections from any origin
            'async_mode': 'eventlet',
            'ping_timeout': 60,  # Increase ping timeout for longer operations
            'ping_interval': 25,  # More frequent pings to detect disconnects
            'max_http_buffer_size': 50 * 1024 * 1024,  # 50MB buffer for larger payloads
            'engineio_logger': True  # Enable detailed Socket.IO logging
        }
        
        # Test if socketio accepts these parameters
        test_socket = SocketIO(async_mode='eventlet', ping_timeout=60)
        del test_socket
    except TypeError as e:
        # Fallback to basic configuration
        logger.warning(f"Using basic SocketIO configuration due to: {e}")
        socketio_kwargs = {
            'cors_allowed_origins': '*',  # Allow connections from any origin
            'async_mode': 'eventlet'
        }
    
    # Update SocketIO config if provided
    if config and 'server' in config and 'cors_allowed_origins' in config['server']:
        socketio_kwargs['cors_allowed_origins'] = config['server']['cors_allowed_origins']
    
    socketio.init_app(app, **socketio_kwargs)
    
    # Import and register WebSocket event handlers
    from app.websocket import register_events
    register_events(socketio)
    
    # Import and register HTTP routes
    from app.routes import register_routes
    register_routes(app)
    
    # Log successful initialization
    logger.info("Flask app and SocketIO initialized successfully")
    
    return app, socketio