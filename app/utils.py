"""
Utility functions for the VR Interview Server.
Includes helper functions for session management, audio processing, etc.
"""

import os
import time
import logging
import threading
import wave
import array
import numpy as np
from datetime import datetime, timedelta

# Import state manager
from app.state_manager import InterviewStateManager

logger = logging.getLogger("interview-server")
state_manager = InterviewStateManager()

def cleanup_inactive_sessions(timeout=1800):
    """
    Periodically clean up inactive sessions.
    This function runs in a separate thread.
    
    Args:
        timeout (int): Session timeout in seconds (default: 1800 = 30 minutes)
    """
    while True:
        try:
            # Sleep first to allow the server to start up
            time.sleep(300)  # Run every 5 minutes
            
            # Clean up inactive sessions
            removed_count = state_manager.cleanup_inactive_sessions(timeout)
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} inactive sessions")
        
        except Exception as e:
            logger.error(f"Error in cleanup_inactive_sessions: {e}")

def convert_audio_format(input_path, output_path, target_sample_rate=16000):
    """
    Convert audio file format (resampling, etc.).
    Useful for preparing audio for specific models.
    
    Args:
        input_path (str): Path to input audio file
        output_path (str): Path to output audio file
        target_sample_rate (int): Target sample rate
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Open input file
        with wave.open(input_path, 'rb') as wf:
            # Get parameters
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            
            # Read all frames
            frames = wf.readframes(n_frames)
        
        # Convert to numpy array
        if sample_width == 2:
            data = np.frombuffer(frames, dtype=np.int16)
        elif sample_width == 4:
            data = np.frombuffer(frames, dtype=np.int32)
        else:
            logger.error(f"Unsupported sample width: {sample_width}")
            return False
        
        # Reshape for multiple channels
        if n_channels > 1:
            data = data.reshape(-1, n_channels)
            # Convert to mono by averaging channels
            data = data.mean(axis=1).astype(data.dtype)
        
        # Resample if necessary
        if sample_rate != target_sample_rate:
            # Simple resampling - for better results, use a library like librosa
            duration = n_frames / sample_rate
            target_n_frames = int(duration * target_sample_rate)
            indices = np.linspace(0, len(data) - 1, target_n_frames).astype(int)
            data = data[indices]
        
        # Write output file
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(target_sample_rate)
            wf.writeframes(data.tobytes())
        
        logger.info(f"Converted audio: {input_path} -> {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error converting audio format: {e}")
        return False

def generate_session_stats(session_id):
    """
    Generate statistics for a session.
    
    Args:
        session_id (str): The session ID
        
    Returns:
        dict: Session statistics
    """
    try:
        session = state_manager.get_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        # Calculate statistics
        total_messages = len(session.conversation_history)
        user_messages = sum(1 for msg in session.conversation_history if msg["speaker"] == "user")
        interviewer_messages = total_messages - user_messages
        
        # Calculate average message length
        user_msg_lengths = [len(msg["text"]) for msg in session.conversation_history if msg["speaker"] == "user"]
        interviewer_msg_lengths = [len(msg["text"]) for msg in session.conversation_history if msg["speaker"] == "interviewer"]
        
        avg_user_length = sum(user_msg_lengths) / len(user_msg_lengths) if user_msg_lengths else 0
        avg_interviewer_length = sum(interviewer_msg_lengths) / len(interviewer_msg_lengths) if interviewer_msg_lengths else 0
        
        # Calculate session duration
        if session.conversation_history:
            start_time = session.conversation_history[0]["timestamp"]
            end_time = session.conversation_history[-1]["timestamp"]
            duration_seconds = end_time - start_time
            duration = str(timedelta(seconds=int(duration_seconds)))
        else:
            duration = "0:00:00"
        
        # Return stats
        return {
            "session_id": session_id,
            "position": session.position,
            "difficulty": session.difficulty,
            "interviewer_type": session.interviewer_type,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "interviewer_messages": interviewer_messages,
            "avg_user_message_length": avg_user_length,
            "avg_interviewer_message_length": avg_interviewer_length,
            "duration": duration,
            "turns_completed": session.turn_index
        }
        
    except Exception as e:
        logger.error(f"Error generating session stats: {e}")
        return {"error": str(e)}

def ensure_directories():
    """
    Ensure that all required directories exist.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from flask import current_app
        
        # Get directory paths from app config
        paths = [
            current_app.config.get('UPLOAD_FOLDER', 'data/audio/uploads'),
            current_app.config.get('RESPONSE_FOLDER', 'data/audio/responses'),
            current_app.config.get('CONVERSATION_FOLDER', 'data/conversations')
        ]
        
        # Create directories
        for path in paths:
            os.makedirs(path, exist_ok=True)
            logger.info(f"Ensured directory exists: {path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error ensuring directories: {e}")
        return False