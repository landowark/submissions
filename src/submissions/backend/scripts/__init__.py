from pathlib import Path
import importlib

p = Path(__file__).parent.absolute()
subs = [item.stem for item in p.glob("*.py") if "__" not in item.stem]
modules = {}
for sub in subs:
    importlib.import_module(f"backend.scripts.{sub}")
