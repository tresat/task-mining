import os
import requests
import json

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

load_env()
key = os.environ.get("GEMINI_API_KEY")

if not key:
    print("Error: GEMINI_API_KEY not set")
    exit(1)

print(f"Testing key: {key[:5]}...")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
response = requests.get(url)

if response.status_code == 200:
    print("Success! Available models:")
    models = response.json().get("models", [])
    for m in models:
        if "gemini" in m["name"]:
            print(f" - {m['name']}")
else:
    print(f"Error {response.status_code}: {response.text}")
