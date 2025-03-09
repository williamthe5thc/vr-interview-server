#!/usr/bin/env python
"""
Main entry point for the VR Interview Practice Application server.
Initializes the Flask app and WebSocket server.
"""

import os
import sys
import json
import logging
import threading
import eventlet
import atexit

# Needed for eventlet WebSocket
eventlet.monkey_patch()

# Increase eventlet concurrency
try:
    # Try to set debug options if available
    # Skip debug_blocking on Windows since it uses SIGALRM which is not available
    import platform
    if platform.system() != "Windows":
        eventlet.hubs.get_hub().debug_blocking = True  # Enable detection of blocking operations
        # These may not be available in all eventlet versions
        if hasattr(eventlet, 'debug'):
            eventlet.debug.hub_blocking_detection(True)
            eventlet.debug.hub_exceptions(True)
except Exception as e:
    logger.warning(f"Could not enable eventlet debugging: {e}")
    # Continue without debug features

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set to INFO for production, DEBUG for development
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
# Set specific loggers to different levels
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('socketio').setLevel(logging.WARNING)
logger = logging.getLogger("interview-server")

# Import app factory
from app import create_app

def load_config():
    """Load configuration from config.json"""
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        logger.info("Using default configuration")
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 8080,
                "debug": True
            },
            "llm": {
                "model_path": "./phi-model",
                "temperature": 0.7,
                "max_tokens": 75
            },
            "audio": {
                "tts_engine": "gTTS",  # Options: "AllTalk", "gTTS"
                "alltalk_path": "D:\\AllTalk",
                "whisper_model": "base"
            }
        }

if __name__ == '__main__':
    # Load configuration
    config = load_config()
    
    # Create Flask app and SocketIO instance
    app, socketio = create_app(config)
    
    # Import after app creation to avoid circular imports
    from app.websocket import cleanup as websocket_cleanup
    
    # Register cleanup function to run at exit
    atexit.register(websocket_cleanup)
    
    # Start cleanup thread for inactive sessions
    from app.utils import cleanup_inactive_sessions
    cleanup_thread = threading.Thread(
        target=cleanup_inactive_sessions,
        args=(app.config.get('SESSION_TIMEOUT', 1800),)
    )
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    # Log startup information
    logger.info(f"Starting WebSocket server on http://{config['server']['host']}:{config['server']['port']}")
    logger.info(f"Using LLM model: {config['llm']['model_path']}")
    logger.info(f"Using TTS engine: {config['audio']['tts_engine']}")
    # Debug state flow message removed
    
    # Increase eventlet worker pool size before running the server
    # This allows more concurrent operations
    try:
        if hasattr(eventlet, 'tpool') and hasattr(eventlet.tpool, 'spawn_n'):
            eventlet.spawn_n = eventlet.tpool.spawn_n
    except Exception as e:
        logger.warning(f"Could not configure eventlet spawn_n: {e}")
    
    # Configure eventlet to use a larger thread pool
    eventlet.wsgi.MAX_HEADER_LINE = 16384
    eventlet.wsgi.MAX_REQUEST_LINE = 32768
    
    # Start server with enhanced configuration
    try:
        # Try with minimal configuration to avoid compatibility issues
        socketio.run(
            app, 
            host=config['server']['host'], 
            port=config['server']['port'],
            debug=config['server']['debug'],
            use_reloader=False
        )
    except (TypeError, OSError) as e:
        if "10048" in str(e):
            # Port already in use error
            logger.error(f"Port {config['server']['port']} is already in use. Try a different port.")
            # Try with a different port
            try:
                alt_port = config['server']['port'] + 1
                logger.info(f"Attempting to use alternate port: {alt_port}")
                socketio.run(
                    app,
                    host=config['server']['host'],
                    port=alt_port,
                    debug=config['server']['debug'],
                    use_reloader=False
                )
            except Exception as ee:
                logger.error(f"Failed to start server on alternate port: {ee}")
        else:
            logger.error(f"Error starting server: {e}")