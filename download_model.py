from transformers import AutoModelForCausalLM, AutoTokenizer

# Use a smaller model that doesn't require GPTQ
model_name = "microsoft/phi-2"  # 2.7B parameter model
print(f"Downloading tokenizer for {model_name}...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
print(f"Downloading model {model_name}...")
model = AutoModelForCausalLM.from_pretrained(
    model_name, 
    torch_dtype="auto",
    trust_remote_code=True,
)
print("Model downloaded! Now saving locally...")
# Save the model to disk
model.save_pretrained("./phi-model")
tokenizer.save_pretrained("./phi-model")
print("Download and save complete!")