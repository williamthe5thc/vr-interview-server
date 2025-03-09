"""
WebSocket event handlers for the VR Interview Server.
Handles all real-time communication with VR clients.
"""

import os
import uuid
import base64
import logging
import threading
import time
import json
from flask import request, current_app
from flask_socketio import emit, join_room, leave_room
import eventlet

# Initialize state manager - must be done first
from app.state_manager import InterviewStateManager
state_manager = InterviewStateManager()

# Import other modules
from app.interview_session import InterviewSession
from services.worker_process import start_worker_process, stop_worker_process

# Set up logging
logger = logging.getLogger("interview-server")
logger.info("web socket started")

# Global variables
input_queue = None
output_queue = None
worker_process = None
processing_tasks = {}

def initialize_worker():
    """Initialize the worker process."""
    global input_queue, output_queue, worker_process
    if input_queue is None or output_queue is None or worker_process is None:
        input_queue, output_queue, worker_process = start_worker_process()

def register_events(socketio):
    """Register WebSocket event handlers with the SocketIO instance."""
    # Initialize worker if needed
    initialize_worker()
    
    # Set the socketio instance in the state manager
    state_manager.set_socketio(socketio)
    
    # Start the worker results handler thread
    result_thread = threading.Thread(target=handle_worker_results, args=(socketio,))
    result_thread.daemon = True
    result_thread.start()
    logger.info("Started worker results handler thread")

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
        # Debug message removed
        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Join the room for this session
        join_room(session_id)
        logger.info(f"Client {client_id} joined session {session_id}")
        
        # Update client ID
        session.client_id = client_id
        
        # Send current state
        emit('state_update', {
            'session_id': session_id,
            'state': session.state,
            'turn': session.turn_index
        })
        
        # Also send explicit state update
        emit('explicit_state_update', {
            'session_id': session_id,
            'state': session.state,
            'turn': session.turn_index,
            'previous_state': session.state
        })
    
    @socketio.on('configure_session')
    def handle_configure_session(data):
        """Configure session parameters."""
        session_id = data.get('session_id')
        config = data.get('config', {})
        # Debug message removed

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
        # Debug state flow message removed
        # Debug message removed

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
        # Debug message removed
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
        # Debug state flow message removed
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
        
        # Send task to worker process instead of processing directly
        submit_processing_task(session_id, audio_path, session)
        
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
    
    @socketio.on('get_state')
    def handle_get_state(data):
        """Handle requests for current state."""
        session_id = data.get('session_id')
        # Debug message removed
        
        if not session_id:
            logger.error("Missing session ID in get_state request")
            emit('error', {'message': 'Session ID required'})
            return
        
        session = state_manager.get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found for get_state request")
            emit('error', {'message': 'Session not found'})
            return
        
        # Send current state
        emit('state_update', {
            'session_id': session_id,
            'state': session.state,
            'turn': session.turn_index,
            'previous_state': session.state  # Same as current since this is just a status update
        })
        
        # Also send an explicit state update to handle any resynchronization issues
        emit('explicit_state_update', {
            'session_id': session_id,
            'state': session.state,
            'turn': session.turn_index,
            'previous_state': session.state  # Same as current since this is just a status update
        })
        
        # Add explicit ready_for_next_input notification if in waiting state
        if session.state == 'waiting':
            emit('ready_for_next_input', {
                'session_id': session_id,
                'state': 'waiting',
                'turn': session.turn_index
            })
            logger.info(f"Sent ready_for_next_input for session {session_id} during get_state")
        
        logger.info(f"State requested for session {session_id}: {session.state}")
        
        # If we're in processing state for more than 45 seconds, try to reset to waiting
        # This handles stuck states
        if session.state == 'processing' and hasattr(session, 'state_timestamp') and \
           (time.time() - session.state_timestamp) > 45:  # 45 seconds timeout
            
            logger.warning(f"Session {session_id} stuck in processing state for >45s during get_state - resetting to waiting")
            
            # Create a fallback response
            fallback_response = "Thank you for your question. I'd like to explore that further. Can you tell me more about your experience with this?"
            
            # Add interviewer message to conversation history
            session.add_message("interviewer", fallback_response)
            
            # Update state
            state_manager.update_session_state(session_id, 'waiting')
            
            # Log the fact that we're sending this message
            logger.info(f"Sending get_state recovery response to client for session {session_id}")
            
            # Send several notifications with slight delays to ensure delivery
            emit('response_ready', {
                'session_id': session_id,
                'text': fallback_response,
                'audio_url': '',
                'is_recovery': True
            })
            
            # Use non-blocking sleep
            eventlet.sleep(0)
            
            # Send an explicit state update
            emit('explicit_state_update', {
                'session_id': session_id,
                'state': 'waiting',
                'turn': session.turn_index,
                'previous_state': 'processing'
            })
            
            # Use non-blocking sleep
            eventlet.sleep(0)
            
            # Send ready for next input notification
            emit('ready_for_next_input', {
                'session_id': session_id,
                'state': 'waiting',
                'turn': session.turn_index
            })
            
            # Log recovery action
            logger.info(f"Session {session_id} recovered from stuck state during get_state")

