"""
Manages interview session states and provides session management functionality.
"""

import time
import logging
import threading
import eventlet

# Import interview session class
from app.interview_session import InterviewSession

logger = logging.getLogger("interview-server")

class InterviewStateManager:
    """
    Manages the state of all active interview sessions.
    
    A singleton class that maintains the collection of active sessions
    and handles state transitions.
    """
    
    # Session state constants
    STATE_IDLE = "idle"              # Waiting for user to start speaking
    STATE_LISTENING = "listening"    # Actively recording user speech
    STATE_PROCESSING = "processing"  # Processing audio/generating response
    STATE_RESPONDING = "responding"  # Playing back LLM response
    STATE_WAITING = "waiting"        # Waiting for the next turn
    STATE_ERROR = "error"            # Error state
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure singleton pattern."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InterviewStateManager, cls).__new__(cls)
                # Initialize the instance
                cls._instance._initialize()
                
                # Use eventlet for broadcasting state updates
                # This is more compatible with Windows
                def broadcast_states():
                    """Periodically broadcast session states to clients"""
                    while True:
                        try:
                            # Sleep with longer interval to reduce log spam
                            eventlet.sleep(20)
                            
                            # Skip if socketio is not available
                            if not hasattr(cls._instance, 'socketio') or cls._instance.socketio is None:
                                continue
                            
                            # Process each active session
                            for session_id, session in cls._instance.active_sessions.items():
                                if not session.active:
                                    continue
                                    
                                try:
                                    # Send state update silently (no logging)
                                    cls._instance.socketio.emit('state_update', {
                                        'session_id': session_id,
                                        'state': session.state,
                                        'turn': session.turn_index,
                                        'previous_state': session.state
                                    }, room=session_id)
                                    # Debug broadcast message removed
                                    
                                    # Send explicit state update
                                    cls._instance.socketio.emit('explicit_state_update', {
                                        'session_id': session_id,
                                        'state': session.state,
                                        'turn': session.turn_index,
                                        'previous_state': session.state
                                    }, room=session_id)
                                    
                                    # Process stuck sessions
                                    if session.state == 'processing' and hasattr(session, 'state_timestamp'):
                                        stuck_time = time.time() - session.state_timestamp
                                        
                                        # Auto-recover after 40 seconds
                                        if stuck_time > 40:
                                            logger.warning(f"Session {session_id} stuck in processing state for >40s - auto-recovering")
                                            
                                            # Create fallback response
                                            fallback_response = "Thank you for your question. Let me think about that for a moment. Could you tell me more about your experience in this field while I formulate my thoughts?"
                                            
                                            # Add to conversation history
                                            session.add_message("interviewer", fallback_response)
                                            
                                            # Force state change
                                            cls._instance.update_session_state(session_id, 'waiting')
                                            
                                            # Send recovery signals
                                            cls._instance.socketio.emit('response_ready', {
                                                'session_id': session_id,
                                                'text': fallback_response,
                                                'audio_url': '',
                                                'is_recovery': True
                                            }, room=session_id)
                                            
                                            # Also send direct state update
                                            cls._instance.socketio.emit('explicit_state_update', {
                                                'session_id': session_id,
                                                'state': 'waiting',
                                                'turn': session.turn_index,
                                                'previous_state': 'processing'
                                            }, room=session_id)
                                            
                                            # Signal ready for next input
                                            cls._instance.socketio.emit('ready_for_next_input', {
                                                'session_id': session_id,
                                                'state': 'waiting',
                                                'turn': session.turn_index
                                            }, room=session_id)
                                            
                                    # For waiting state, always send ready_for_next_input
                                    if session.state == 'waiting':
                                        cls._instance.socketio.emit('ready_for_next_input', {
                                            'session_id': session_id,
                                            'state': 'waiting',
                                            'turn': session.turn_index
                                        }, room=session_id)
                                        # Debug broadcast message removed
                                        
                                except Exception as e:
                                    logger.error(f"Error broadcasting state for session {session_id}: {e}")
                                    
                        except Exception as e:
                            logger.error(f"Error in state broadcast greenthread: {e}")
                
                # Start broadcasting using eventlet greenthread (not normal thread)
                eventlet.spawn(broadcast_states)
                logger.info("Started state broadcast greenthread")
                
            return cls._instance
    
    def _initialize(self):
        """Initialize the state manager."""
        self.active_sessions = {}  # Dictionary of active sessions by session_id
        self.client_sessions = {}  # Dictionary of session_ids by client_id
        self.socketio = None
        logger.info("Interview State Manager initialized")
    
    def set_socketio(self, socketio_instance):
        """Set the SocketIO instance for sending updates."""
        self.socketio = socketio_instance
    
    def add_session(self, session):
        """
        Add a new session to the manager.
        
        Args:
            session (InterviewSession): The session to add
        """
        self.active_sessions[session.session_id] = session
        if session.client_id:
            self.client_sessions[session.client_id] = session.session_id
    
    def get_session(self, session_id):
        """
        Get a session by ID.
        
        Args:
            session_id (str): The session ID
            
        Returns:
            InterviewSession or None: The session if found, None otherwise
        """
        session = self.active_sessions.get(session_id)
        return session
    
    def get_session_by_client_id(self, client_id):
        """
        Get a session by client ID.
        
        Args:
            client_id (str): The client ID
            
        Returns:
            InterviewSession or None: The session if found, None otherwise
        """
        session_id = self.client_sessions.get(client_id)
        if session_id:
            return self.active_sessions.get(session_id)
        return None
    
    def remove_session(self, session_id):
        """
        Remove a session from the manager.
        
        Args:
            session_id (str): The session ID
        """
        session = self.active_sessions.get(session_id)
        if session:
            if session.client_id in self.client_sessions:
                del self.client_sessions[session.client_id]
            del self.active_sessions[session_id]
    
    def mark_session_inactive(self, session_id):
        """
        Mark a session as inactive.
        
        Args:
            session_id (str): The session ID
        """
        session = self.active_sessions.get(session_id)
        if session:
            session.active = False
            session.last_activity = time.time()
    
    def update_session_state(self, session_id, new_state):
        """
        Update the state of a session and notify clients.
        
        Args:
            session_id (str): The session ID
            new_state (str): The new state
        
        Returns:
            bool: True if successful, False otherwise
        """
        session = self.active_sessions.get(session_id)
        if not session:
            logger.warning(f"Attempt to update non-existent session: {session_id}")
            return False
        
        # Debug state flow message removed
        
        # Log state transition
        logger.info(f"Session {session_id} state change: {session.state} -> {new_state}")
        
        # Update session state
        old_state = session.state
        session.state = new_state
        session.last_activity = time.time()
        session.state_timestamp = time.time()  # Add state timestamp for timing tracking
        
        # Send state update to client using nonblocking approach
        if hasattr(self, 'socketio') and self.socketio:
            try:
                self.socketio.emit('state_update', {
                    'session_id': session_id,
                    'state': new_state,
                    'turn': session.turn_index,
                    'previous_state': old_state
                }, room=session_id)
                # Debug event message removed
                
                # Also send an explicit state update
                self.socketio.emit('explicit_state_update', {
                    'session_id': session_id,
                    'state': new_state,
                    'turn': session.turn_index,
                    'previous_state': old_state
                }, room=session_id)
                # Debug event message removed
                
                # If transitioning to waiting state, send ready_for_next_input
                if new_state == 'waiting':
                    self.socketio.emit('ready_for_next_input', {
                        'session_id': session_id,
                        'state': new_state,
                        'turn': session.turn_index
                    }, room=session_id)
                    # Debug event message removed
            except Exception as e:
                logger.error(f"Error sending state update: {e}")
        
        return True
    
    def reset_session(self, session_id):
        """
        Reset a session to its initial state.
        
        Args:
            session_id (str): The session ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        
        # Reset session properties
        session.state = self.STATE_IDLE
        session.turn_index = 0
        session.conversation_history = []
        session.last_activity = time.time()
        
        return True
    
    def get_active_sessions(self):
        """
        Get all active sessions.
        
        Returns:
            list: List of active sessions
        """
        return [s for s in self.active_sessions.values() if s.active]
    
    def get_inactive_sessions(self, timeout=1800):
        """
        Get all inactive sessions exceeding the timeout.
        
        Args:
            timeout (int): Timeout in seconds (default: 1800 = 30 minutes)
            
        Returns:
            list: List of inactive session IDs
        """
        current_time = time.time()
        return [
            session_id for session_id, session in self.active_sessions.items()
            if not session.active and (current_time - session.last_activity) > timeout
        ]
    
    def cleanup_inactive_sessions(self, timeout=1800):
        """
        Remove inactive sessions exceeding the timeout.
        
        Args:
            timeout (int): Timeout in seconds
            
        Returns:
            int: Number of sessions removed
        """
        inactive_sessions = self.get_inactive_sessions(timeout)
        for session_id in inactive_sessions:
            self.remove_session(session_id)
        
        if inactive_sessions:
            logger.info(f"Cleaned up {len(inactive_sessions)} inactive sessions")
        
        return len(inactive_sessions)