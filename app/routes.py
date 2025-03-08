"""
HTTP routes for the VR Interview Server.
Primarily used for serving static files like audio responses.
"""

import os
import json
import logging
from flask import send_from_directory, jsonify, current_app, request, Response

# Import state manager
from app.state_manager import InterviewStateManager

logger = logging.getLogger("interview-server")
state_manager = InterviewStateManager()

def register_routes(app):
    """Register HTTP routes with the Flask app."""
    
    @app.route('/')
    def index():
        """Server info endpoint."""
        return jsonify({
            "name": "VR Interview Practice Server",
            "status": "running",
            "active_sessions": len(state_manager.get_active_sessions()),
            "websocket_url": f"ws://{request.host}"
        })
    
    @app.route('/responses/<path:filename>')
    def serve_response(filename):
        """
        Serve audio response files.
        
        Args:
            filename (str): The filename to serve
            
        Returns:
            Response: The audio file
        """
        try:
            return send_from_directory(current_app.config['RESPONSE_FOLDER'], filename)
        except Exception as e:
            logger.error(f"Error serving response file {filename}: {e}")
            return "File not found", 404
    
    @app.route('/status')
    def server_status():
        """
        Get server status information.
        
        Returns:
            Response: Server status in JSON format
        """
        try:
            active_sessions = state_manager.get_active_sessions()
            
            # Collect basic stats
            status_data = {
                "status": "running",
                "active_sessions": len(active_sessions),
                "session_details": [session.to_dict() for session in active_sessions]
            }
            
            return jsonify(status_data)
            
        except Exception as e:
            logger.error(f"Error getting server status: {e}")
            return jsonify({"status": "error", "message": str(e)})
    
    @app.route('/session/<session_id>/history')
    def session_history(session_id):
        """
        Get conversation history for a session.
        
        Args:
            session_id (str): The session ID
            
        Returns:
            Response: Conversation history in JSON format
        """
        try:
            session = state_manager.get_session(session_id)
            if not session:
                return jsonify({"error": "Session not found"}), 404
            
            return jsonify({
                "session_id": session_id,
                "position": session.position,
                "turn_index": session.turn_index,
                "history": session.conversation_history
            })
            
        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/session/<session_id>/save', methods=['POST'])
    def save_session(session_id):
        """
        Save session conversation history to a file.
        
        Args:
            session_id (str): The session ID
            
        Returns:
            Response: Success or error message
        """
        try:
            session = state_manager.get_session(session_id)
            if not session:
                return jsonify({"error": "Session not found"}), 404
            
            # Generate filename based on session ID and timestamp
            filename = f"{session_id}_{int(session.last_activity)}.json"
            filepath = os.path.join(current_app.config['CONVERSATION_FOLDER'], filename)
            
            # Save conversation
            success = session.save_conversation(filepath)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": "Conversation saved successfully",
                    "filename": filename
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Failed to save conversation"
                }), 500
                
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/health')
    def health_check():
        """
        Health check endpoint.
        
        Returns:
            Response: Health status
        """
        return jsonify({"status": "healthy"})
    
    # Register error handlers
    
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404
    
    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}")
        return jsonify({"error": "Internal server error"}), 500