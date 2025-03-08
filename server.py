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

# Needed for eventlet WebSocket
eventlet.monkey_patch()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
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
    
    # Start server
    socketio.run(
        app, 
        host=config['server']['host'], 
        port=config['server']['port'],
        debug=config['server']['debug'],
        use_reloader=False
    )