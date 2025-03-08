"""
WebSocket event handlers for the VR Interview Server.
Handles all real-time communication with VR clients.
"""

import os
import uuid
import base64
import logging
import threading
import queue
import json
from flask import request, current_app
from flask_socketio import emit, join_room, leave_room
import eventlet

# Import modules
from app.state_manager import InterviewStateManager
from app.interview_session import InterviewSession
from services.speech_processing import transcribe_audio, generate_speech
from services.llm_service import generate_llm_response
from app import create_app

# Initialize state manager
state_manager = InterviewStateManager()
logger = logging.getLogger("interview-server")
logger.info("web socket started")

# Create a queue for thread-safe socket.io operations
socketio_queue = queue.Queue()
socketio_instance = None

def register_events(socketio):
    """Register WebSocket event handlers with the SocketIO instance."""
    global socketio_instance
    socketio_instance = socketio
    state_manager.set_socketio(socketio)

    # Start the background task to process queued socket.io operations
    socketio.start_background_task(process_socketio_queue)

    @socketio.on('connect')
    def handle_connect():
        """Handle new client connections."""
        client_id = request.sid
        logger.info(f"Client connected: {client_id}")
        
        # Create a new session
        session_id = str(uuid.uuid4())
        
        # Create session with default configuration
        config = current_app.config.get('APP_CONFIG', {})
        default_position = config.get('interview', {}).get('default_position', "Software Engineer")
        default_difficulty = config.get('interview', {}).get('default_difficulty', 0.5)
        
        session = InterviewSession(
            session_id=session_id, 
            client_id=client_id,
            position=default_position,
            difficulty=default_difficulty
        )
        
        # Register session
        state_manager.add_session(session)
        
        # Emit session created event
        emit('session_created', {'session_id': session_id})
        logger.info(f"Session created: {session_id} for client: {client_id}")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnections."""
        client_id = request.sid
        logger.info(f"Client disconnected: {client_id}")
        
        # Find and mark session as inactive
        session = state_manager.get_session_by_client_id(client_id)
        if session:
            logger.info(f"Marking session {session.session_id} as inactive")
            state_manager.mark_session_inactive(session.session_id)
    
    @socketio.on('join_session')
    def handle_join_session(data):
        """Handle client joining a specific session."""
        session_id = data.get('session_id')
        client_id = request.sid
        logger.info(f"join session thing")
        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Join the room for this session
        join_room(session_id)
        # Also join a room with the client ID
        join_room(client_id)
        logger.info(f"Client {client_id} joined session {session_id}")
        
        # Update client ID
        session.client_id = client_id
        
        # Send current state
        emit('state_update', {
            'session_id': session_id,
            'state': session.state,
            'turn': session.turn_index
        })
    
    @socketio.on('configure_session')
    def handle_configure_session(data):
        """Configure session parameters."""
        session_id = data.get('session_id')
        config = data.get('config', {})
        logger.info(f"Client configure session")

        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Update session configuration
        if 'position' in config:
            session.position = config['position']
        
        if 'difficulty' in config:
            session.difficulty = float(config['difficulty'])
        
        if 'interviewer_type' in config:
            session.interviewer_type = config['interviewer_type']
        
        logger.info(f"Session {session_id} configured: {config}")
        emit('session_configured', {'session_id': session_id})
    
    @socketio.on('start_speaking')
    def handle_start_speaking(data):
        """Handle when user starts speaking."""
        session_id = data.get('session_id')
        logger.info(f"start speaking")

        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Check if we can transition to listening state
        if session.state not in ['idle', 'waiting']:
            emit('error', {'message': f'Cannot start speaking in {session.state} state'})
            return
        
        # Update session state
        state_manager.update_session_state(session_id, 'listening')
        logger.info(f"Session {session_id} now listening")
        
        # Initialize audio buffer
        session.clear_audio_buffer()
        
        emit('listening_started', {'session_id': session_id})
    
    @socketio.on('audio_data')
    def handle_audio_data(data):
        """Handle incoming audio data chunks."""
        logger.info(f"audio data")
        session_id = data.get('session_id')
        audio_chunk = data.get('audio')  # Base64 encoded audio
        
        if not session_id or not audio_chunk:
            return
        
        session = state_manager.get_session(session_id)
        if not session or session.state != 'listening':
            return
        
        try:
            # Decode base64 audio data
            audio_bytes = base64.b64decode(audio_chunk)
            
            # Add to session's audio buffer
            session.add_audio_chunk(audio_bytes)
            
            # Acknowledge receipt
            emit('audio_received', {'session_id': session_id})
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
    
    @socketio.on('stop_speaking')
    def handle_stop_speaking(data):
        """Handle when user stops speaking."""
        session_id = data.get('session_id')
        logger.info(f"Received stop_speaking event for session {session_id}")

        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Check if we're in listening state
        if session.state != 'listening':
            emit('error', {'message': f'Cannot stop speaking in {session.state} state'})
            return
        
        # Update session state
        state_manager.update_session_state(session_id, 'processing')
        logger.info(f"Session {session_id} now processing")
        
        # Save audio buffer to file
        audio_path = os.path.join(
            current_app.config['UPLOAD_FOLDER'], 
            f"{session_id}_{session.turn_index}.wav"
        )
        session.save_audio_buffer(audio_path)
        
        # Process in a separate thread
        processing_thread = threading.Thread(
            target=process_audio_and_respond,
            args=(session_id, audio_path)
        )
        processing_thread.daemon = True
        processing_thread.start()
        
        emit('processing_started', {'session_id': session_id})
    
    @socketio.on('reset_session')
    def handle_reset_session(data):
        """Reset session to initial state."""
        session_id = data.get('session_id')
        
        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Reset session
        state_manager.reset_session(session_id)
        
        emit('session_reset', {'session_id': session_id})
        logger.info(f"Session {session_id} reset")
        
        # Send current state
        emit('state_update', {
            'session_id': session_id,
            'state': 'idle',
            'turn': 0
        })

def queue_emit(event, data, room=None, to=None):
    """
    Queue an emit operation to be processed by the main eventlet thread.
    This makes Socket.IO operations thread-safe.
    """
    socketio_queue.put((event, data, room, to))
    logger.info(f"Queued {event} event for room {room} or recipient {to}")

def process_socketio_queue():
    """
    Process queued Socket.IO operations in the main eventlet thread.
    This function runs as a background task.
    """
    logger.info("Started Socket.IO queue processing background task")
    while True:
        try:
            # Get an item from the queue (blocks until an item is available)
            event, data, room, to = socketio_queue.get(timeout=1.0)
            
            # Emit the event
            if room:
                socketio_instance.emit(event, data, room=room)
                logger.info(f"Emitted {event} event to room {room}")
            elif to:
                socketio_instance.emit(event, data, to=to)
                logger.info(f"Emitted {event} event to recipient {to}")
            else:
                socketio_instance.emit(event, data)
                logger.info(f"Emitted {event} event globally")
                
            # Mark the task as done
            socketio_queue.task_done()
        except queue.Empty:
            # If the queue is empty (timeout), just continue
            pass
        except Exception as e:
            logger.error(f"Error processing socketio queue: {e}")
        
        # Give eventlet a chance to switch
        eventlet.sleep(0)

def load_config():
    """Load configuration from config.json - mirrors function in server.py"""
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
                "tts_engine": "gTTS",
                "alltalk_path": "D:\\AllTalk",
                "whisper_model": "base"
            }
        }

def process_audio_and_respond(session_id, audio_path):
    """
    Process audio input and generate interviewer response.
    This function runs in a separate thread.
    """
    logger.info(f"Starting process_audio_and_respond for session {session_id}")
    
    try:
        session = state_manager.get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found during processing")
            return
        logger.info(f"Session retrieved: {session_id}")
        
        logger.info(f"Processing audio file at: {audio_path}")
        
        # Check if audio file exists
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            state_manager.update_session_state(session_id, 'error')
            queue_emit('error', {'message': 'Audio file not found'}, room=session_id)
            return
        logger.info(f"Audio file exists at {audio_path}")
        
        # Transcribe audio
        logger.info("Starting audio transcription...")
        transcription = transcribe_audio(audio_path)
        if not transcription:
            logger.error(f"Failed to transcribe audio for session {session_id}")
            state_manager.update_session_state(session_id, 'error')
            queue_emit('error', {'message': 'Failed to transcribe audio'}, room=session_id)
            return
        
        logger.info(f"Transcription for session {session_id}: {transcription}")
        
        # Add user message to conversation history
        session.add_message("user", transcription)
        logger.info("Added user message to conversation history")
        
        # Load config and create a fresh app context - FIX FOR CIRCULAR IMPORT ISSUE
        config = load_config()
        app, _ = create_app(config)
        
        # Create application context properly
        with app.app_context():
            # Now we're inside an application context
            logger.info("Generating LLM response...")
            
            # Get interviewer personality prompt from config
            interviewer_type = session.interviewer_type
            position = session.position
            difficulty = session.difficulty
            
            logger.info(f"Interview type is {interviewer_type}")
            interviewer_prompts = config.get('interview', {}).get('interviewer_types', {})
            personality_prompt = interviewer_prompts.get(
                interviewer_type, 
                "You are an interviewer conducting a job interview."
            )
            
            # Format conversation history for LLM
            from services.llm_service import format_conversation_for_llm
            formatted_history = format_conversation_for_llm(session.conversation_history)
            
            # Generate response from LLM
            response_text = generate_llm_response(
                transcription,
                formatted_history,
                personality_prompt,
                position,
                difficulty,
                config
            )
            
            if not response_text:
                logger.error(f"Failed to generate LLM response for session {session_id}")
                state_manager.update_session_state(session_id, 'error')
                queue_emit('error', {'message': 'Failed to generate response'}, room=session_id)
                return
                
            logger.info(f"LLM response generated: {response_text}")
            
            # Add interviewer message to conversation history
            session.add_message("interviewer", response_text)
            
            # Generate speech from text
            response_audio_path = os.path.join(
                app.config['RESPONSE_FOLDER'], 
                f"{session_id}_{session.turn_index}.wav"
            )
            
            success = generate_speech(response_text, response_audio_path, config)
            if not success:
                logger.warning(f"Failed to generate speech for session {session_id}, continuing with text only")
            
            # Update state to responding
            state_manager.update_session_state(session_id, 'responding')
            
            # Construct relative URL for audio file
            # This will be requested via HTTP
            audio_url = f"/responses/{session_id}_{session.turn_index}.wav"
            
            # Send response to client using queue_emit for thread safety
            logger.info(f"Sending response to client {session.client_id}: {response_text[:50]}...")
            
            # Try multiple emission methods for reliability
            # 1. Emit to room
            queue_emit('response_ready', {
                'session_id': session_id,
                'text': response_text,
                'audio_url': audio_url
            }, room=session_id)
            
            # 2. Emit directly to client ID
            if session.client_id:
                queue_emit('response_ready', {
                    'session_id': session_id,
                    'text': response_text,
                    'audio_url': audio_url
                }, to=session.client_id)
            
            # Wait a bit to simulate audio playback (client will notify when done in real impl)
            # In a full implementation, the client would signal when audio playback is complete
            estimated_playback_time = len(response_text.split()) * 0.3  # Rough estimate: 0.3s per word
            eventlet.sleep(max(estimated_playback_time, 2))
            
            # Update turn index and move to waiting state
            session.turn_index += 1
            state_manager.update_session_state(session_id, 'waiting')
            
            # Send final state update explicitly
            logger.info(f"Sending final state update to client {session.client_id} for session {session_id}")
            
            # Use multiple approaches to ensure the state update gets through
            # 1. Room-based approach
            queue_emit('state_update', {
                'session_id': session_id,
                'state': 'waiting',
                'turn': session.turn_index,
                'previous_state': 'responding'
            }, room=session_id)
            
            # 2. Direct to client approach
            if session.client_id:
                queue_emit('state_update', {
                    'session_id': session_id,
                    'state': 'waiting',
                    'turn': session.turn_index,
                    'previous_state': 'responding'
                }, to=session.client_id)
            
    except Exception as e:
        logger.error(f"Error in process_audio_and_respond: {e}")
        state_manager.update_session_state(session_id, 'error')
        queue_emit('error', {'message': f'Processing error: {str(e)}'}, room=session_id)