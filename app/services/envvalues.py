from dotenv import load_dotenv
import os

load_dotenv()

def get_env_value(key):
    return os.getenv(key)