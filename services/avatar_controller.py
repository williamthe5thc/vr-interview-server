"""
Avatar controller service for generating interviewer animations.
This is optional and can be extended later for more sophisticated avatar control.
"""

import os
import time
import json
import logging
import random
from collections import defaultdict

logger = logging.getLogger("interview-server")

class AvatarController:
    """
    Controls the interviewer avatar animations and behaviors.
    
    Can be extended with more sophisticated animation control logic,
    particularly when integrating with a Unity-based avatar system.
    """
    
    # Animation types
    ANIM_IDLE = "idle"
    ANIM_TALKING = "talking"
    ANIM_LISTENING = "listening"
    ANIM_THINKING = "thinking"
    ANIM_GESTURE = "gesture"
    
    # Gesture types
    GESTURE_NOD = "nod"
    GESTURE_SHAKE = "shake"
    GESTURE_HAND = "hand_gesture"
    GESTURE_LEAN = "lean"
    
    def __init__(self, interviewer_type="professional"):
        """
        Initialize the avatar controller.
        
        Args:
            interviewer_type (str, optional): Type of interviewer. Defaults to "professional".
        """
        self.interviewer_type = interviewer_type
        self.current_animation = self.ANIM_IDLE
        self.last_gesture_time = 0
        self.gesture_probability = 0.3  # Probability of making a gesture while talking
        
        # Animation parameters for different interviewer types
        self.animation_params = {
            "professional": {
                "gesture_frequency": 0.3,
                "gesture_types": [self.GESTURE_NOD, self.GESTURE_HAND],
                "blink_rate": 0.2,
                "posture": "upright"
            },
            "technical": {
                "gesture_frequency": 0.2,
                "gesture_types": [self.GESTURE_HAND],
                "blink_rate": 0.15,
                "posture": "slight_lean"
            },
            "behavioral": {
                "gesture_frequency": 0.4,
                "gesture_types": [self.GESTURE_NOD, self.GESTURE_HAND, self.GESTURE_LEAN],
                "blink_rate": 0.25,
                "posture": "engaged"
            },
            "stress": {
                "gesture_frequency": 0.15,
                "gesture_types": [self.GESTURE_SHAKE, self.GESTURE_LEAN],
                "blink_rate": 0.1,
                "posture": "authoritative"
            }
        }
        
        # Default to professional if type not found
        if interviewer_type not in self.animation_params:
            self.interviewer_type = "professional"
        
        logger.info(f"Avatar Controller initialized with interviewer type: {self.interviewer_type}")
    
    def set_interviewer_type(self, interviewer_type):
        """
        Set the interviewer type.
        
        Args:
            interviewer_type (str): Type of interviewer
            
        Returns:
            bool: True if successful, False otherwise
        """
        if interviewer_type in self.animation_params:
            self.interviewer_type = interviewer_type
            logger.info(f"Interviewer type changed to: {interviewer_type}")
            return True
        else:
            logger.warning(f"Unknown interviewer type: {interviewer_type}")
            return False
    
    def get_animation_state(self, session_state, is_speaking=False):
        """
        Get the current animation state based on session state.
        
        Args:
            session_state (str): Current session state
            is_speaking (bool, optional): Whether the interviewer is speaking. Defaults to False.
            
        Returns:
            dict: Animation state parameters
        """
        animation_state = {
            "animation": self.ANIM_IDLE,
            "gesture": None,
            "intensity": 0.5,
            "posture": self.animation_params[self.interviewer_type]["posture"]
        }
        
        # Map session state to animation state
        if session_state == "idle" or session_state == "waiting":
            animation_state["animation"] = self.ANIM_IDLE
            
        elif session_state == "listening":
            animation_state["animation"] = self.ANIM_LISTENING
            
            # Occasionally nod while listening
            if random.random() < 0.1:
                animation_state["gesture"] = self.GESTURE_NOD
                
        elif session_state == "processing":
            animation_state["animation"] = self.ANIM_THINKING
            
        elif session_state == "responding":
            animation_state["animation"] = self.ANIM_TALKING
            
            # Add random gestures while talking
            if is_speaking and random.random() < self.animation_params[self.interviewer_type]["gesture_frequency"]:
                # Choose a random gesture from the allowed types
                gesture_types = self.animation_params[self.interviewer_type]["gesture_types"]
                animation_state["gesture"] = random.choice(gesture_types)
        
        # Add intensity variations based on interviewer type
        if self.interviewer_type == "stress":
            animation_state["intensity"] = 0.7
        elif self.interviewer_type == "behavioral":
            animation_state["intensity"] = 0.6
        
        return animation_state
    
    def generate_viseme_data(self, text, duration):
        """
        Generate lip sync data (visemes) for the given text.
        This is a placeholder implementation - in a real system,
        you would use a proper lip sync algorithm.
        
        Args:
            text (str): Text being spoken
            duration (float): Duration of the audio in seconds
            
        Returns:
            list: List of viseme keyframes
        """
        # Simple placeholder implementation
        # In a real system, you'd use a proper lip sync algorithm
        
        # Create a list of word durations (approx 0.3s per word)
        words = text.split()
        total_words = len(words)
        
        # Simple model: distribute visemes evenly throughout the duration
        visemes = []
        time_per_word = duration / max(total_words, 1)
        
        for i, word in enumerate(words):
            # Calculate start time for this word
            start_time = i * time_per_word
            
            # Simple viseme sequence for each word (open, wide, close)
            visemes.append({
                "time": start_time,
                "viseme": "rest",
                "weight": 0.2
            })
            
            visemes.append({
                "time": start_time + (time_per_word * 0.3),
                "viseme": "wide",
                "weight": 0.8
            })
            
            visemes.append({
                "time": start_time + (time_per_word * 0.7),
                "viseme": "close",
                "weight": 0.5
            })
        
        # Add final rest state
        visemes.append({
            "time": duration,
            "viseme": "rest",
            "weight": 0.0
        })
        
        return visemes
    
    def generate_animation_data(self, session_state, text=None, duration=None):
        """
        Generate animation data for the current state.
        
        Args:
            session_state (str): Current session state
            text (str, optional): Text being spoken (if responding). Defaults to None.
            duration (float, optional): Duration of the audio in seconds. Defaults to None.
            
        Returns:
            dict: Animation data
        """
        # Get base animation state
        is_speaking = session_state == "responding" and text is not None
        animation_state = self.get_animation_state(session_state, is_speaking)
        
        # Generate viseme data if speaking
        visemes = None
        if is_speaking and text and duration:
            visemes = self.generate_viseme_data(text, duration)
        
        # Generate blink events
        blinks = []
        if duration:
            blink_interval = 1.0 / self.animation_params[self.interviewer_type]["blink_rate"]
            time_pos = random.uniform(0.5, 2.0)  # Start with a random offset
            
            while time_pos < duration:
                blinks.append({
                    "time": time_pos,
                    "duration": random.uniform(0.1, 0.2)
                })
                time_pos += random.uniform(blink_interval * 0.5, blink_interval * 1.5)
        
        # Complete animation data
        animation_data = {
            "state": animation_state["animation"],
            "gesture": animation_state["gesture"],
            "intensity": animation_state["intensity"],
            "posture": animation_state["posture"],
            "visemes": visemes,
            "blinks": blinks,
            "duration": duration
        }
        
        return animation_data
    
    def generate_idle_variations(self, duration):
        """
        Generate idle animation variations to avoid a static appearance.
        
        Args:
            duration (float): Duration in seconds
            
        Returns:
            list: List of idle animation events
        """
        idle_events = []
        
        # Small head movements
        num_movements = int(duration / 5)  # Approx one movement every 5 seconds
        for i in range(num_movements):
            time_pos = random.uniform(i * 5, (i + 1) * 5)
            idle_events.append({
                "time": time_pos,
                "type": "head_movement",
                "params": {
                    "direction": random.choice(["left", "right", "up", "down"]),
                    "amount": random.uniform(0.1, 0.3)
                }
            })
        
        # Small posture adjustments
        num_adjustments = int(duration / 10)  # Approx one adjustment every 10 seconds
        for i in range(num_adjustments):
            time_pos = random.uniform(i * 10, (i + 1) * 10)
            idle_events.append({
                "time": time_pos,
                "type": "posture_adjust",
                "params": {
                    "direction": random.choice(["forward", "backward", "shift"]),
                    "amount": random.uniform(0.1, 0.2)
                }
            })
        
        return idle_events