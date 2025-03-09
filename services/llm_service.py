def _clean_response(response_text):
    """
    Clean the response from LLM to remove instruction tokens and take only the first response.
    
    Args:
        response_text (str): Raw response from the LLM
        
    Returns:
        str: Cleaned response text
    """
    # Log the raw response for debugging
    logger.info(f"Raw LLM response: {response_text[:100]}...")
    
    # If response is just <s> or empty, return a default response
    if not response_text or response_text.strip() in ["<s>", ""]:
        logger.warning("Empty or minimal response received from LLM, using fallback response")
        return "Thank you for that information. Can you tell me more about your experience with this kind of work?"
    
    # Remove <s> token if present
    if response_text.startswith("<s>"):
        response_text = response_text[3:].strip()
    
    # Remove any "Respond as the interviewer: [/INST]" text
    if "Respond as the interviewer: [/INST]" in response_text:
        response_text = response_text.split("Respond as the interviewer: [/INST]", 1)[1].strip()
    
    # Remove any "Candidate: " prefixes that might be in the response
    if response_text.startswith("Candidate:"):
        response_text = response_text.split("\n", 1)[1].strip() if "\n" in response_text else ""
    
    # Remove instruction tokens like "[INST]" that might be left
    response_text = response_text.replace("[INST]", "").replace("[/INST]", "")
    
    # If there are multiple lines with "Interviewer:" or "Candidate:", take only until the next "Candidate:"
    if "Candidate:" in response_text:
        response_text = response_text.split("Candidate:")[0].strip()
    
    # If the response has "Interviewer:" prefix, extract just that part
    if "Interviewer:" in response_text:
        parts = response_text.split("Interviewer:", 1)
        if len(parts) > 1:
            response_text = parts[1].strip()
    
    # Clean up any trailing instruction-like text
    if "Respond as the" in response_text:
        response_text = response_text.split("Respond as the")[0].strip()
        
    # Final safety check - make sure we have some text
    if not response_text.strip():
        logger.warning("Clean response is empty, using fallback response")
        return "Thanks for sharing that information. Could you tell me more about your specific experience with those technologies?"
    
    logger.info(f"Cleaned response: {response_text[:100]}...")
    return response_text.strip()

"""
LLM service for generating interviewer responses.
Handles model loading, prompt formatting, and response generation.
"""

import os
import time
import json
import logging
import functools
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from collections import OrderedDict

logger = logging.getLogger("interview-server")

# Cache for LLM responses
response_cache = OrderedDict()
CACHE_SIZE = 200  # Maximum number of cached responses

# Lazy-loaded models
_model = None
_tokenizer = None

def _get_model_and_tokenizer(model_path):
    """
    Get or initialize the LLM model and tokenizer.
    
    Args:
        model_path (str): Path to the model
        
    Returns:
        tuple: (model, tokenizer)
    """
    global _model, _tokenizer
    
    if _model is None or _tokenizer is None:
        logger.info(f"Loading LLM model from {model_path}")
        try:
            # Load tokenizer
            _tokenizer = AutoTokenizer.from_pretrained(model_path)
            
            # Load model
            _model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype="auto",
                trust_remote_code=True,
                device_map="auto"  # Will use CUDA if available
            )
            
            logger.info(f"LLM model loaded successfully: {model_path}")
            
            # Log device information
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                logger.info(f"Using GPU: {device_name}")
            else:
                logger.warning("CUDA not available, using CPU (this will be slow)")
                
        except Exception as e:
            logger.error(f"Error loading LLM model: {e}")
            raise
    
    return _model, _tokenizer

def _build_prompt(user_input, conversation_history, personality_prompt, position, difficulty):
    """
    Build a prompt for the LLM.
    
    Args:
        user_input (str): The user's input text
        conversation_history (str): The conversation history
        personality_prompt (str): The interviewer personality prompt
        position (str): The job position
        difficulty (float): The interview difficulty (0.0-1.0)
        
    Returns:
        str: The formatted prompt
    """
    # Add difficulty modifier to personality prompt
    difficulty_modifier = ""
    if difficulty > 0.7:
        difficulty_modifier = "\nAsk challenging follow-up questions and dig deeper into responses."
    elif difficulty < 0.4:
        difficulty_modifier = "\nBe supportive and helpful, providing guidance if the candidate struggles."
    
    # Format the prompt for Phi-2 style - note that Phi-2 uses a particular format
    # The crucial part is to end the user's most recent message and add "Interviewer:" as a prompt
    # We wrap the entire conversation in a chat context
    
    # Add user's most recent input to conversation history if not already there
    recent_input_prompt = f"\nCandidate: {user_input}\nInterviewer:"
    
    # Format the prompt specifically for Phi-2
    prompt = f"""<s>You are an AI assistant that helps with job interviews.
    
    {personality_prompt}
    You're conducting an interview for a {position} position.{difficulty_modifier}
    
    Previous conversation:
    {conversation_history}{recent_input_prompt}"""
    
    logger.info(f"Prompt format: {prompt[:200]}...")
    
    return prompt

