#!/usr/bin/env python
"""
Test script to verify that the VR Interview Server is running correctly.
This script checks all the required components and configurations.
"""

import os
import sys
import json
import importlib
import subprocess
import platform
import time

def check_python_version():
    """Check that Python version is compatible."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python version 3.8+ is required")
        print(f"Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    else:
        print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
        return True

def check_dependencies():
    """Check that all required dependencies are installed."""
    required_packages = [
        "flask", "flask_socketio", "eventlet", "torch", "transformers",
        "whisper", "gtts", "numpy"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            print(f"✅ {package} installed")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} missing")
    
    if missing_packages:
        print("\nMissing packages. Install with:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    return True

def check_file_structure():
    """Check that all required files exist."""
    required_files = [
        "server.py",
        "config.json",
        "app/__init__.py",
        "app/websocket.py",
        "app/state_manager.py",
        "app/interview_session.py",
        "app/routes.py",
        "app/utils.py",
        "services/__init__.py",
        "services/speech_processing.py",
        "services/llm_service.py"
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
            print(f"❌ {file_path} missing")
        else:
            print(f"✅ {file_path} exists")
    
    if missing_files:
        print("\nMissing files:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    return True

def check_config():
    """Check that config.json is valid and has required fields."""
    if not os.path.exists("config.json"):
        print("❌ config.json not found")
        return False
    
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        
        required_sections = ["server", "llm", "audio", "interview", "paths"]
        missing_sections = []
        
        for section in required_sections:
            if section not in config:
                missing_sections.append(section)
                print(f"❌ config.json missing '{section}' section")
            else:
                print(f"✅ config.json has '{section}' section")
        
        if missing_sections:
            return False
        
        # Check specific required fields
        if "host" not in config["server"] or "port" not in config["server"]:
            print("❌ config.json missing server host/port")
            return False
        
        print(f"✅ config.json validated")
        return True
        
    except json.JSONDecodeError:
        print("❌ config.json is not valid JSON")
        return False
    except Exception as e:
        print(f"❌ Error checking config: {e}")
        return False

def check_directories():
    """Check that required directories exist or create them."""
    required_dirs = [
        "data/audio/uploads",
        "data/audio/responses",
        "data/conversations"
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                print(f"✅ Created directory: {dir_path}")
            except Exception as e:
                print(f"❌ Failed to create directory {dir_path}: {e}")
                return False
        else:
            print(f"✅ Directory exists: {dir_path}")
    
    return True

def check_gpu():
    """Check if GPU is available for LLM acceleration."""
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            print(f"✅ GPU available: {device_name}")
            print(f"   CUDA Version: {torch.version.cuda}")
            return True
        else:
            print("⚠️ No GPU detected, LLM will run on CPU (slower)")
            return "cpu"
    except ImportError:
        print("⚠️ PyTorch not installed, cannot check GPU")
        return "unknown"
    except Exception as e:
        print(f"⚠️ Error checking GPU: {e}")
        return "error"

def check_microphone():
    """Check if microphone is available."""
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        
        # Get number of input devices
        info = p.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')
        
        # Count input devices
        input_devices = []
        for i in range(num_devices):
            device_info = p.get_device_info_by_index(i)
            if device_info.get('maxInputChannels') > 0:
                input_devices.append(device_info.get('name'))
        
        p.terminate()
        
        if input_devices:
            print(f"✅ {len(input_devices)} microphone(s) detected:")
            for device in input_devices:
                print(f"   - {device}")
            return True
        else:
            print("⚠️ No microphone detected")
            return False
            
    except ImportError:
        print("⚠️ PyAudio not installed, cannot check microphone")
        return "unknown"
    except Exception as e:
        print(f"⚠️ Error checking microphone: {e}")
        return "error"

def check_llm_model():
    """Check if LLM model is available."""
    # Read config to get model path
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        
        model_path = config.get("llm", {}).get("model_path", "./phi-model")
        
        if os.path.exists(model_path):
            # Check if it's a valid model directory
            tokenizer_files = [
                os.path.join(model_path, "tokenizer.json"),
                os.path.join(model_path, "tokenizer_config.json")
            ]
            
            model_files = [
                os.path.join(model_path, "pytorch_model.bin"),
                os.path.join(model_path, "config.json")
            ]
            
            # Check for safetensors format as an alternative
            safetensors_files = [
                os.path.join(model_path, "model.safetensors")
            ]
            
            has_tokenizer = any(os.path.exists(f) for f in tokenizer_files)
            has_model = any(os.path.exists(f) for f in model_files) or any(os.path.exists(f) for f in safetensors_files)
            
            if has_tokenizer and has_model:
                print(f"✅ LLM model found at: {model_path}")
                return True
            else:
                print(f"❌ LLM model files incomplete at: {model_path}")
                print("   Missing model or tokenizer files")
                return False
        else:
            print(f"❌ LLM model not found at: {model_path}")
            print("  You need to download the model first.")
            return False
            
    except Exception as e:
        print(f"❌ Error checking LLM model: {e}")
        return False

def test_server_startup():
    """Attempt to start the server briefly to test for issues."""
    print("\nTesting server startup (will stop after 5 seconds)...")
    
    try:
        # Start server process
        server_process = subprocess.Popen(
            [sys.executable, "server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for 5 seconds
        time.sleep(5)
        
        # Check if process is still running
        exit_code = server_process.poll()
        
        if exit_code is None:
            # Process is still running, good sign
            print("✅ Server started successfully")
            
            # Terminate the process
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(server_process.pid)])
            else:
                server_process.terminate()
            
            server_process.wait(timeout=5)
            return True
        else:
            # Process exited, get output
            stdout, stderr = server_process.communicate()
            print(f"❌ Server startup failed with exit code {exit_code}")
            print("\nStandard output:")
            print(stdout.strip())
            print("\nError output:")
            print(stderr.strip())
            return False
            
    except Exception as e:
        print(f"❌ Error testing server startup: {e}")
        return False

def run_tests():
    """Run all server tests."""
    print("=== VR Interview Server Test ===\n")
    
    # Check system requirements
    print("Checking system requirements...")
    python_ok = check_python_version()
    dependencies_ok = check_dependencies()
    print()
    
    # Check file structure
    print("Checking file structure...")
    files_ok = check_file_structure()
    config_ok = check_config()
    print()
    
    # Check directories
    print("Checking directories...")
    dirs_ok = check_directories()
    print()
    
    # Check hardware
    print("Checking hardware...")
    gpu_status = check_gpu()
    mic_status = check_microphone()
    print()
    
    # Check LLM model
    print("Checking LLM model...")
    model_ok = check_llm_model()
    print()
    
    # Only test server startup if previous checks passed
    server_ok = False
    if python_ok and dependencies_ok and files_ok and config_ok and dirs_ok:
        server_ok = test_server_startup()
    else:
        print("⚠️ Skipping server startup test due to previous failures")
    
    # Summary
    print("\n=== Test Summary ===")
    print(f"Python version: {'✅ OK' if python_ok else '❌ Failed'}")
    print(f"Dependencies: {'✅ OK' if dependencies_ok else '❌ Failed'}")
    print(f"File structure: {'✅ OK' if files_ok else '❌ Failed'}")
    print(f"Configuration: {'✅ OK' if config_ok else '❌ Failed'}")
    print(f"Directories: {'✅ OK' if dirs_ok else '❌ Failed'}")
    print(f"GPU: {'✅ Available' if gpu_status == True else '⚠️ Not available' if gpu_status == 'cpu' else '⚠️ Unknown'}")
    print(f"Microphone: {'✅ Available' if mic_status == True else '⚠️ Not available' if mic_status == False else '⚠️ Unknown'}")
    print(f"LLM model: {'✅ OK' if model_ok else '❌ Failed'}")
    print(f"Server startup: {'✅ OK' if server_ok else '❌ Failed' if server_ok is False else '⚠️ Not tested'}")
    
    # Overall status
    critical_checks = [python_ok, dependencies_ok, files_ok, config_ok, dirs_ok]
    if all(critical_checks) and server_ok:
        print("\n✅ All tests passed! Server should be ready.")
        return True
    else:
        print("\n❌ Some tests failed. Please address the issues before running the server.")
        return False

if __name__ == "__main__":
    run_tests()