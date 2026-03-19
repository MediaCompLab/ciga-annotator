import sys
import os

# Add src to python path so 'src' module can be found
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.main import main

if __name__ == "__main__":
    main()
