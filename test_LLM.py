import os
import logging
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("model-test")

model_path = "./phi-model"

logger.info(f"Testing model loading from {model_path}")
logger.info(f"Path exists: {os.path.exists(model_path)}")

try:
    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    logger.info("Tokenizer loaded successfully")
    
    logger.info("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype="auto",
        trust_remote_code=True
    )
    logger.info("Model loaded successfully")
    
    # Test a simple prediction
    prompt = "Hello, how are you?"
    inputs = tokenizer(prompt, return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=20)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    logger.info(f"Model test response: {response}")
    
    print("MODEL TEST SUCCESSFUL!")
except Exception as e:
    logger.error(f"Error loading model: {e}")
    print("MODEL TEST FAILED!")