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
                trust_remote_code=True
            )
            
            # Check if CUDA is available
            if torch.cuda.is_available():
                logger.info("CUDA is available, using GPU")
                device = "cuda"
                _model = _model.to(device)
            else:
                logger.warning("CUDA not available, using CPU (this will be slow)")
                device = "cpu"
            
            logger.info(f"LLM model loaded successfully: {model_path}")
            
            # Log device information
            if device == "cuda":
                device_name = torch.cuda.get_device_name(0)
                logger.info(f"Using GPU: {device_name}")
                
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
    
    # Format the prompt (simplified format that works better with phi models)
    prompt = f"""SYSTEM: You are a professional job interviewer named Alex. Follow these rules strictly:
1. Only respond as the interviewer Alex
2. Keep responses to 1-2 sentences maximum
3. Ask only ONE question at a time
4. NEVER answer your own questions
5. NEVER role-play as the candidate
6. NEVER use phrases like "Can you tell me more" - be specific

{personality_prompt}

You're interviewing someone for a {position} position.{difficulty_modifier}

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
"[Your direct response to the candidate's statement, then ask a specific follow-up question]"

Previous conversation:
{conversation_history}

Candidate: {user_input}

Interviewer Alex: """
    
    # Log the prompt for debugging
    logger.info(f"Generated prompt:\n{prompt}")
    
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
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
                top_p=top_p
            )
        
        # Decode response
        response_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        
        # Log generation time
        elapsed_time = time.time() - start_time
        logger.info(f"LLM response generated in {elapsed_time:.2f} seconds")
        
        # Clean and validate the LLM response 
        def clean_response(text):
            # Strip whitespace
            text = text.strip()
            
            # Remove control tokens
            for token in ["[s]", "[END]", "[INST]", "[/INST]", "ASSISTANT:", "SYSTEM:"]:
                text = text.replace(token, "")
                
            # Remove role labels
            for role in ["Candidate:", "Interviewer:", "Interviewer Alex:", "Alex:"]:
                text = text.replace(role, "")
            
            # Strip whitespace again after removals
            text = text.strip()
            
            # Remove any text that looks like the candidate speaking
            if "\nCandidate:" in text:
                text = text.split("\nCandidate:")[0].strip()
            
            # Check for common patterns indicating a candidate response
            candidate_patterns = [
                "Thank you for sharing", 
                "Thank you for providing",
                "That sounds interesting",
                "I'm interested in learning more",
                "Can you tell me more about"
            ]
            
            # If it contains both a candidate pattern AND a separate interviewer response, split it
            for pattern in candidate_patterns:
                if pattern in text and "\n" in text:
                    # Try to extract just the interviewer part
                    parts = text.split("\n")
                    for part in parts:
                        if not any(p in part for p in candidate_patterns):
                            text = part.strip()
                            break
            
            # If response starts with typical candidate response, replace it
            for pattern in candidate_patterns:
                if text.startswith(pattern):
                    return "What specific programming languages and frameworks are you most comfortable working with?"
            
            # Remove any numbered questions (1., 2., etc.) and just keep the first one
            if "\n1." in text and "\n2." in text:
                try:
                    # Get the introduction text if any
                    intro = text.split("\n1.")[0].strip()
                    # Get just the first question
                    question = text.split("\n1.")[1].split("\n2.")[0].strip()
                    # Combine them
                    if intro:
                        text = f"{intro} {question}"
                    else:
                        text = question
                except:
                    # If parsing fails, return a simple question
                    return "What experience do you have with software development?"
            
            # Final validation - if too short or empty, provide a fallback
            if not text or len(text) < 10:
                return "What kind of projects have you worked on that demonstrate your technical skills?"
                
            return text
        
        # Apply the cleaning
        response_text = clean_response(response_text)
        
        # Log the final cleaned response
        logger.info(f"Cleaned response: {response_text}")
        
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