def submit_processing_task(session_id, audio_path, session):
    """
    Submit a processing task to the worker process.
    
    Args:
        session_id (str): Session ID
        audio_path (str): Path to audio file
        session (InterviewSession): Session object
    """
    # Get the app
    app = get_app()
    
    # Extract needed session data to avoid serializing the entire session
    session_data = {
        'interviewer_type': session.interviewer_type,
        'position': session.position,
        'difficulty': session.difficulty,
        'turn_index': session.turn_index,
        'conversation_history': session.conversation_history
    }
    
    # Create task
    task = {
        'command': 'process_audio',
        'session_id': session_id,
        'audio_path': audio_path,
        'config': {
            'UPLOAD_FOLDER': app.config['UPLOAD_FOLDER'],
            'RESPONSE_FOLDER': app.config['RESPONSE_FOLDER'],
            'APP_CONFIG': app.config.get('APP_CONFIG', {})
        },
        'session_data': session_data,
        'timestamp': time.time()
    }
    
    # Make sure the worker is initialized
    initialize_worker()
    
    # Register task in tracking dictionary
    processing_tasks[session_id] = {
        'task': task,
        'status': 'submitted',
        'timestamp': time.time()
    }
    
    # Submit task to worker process
    input_queue.put(task)
    logger.info(f"Submitted processing task for session {session_id}")
    
