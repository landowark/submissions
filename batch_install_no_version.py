import sys
import re
from pip._internal import main as pip_main

def install(package):
    # Strip whitespace and anything from the first version/comment marker onwards
    # This regex matches '==', '>=', '>', '<=', '<', '~=', or ';' (for environment markers)
    clean_package = re.split(r'[=<>~;]', package)[0].strip()
    
    if clean_package: # Only install if the line isn't empty or just a comment
        pip_main(['install', clean_package])

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python script.py requirements.txt")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        for line in f:
            # Skip empty lines or comments
            if line.strip() and not line.startswith('#'):
                install(line)