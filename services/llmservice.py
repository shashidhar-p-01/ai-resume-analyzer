import os 
import requests
import json
from dotenv import load_dotenv

load_dotenv()
OLLAMA_URL = os.getenv("OLLAMA_URL")
MODEL_NAME = os.getenv("MODEL_NAME")

def generate_response(prompt):
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json = {
            "model" : MODEL_NAME ,
            "prompt" : prompt,
            "stream" : True,
        }, 
        stream=True
    )

    full_response = ""

    for line in response.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        token = chunk.get("response", "")
        print(token, end="", flush=True)
        full_response += token
    print()
    
    return full_response