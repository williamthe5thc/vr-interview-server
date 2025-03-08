"""
Speech processing services including speech-to-text and text-to-speech functionality.
"""

import os
import time
import logging
import subprocess
import tempfile
from pathlib import Path
import whisper
import torch

logger = logging.getLogger("interview-server")

# Initialize whisper model lazily
_whisper_model = None

def _get_whisper_model(model_name="base"):
    """
    Get or initialize the Whisper model.
    
    Args:
        model_name (str): Whisper model name ("tiny", "base", "small", "medium", "large")
        
    Returns:
        whisper.Whisper: The Whisper model
    """
    global _whisper_model
    
    if _whisper_model is None:
        logger.info(f"Loading Whisper model: {model_name}")
        try:
            _whisper_model = whisper.load_model(model_name)
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading Whisper model: {e}")
            raise
    
    return _whisper_model

def transcribe_audio(audio_path, language="en", model_name="base"):
    """
    Transcribe audio file to text using Whisper.
    
    Args:
        audio_path (str): Path to audio file
        language (str, optional): Language code. Defaults to "en".
        model_name (str, optional): Whisper model name. Defaults to "base".
        
    Returns:
        str: Transcribed text, or None if failed
    """
    try:
        # Check if file exists
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return None
        
        # Get the model
        model = _get_whisper_model(model_name)
        
        # Log start time to measure performance
        start_time = time.time()
        
        # Perform transcription
        result = model.transcribe(
            audio_path, 
            language=language,
            fp16=torch.cuda.is_available()  # Use FP16 if CUDA available
        )
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        logger.info(f"Transcription completed in {elapsed_time:.2f} seconds")
        
        # Extract text
        transcription = result.get("text", "").strip()
        
        if not transcription:
            logger.warning(f"Empty transcription for audio: {audio_path}")
        
        return transcription
        
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return None

def generate_speech(text, output_path, config=None):
    """
    Convert text to speech.
    
    Args:
        text (str): Text to convert to speech
        output_path (str): Path to save audio file
        config (dict, optional): Configuration settings
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not text:
        logger.error("Empty text provided for speech generation")
        return False
        
    # Default to gTTS if no config provided
    if config is None:
        config = {'audio': {'tts_engine': 'gTTS'}}
    
    # Get TTS engine from config
    tts_engine = config.get('audio', {}).get('tts_engine', 'gTTS')
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if tts_engine.lower() == 'alltalk':
            return _generate_speech_alltalk(text, output_path, config)
        else:
            return _generate_speech_gtts(text, output_path)
            
    except Exception as e:
        logger.error(f"Error generating speech with {tts_engine}: {e}")
        
        # Try fallback if primary method fails
        if tts_engine.lower() != 'gtts':
            logger.info("Trying fallback to gTTS")
            try:
                return _generate_speech_gtts(text, output_path)
            except Exception as fallback_error:
                logger.error(f"Fallback TTS also failed: {fallback_error}")
        
        return False

def _generate_speech_alltalk(text, output_path, config):
    """
    Generate speech using AllTalk.
    
    Args:
        text (str): Text to convert to speech
        output_path (str): Path to save audio file
        config (dict): Configuration settings
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Get AllTalk path from config
    alltalk_path = config.get('audio', {}).get('alltalk_path', 'D:\\AllTalk')
    
    # Check if path exists
    if not os.path.exists(alltalk_path):
        logger.error(f"AllTalk path not found: {alltalk_path}")
        return False
    
    # AllTalk script path
    alltalk_script = os.path.join(alltalk_path, "generate.py")
    
    # Check if script exists
    if not os.path.exists(alltalk_script):
        logger.error(f"AllTalk script not found: {alltalk_script}")
        return False
    
    # Create temporary text file for input
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
        temp_file.write(text)
        temp_file_path = temp_file.name
    
    try:
        # Prepare AllTalk command
        alltalk_cmd = [
            "python", 
            alltalk_script,
            "--text", text,
            "--output", output_path,
            "--voice", "female_narrator",  # Adjust voice as needed
            "--language", "en"
        ]
        
        # Run AllTalk
        logger.info(f"Running AllTalk command: {' '.join(alltalk_cmd)}")
        result = subprocess.run(alltalk_cmd, check=True, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                text=True)
        
        # Check if output file was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"AllTalk speech generated successfully: {output_path}")
            return True
        else:
            logger.error(f"AllTalk failed to generate speech file: {result.stderr}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"AllTalk process error: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error running AllTalk: {e}")
        return False
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

def _generate_speech_gtts(text, output_path):
    """
    Generate speech using Google Text-to-Speech (gTTS).
    
    Args:
        text (str): Text to convert to speech
        output_path (str): Path to save audio file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from gtts import gTTS
        
        # Generate speech
        tts = gTTS(text=text, lang='en', slow=False)
        
        # Save to file
        tts.save(output_path)
        
        # Check if file was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"gTTS speech generated successfully: {output_path}")
            return True
        else:
            logger.error("gTTS failed to generate speech file")
            return False
            
    except Exception as e:
        logger.error(f"Error generating speech with gTTS: {e}")
        return False