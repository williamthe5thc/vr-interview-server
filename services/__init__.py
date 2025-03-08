"""
Services package initialization.
This package contains external service integrations for the VR Interview Server.
"""

# Import services for easy access
from services.speech_processing import transcribe_audio, generate_speech
from services.llm_service import generate_llm_response

__all__ = [
    'transcribe_audio',
    'generate_speech',
    'generate_llm_response'
]