def handle_worker_results(socketio):
    """
    Thread function that handles results from the worker process.
    
    Args:
        socketio (SocketIO): Socket.IO instance for emitting events
    """
    logger.info("Worker results handler started")
    
    # Import eventlet here to ensure it's available and to monkeypatch this function
    import eventlet
    eventlet.sleep(0)  # Give control back to the event loop immediately
    
    while True:
        try:
            # Use non-blocking queue operations to avoid blocking the thread
            try:
                # Non-blocking get with a very short timeout
                try:
                    result = output_queue.get(timeout=0.01)
                except:
                    # No result available, continue loop
                    eventlet.sleep(0.01)  # Short sleep to prevent CPU spinning
                    continue
                
                # Get session ID from result
                session_id = result.get('session_id')
                
                if not session_id:
                    logger.warning(f"Received result without session ID: {result}")
                    continue
                
                # Get app for app context
                app = get_app()
                
                # Get session
                with app.app_context():
                    session = state_manager.get_session(session_id)
                    
                    if not session:
                        logger.warning(f"Session {session_id} not found for result: {result}")
                        continue
                    
                    # Handle different result types
                    if result['status'] == 'error':
                        # Handle error
                        logger.error(f"Error in worker process for session {session_id}: {result.get('error')}")
                        
                        # Move to waiting state with an error message
                        state_manager.update_session_state(session_id, 'waiting')
                        
                        # Send error message to client
                        socketio.emit('error', {
                            'message': f"Processing error: {result.get('error')}",
                            'session_id': session_id
                        }, room=session_id)
                        
                        # Also send a recovery response
                        fallback_response = "I apologize, but I encountered an issue processing your response. Could you please try again or rephrase your question?"
                        
                        # Add interviewer message to conversation history
                        session.add_message("interviewer", fallback_response)
                        
                        # Send recovery response
                        socketio.emit('response_ready', {
                            'session_id': session_id,
                            'text': fallback_response,
                            'audio_url': '',
                            'is_recovery': True
                        }, room=session_id)
                        
                        # Send ready for next input notification
                        socketio.emit('ready_for_next_input', {
                            'session_id': session_id,
                            'state': 'waiting',
                            'turn': session.turn_index
                        }, room=session_id)
                        
                    elif result['status'] == 'progress':
                        # Handle progress update
                        logger.info(f"Progress update for session {session_id}: {result.get('message')} ({result.get('progress')}%)")
                        
                        # Store transcription if available
                        if 'transcription' in result:
                            # Make sure we haven't already added this message
                            if not any(msg.get('text') == result['transcription'] and msg.get('speaker') == 'user' 
                                    for msg in session.conversation_history):
                                session.add_message("user", result['transcription'])
                                logger.info(f"Added user message to conversation history for session {session_id}")
                        
                    elif result['status'] == 'success':
                        # Handle success
                        logger.info(f"Processing completed for session {session_id}")
                        
                        # Store response in conversation history if not already there
                        response_text = result.get('response_text', '')
                        if response_text and not any(msg.get('text') == response_text and msg.get('speaker') == 'interviewer' 
                               for msg in session.conversation_history):
                            session.add_message("interviewer", response_text)
                        
                        # Update state to waiting
                        state_manager.update_session_state(session_id, 'waiting')
                        
                        # Send response to client
                        socketio.emit('response_ready', {
                            'session_id': session_id,
                            'text': response_text,
                            'audio_url': result.get('audio_url', '')
                        }, room=session_id)
                        
                        # Use eventlet sleep instead of blocking time.sleep
                        eventlet.sleep(0)
                        
                        # Send explicit state update
                        socketio.emit('explicit_state_update', {
                            'session_id': session_id,
                            'state': 'waiting',
                            'turn': session.turn_index,
                            'previous_state': 'processing'
                        }, room=session_id)
                        
                        # Increment turn index
                        session.turn_index += 1
                        
                        # Send ready for next input notification
                        socketio.emit('ready_for_next_input', {
                            'session_id': session_id,
                            'state': 'waiting',
                            'turn': session.turn_index
                        }, room=session_id)
                    
                    # Update task tracking
                    if session_id in processing_tasks:
                        processing_tasks[session_id]['status'] = result['status']
                        processing_tasks[session_id]['updated'] = time.time()
                        
                        # Remove completed tasks after some time
                        if result['status'] in ['success', 'error']:
                            def cleanup_task():
                                # Use non-blocking approach for cleanup
                                start_time = time.time()
                                def do_cleanup():
                                    if time.time() - start_time >= 60 and session_id in processing_tasks:
                                        del processing_tasks[session_id]
                                import eventlet
                                eventlet.sleep(60)  # Non-blocking sleep
                                do_cleanup()
                            
                            cleanup_thread = threading.Thread(target=cleanup_task)
                            cleanup_thread.daemon = True
                            cleanup_thread.start()
            except Exception as e:
                # Just log and continue in case of error getting or processing a result
                if "empty" not in str(e).lower():  # Ignore "queue is empty" errors
                    logger.error(f"Error processing worker result: {e}")
            
            # Use eventlet sleep to avoid blocking the event loop
            eventlet.sleep(0)
            
        except Exception as e:
            logger.error(f"Error in worker result handler: {e}")
            eventlet.sleep(0.1)  # Use shorter, non-blocking sleep on error

def get_app():
    """
    Function to get the Flask app instance from the main module.
    This avoids circular imports.
    """
    try:
        from flask import current_app
        return current_app._get_current_object()
    except RuntimeError:
        # If we're outside the application context
        import sys
        if 'server' in sys.modules:
            return sys.modules['server'].app
        else:
            # If all else fails, import directly
            try:
                from app import create_app
                import json
                try:
                    with open("config.json", "r") as f:
                        config = json.load(f)
                except:
                    # Default config if file not found
                    config = {"server": {"host": "0.0.0.0", "port": 8081}}
                app, _ = create_app(config)
                return app
            except Exception as e:
                logger.error(f"Error creating app in get_app: {e}")
                return None

def cleanup():
    """Clean up resources when server shuts down."""
    global input_queue, worker_process
    try:
        if input_queue is not None and worker_process is not None:
            # Send shutdown signal
            input_queue.put({'command': 'shutdown'})
            
            # Wait with timeout
            worker_process.join(timeout=5)
            
            # Force terminate if still running
            if worker_process.is_alive():
                worker_process.terminate()
                logger.info("Worker process terminated forcefully")
                
                # On Windows, we may need an additional kill
                import os
                import signal
                import platform
                if platform.system() == "Windows":
                    try:
                        # Try to kill the process directly by PID
                        import subprocess
                        subprocess.run(["taskkill", "/F", "/PID", str(worker_process.pid)], 
                                      shell=True, capture_output=True)
                        logger.info(f"Forced kill of worker process PID {worker_process.pid}")
                    except Exception as ke:
                        logger.warning(f"Could not kill worker process: {ke}")
            else:
                logger.info("Worker process exited gracefully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")