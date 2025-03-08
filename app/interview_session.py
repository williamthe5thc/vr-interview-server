"""
Interview session data model and management.
Stores session state, conversation history, and audio handling.
"""

import os
import time
import json
import wave
import array
import struct
import logging
from datetime import datetime

logger = logging.getLogger("interview-server")

class InterviewSession:
    """
    Represents an interview session with a candidate.
    
    Stores the state, conversation history, and handles audio data
    for a specific interview session.
    """
    
    def __init__(self, session_id, client_id=None, position="Software Engineer", 
                 difficulty=0.5, interviewer_type="professional"):
        """
        Initialize a new interview session.
        
        Args:
            session_id (str): Unique identifier for the session
            client_id (str, optional): Client identifier. Defaults to None.
            position (str, optional): Job position. Defaults to "Software Engineer".
            difficulty (float, optional): Interview difficulty (0.0-1.0). Defaults to 0.5.
            interviewer_type (str, optional): Type of interviewer. Defaults to "professional".
        """
        self.session_id = session_id
        self.client_id = client_id
        self.position = position
        self.difficulty = difficulty
        self.interviewer_type = interviewer_type
        
        # State information
        self.state = "idle"  # Initial state
        self.active = True
        self.created_at = time.time()
        self.last_activity = time.time()
        self.turn_index = 0
        
        # Conversation history
        self.conversation_history = []
        
        # Audio buffer for handling streaming audio
        self.audio_buffer = bytearray()
        self.audio_format = {
            'channels': 1,
            'sample_width': 2,  # 16-bit audio
            'sample_rate': 44100
        }
        
        logger.info(f"Created new interview session: {session_id}")
    
    def add_message(self, speaker, text):
        """
        Add a message to the conversation history.
        
        Args:
            speaker (str): Either "user" or "interviewer"
            text (str): The message text
        """
        self.conversation_history.append({
            "speaker": speaker,
            "text": text,
            "timestamp": time.time()
        })
        self.last_activity = time.time()
    
    def get_formatted_history(self, max_turns=10):
        """
        Get a formatted string representation of the conversation history.
        
        Args:
            max_turns (int, optional): Maximum number of turns to include. Defaults to 10.
            
        Returns:
            str: Formatted conversation history
        """
        # Take the most recent turns (up to max_turns)
        recent_history = self.conversation_history[-max_turns*2:] if self.conversation_history else []
        
        formatted = ""
        for entry in recent_history:
            speaker_label = "Candidate" if entry["speaker"] == "user" else "Interviewer"
            formatted += f"{speaker_label}: {entry['text']}\n"
        
        return formatted
    
    def add_audio_chunk(self, audio_bytes):
        """
        Add an audio chunk to the buffer.
        
        Args:
            audio_bytes (bytes): Audio data to add
        """
        self.audio_buffer.extend(audio_bytes)
    
    def clear_audio_buffer(self):
        """Clear the audio buffer."""
        self.audio_buffer = bytearray()
    
    def save_audio_buffer(self, filepath):
        """
        Save the audio buffer to a WAV file.
        
        Args:
            filepath (str): Path where the WAV file should be saved
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Create WAV file
            with wave.open(filepath, 'wb') as wav_file:
                wav_file.setnchannels(self.audio_format['channels'])
                wav_file.setsampwidth(self.audio_format['sample_width'])
                wav_file.setframerate(self.audio_format['sample_rate'])
                wav_file.writeframes(self.audio_buffer)
            
            logger.info(f"Saved audio to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving audio buffer: {e}")
            return False
    
    def save_conversation(self, filepath):
        """
        Save the conversation history to a JSON file.
        
        Args:
            filepath (str): Path where the JSON file should be saved
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Create conversation data
            conversation_data = {
                "session_id": self.session_id,
                "position": self.position,
                "difficulty": self.difficulty,
                "interviewer_type": self.interviewer_type,
                "created_at": self.created_at,
                "last_activity": self.last_activity,
                "turn_count": self.turn_index,
                "history": self.conversation_history
            }
            
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(conversation_data, f, indent=2)
            
            logger.info(f"Saved conversation to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return False
    
    def to_dict(self):
        """
        Convert the session to a dictionary.
        
        Returns:
            dict: Dictionary representation of the session
        """
        return {
            "session_id": self.session_id,
            "client_id": self.client_id,
            "state": self.state,
            "active": self.active,
            "position": self.position,
            "difficulty": self.difficulty,
            "interviewer_type": self.interviewer_type,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "turn_index": self.turn_index,
            "message_count": len(self.conversation_history)
        }