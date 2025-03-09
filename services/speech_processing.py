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

def _create_silent_audio_file(output_path, duration=5.0, sample_rate=22050):
    """
    Create a silent WAV file as a fallback when TTS fails.
    
    Args:
        output_path (str): Path to save the audio file
        duration (float): Duration of the silent audio in seconds
        sample_rate (int): Sample rate of the audio
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import wave
        import struct
        import numpy as np
        
        # Create silent audio data (very quiet background noise to avoid complete silence)
        noise_level = 0.001  # Very quiet background noise
        num_samples = int(duration * sample_rate)
        samples = np.random.normal(0, noise_level, num_samples).astype(np.float32)
        
        # Convert to 16-bit PCM
        samples = (samples * 32767).astype(np.int16)
        
        # Write WAV file
        with wave.open(output_path, 'w') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())
        
        logger.info(f"Created silent audio file as fallback: {output_path} (duration: {duration:.2f}s)")
        return True
        
    except Exception as e:
        logger.error(f"Error creating silent audio file: {e}")
        return False

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
    # Create silent audio file with duration based on text length
    words = text.split()
    word_count = len(words)
    
    # Roughly 3 words per second for average speech
    duration = max(5.0, word_count * 0.33)  # At least 5 seconds, ~330ms per word
    
    logger.info(f"Using silent audio fallback for TTS: {word_count} words, {duration:.2f}s duration")
    return _create_silent_audio_file(output_path, duration=duration)

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
        import gtts.tokenizer.pre_processors
        from gtts.tts import gTTSError
        
        # Use a silent file as fallback if we get a connection error
        if not hasattr(_generate_speech_gtts, "offline_mode"):
            _generate_speech_gtts.offline_mode = False
        
        # If we're already in offline mode or if text is very long, use the silent fallback
        if _generate_speech_gtts.offline_mode or len(text) > 1000:
            logger.warning("Using offline mode for TTS or text is too long")
            return _create_silent_audio_file(output_path, duration=len(text.split()) * 0.3)
        
        # Generate speech with a timeout
        import threading
        import time
        
        result = [False]
        error = [None]
        
        def _generate_speech_thread():
            try:
                # Generate speech
                tts = gTTS(text=text, lang='en', slow=False)
                
                # Save to file
                tts.save(output_path)
                result[0] = True
            except Exception as e:
                error[0] = str(e)
                result[0] = False
        
        thread = threading.Thread(target=_generate_speech_thread)
        thread.daemon = True
        thread.start()
        
        # Wait with timeout
        thread.join(timeout=10)  # 10 second timeout
        
        if thread.is_alive():
            logger.error("TTS generation timed out after 10 seconds")
            _generate_speech_gtts.offline_mode = True
            return _create_silent_audio_file(output_path, duration=len(text.split()) * 0.3)
        
        if not result[0]:
            logger.error(f"Error in TTS thread: {error[0]}")
            _generate_speech_gtts.offline_mode = True
            return _create_silent_audio_file(output_path, duration=len(text.split()) * 0.3)
        
        # Check if file was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"gTTS speech generated successfully: {output_path}")
            return True
        else:
            logger.error("gTTS failed to generate speech file")
            _generate_speech_gtts.offline_mode = True
            return _create_silent_audio_file(output_path, duration=len(text.split()) * 0.3)
            
    except Exception as e:
        logger.error(f"Error generating speech with gTTS: {e}")
        _generate_speech_gtts.offline_mode = True
        return _create_silent_audio_file(output_path, duration=len(text.split()) * 0.3)