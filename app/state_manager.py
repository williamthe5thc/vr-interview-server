"""
Manages interview session states and provides session management functionality.
"""

import time
import logging
import threading
from flask_socketio import SocketIO

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
        return self.active_sessions.get(session_id)
    
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
        
        # Log state transition
        logger.info(f"Session {session_id} state change: {session.state} -> {new_state}")
        
        # Update session state
        old_state = session.state
        session.state = new_state
        session.last_activity = time.time()
        
        # Send state update to client - using the queue_emit function for thread safety
        if hasattr(self, 'socketio') and self.socketio:
            try:
                # Import here to avoid circular imports
                from app.websocket import queue_emit
                
                # Queue the state update for emission by the main thread
                queue_emit('state_update', {
                    'session_id': session_id,
                    'state': new_state,
                    'turn': session.turn_index,
                    'previous_state': old_state
                }, room=session_id)
                
                # Also emit directly to the client if available
                if session.client_id:
                    queue_emit('state_update', {
                        'session_id': session_id,
                        'state': new_state,
                        'turn': session.turn_index,
                        'previous_state': old_state
                    }, to=session.client_id)
                
            except ImportError:
                # If queue_emit is not available (e.g., during initialization),
                # fall back to direct emit
                self.socketio.emit('state_update', {
                    'session_id': session_id,
                    'state': new_state,
                    'turn': session.turn_index,
                    'previous_state': old_state
                }, room=session_id)
                
                logger.warning("Using direct emit for state update (queue_emit unavailable)")
                
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