def _add_to_cache(key, value):
    """
    Add a response to the cache with LRU eviction.
    
    Args:
        key (str): Cache key
        value (str): Response text
    """
    global response_cache, CACHE_SIZE
    
    # Add to cache
    response_cache[key] = value
    
    # Evict oldest items if cache is too large
    while len(response_cache) > CACHE_SIZE:
        response_cache.popitem(last=False)

def _get_cache_key(user_input, position, interviewer_type, difficulty):
    """
    Generate a cache key from the input parameters.
    
    Args:
        user_input (str): The user's input text
        position (str): The job position
        interviewer_type (str): The interviewer type
        difficulty (float): The interview difficulty
        
    Returns:
        str: The cache key
    """
    # Normalize inputs for better cache hits
    normalized_input = user_input.lower().strip()
    normalized_position = position.lower().strip()
    
    # Create cache key
    return f"{interviewer_type}:{normalized_position}:{difficulty:.1f}:{normalized_input}"

def generate_llm_response(user_input, conversation_history, personality_prompt, 
                         position="Software Engineer", difficulty=0.5, config=None):
    """
    Generate a response from the LLM.
    
    Args:
        user_input (str): The user's input text
        conversation_history (str): The conversation history
        personality_prompt (str): The interviewer personality prompt
        position (str, optional): The job position. Defaults to "Software Engineer".
        difficulty (float, optional): The interview difficulty (0.0-1.0). Defaults to 0.5.
        config (dict, optional): Configuration settings. Defaults to None.
        
    Returns:
        str: Generated response text, or None if failed
    """
    if not user_input:
        logger.error("Empty user input provided for LLM")
        return None
    
    # Default config if none provided
    if config is None:
        config = {
            'llm': {
                'model_path': './phi-model',
                'temperature': 0.7,
                'max_tokens': 75,
                'top_p': 0.95,
                'response_cache_size': 200
            }
        }
    
    # Get cache size from config
    global CACHE_SIZE
    CACHE_SIZE = config.get('llm', {}).get('response_cache_size', 200)
    
    # Get model path from config
    model_path = config.get('llm', {}).get('model_path', './phi-model')
    
    # Get LLM generation parameters
    temperature = float(config.get('llm', {}).get('temperature', 0.7))
    max_tokens = int(config.get('llm', {}).get('max_tokens', 75))
    top_p = float(config.get('llm', {}).get('top_p', 0.95))
    
    # Generate cache key
    cache_key = _get_cache_key(user_input, position, personality_prompt[:20], difficulty)
    
    # Check cache
    if cache_key in response_cache:
        logger.info(f"Using cached response for input: {user_input[:50]}...")
        return response_cache[cache_key]
    
    try:
        # Build the prompt
        prompt = _build_prompt(
            user_input=user_input,
            conversation_history=conversation_history,
            personality_prompt=personality_prompt,
            position=position,
            difficulty=difficulty
        )
        
        # Get model and tokenizer
        model, tokenizer = _get_model_and_tokenizer(model_path)
        
        # Log start time for performance monitoring
        start_time = time.time()
        
        # Tokenize input
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        # Generate response
        with torch.no_grad():
            try:
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    do_sample=True,
                    top_p=top_p,
                    pad_token_id=tokenizer.eos_token_id  # Explicitly set pad token
                )
            except Exception as generate_error:
                logger.error(f"Error during LLM generation: {generate_error}")
                # Fallback to a simpler generation method
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=0.5,  # Lower temperature for more deterministic output
                    do_sample=False,   # Greedy decoding
                    num_beams=1       # No beam search
                )
        
        # Decode response
        full_response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        
        # Clean up the response - remove instruction tokens and get first interviewer response
        response_text = _clean_response(full_response)
        
        # Log generation time
        elapsed_time = time.time() - start_time
        logger.info(f"LLM response generated in {elapsed_time:.2f} seconds")
        
        # Cache the response
        _add_to_cache(cache_key, response_text)
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error generating LLM response: {e}")
        return None

def format_conversation_for_llm(messages, max_history=10):
    """
    Format a list of conversation messages for LLM input.
    
    Args:
        messages (list): List of message dictionaries with 'speaker' and 'text' keys
        max_history (int): Maximum number of messages to include
        
    Returns:
        str: Formatted conversation history
    """
    # Take last N messages
    recent_messages = messages[-max_history:] if len(messages) > max_history else messages
    
    # Format messages
    formatted_history = ""
    for msg in recent_messages:
        speaker = "Candidate" if msg['speaker'] == 'user' else "Interviewer"
        formatted_history += f"{speaker}: {msg['text']}\n"
    
    return formatted_history.strip()