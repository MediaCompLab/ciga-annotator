import os
import sys
from pathlib import Path

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent.parent

def read_characters(char_file):
    if not char_file or not os.path.exists(char_file):
        return []
        
    characters = []
    try:
        with open(char_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    except UnicodeDecodeError:
        with open(char_file, 'r', encoding='latin-1') as f:
            lines = [line.strip() for line in f if line.strip()]
            
    for line in lines:
        parts = line.split(',', 1)
        if len(parts) == 2:
            characters.append({'name': parts[0].strip(), 'key': parts[1].strip().upper()})
        else:
            characters.append({'name': parts[0].strip(), 'key': None})
    return characters

def save_characters(char_file, characters):
    if not char_file:
        char_file = str(get_base_dir() / "characters.txt")
    with open(char_file, 'w', encoding='utf-8') as f:
        for char in characters:
            if char.get('key'):
                f.write(f"{char['name']},{char['key']}\n")
            else:
                f.write(f"{char['name']}\n")
