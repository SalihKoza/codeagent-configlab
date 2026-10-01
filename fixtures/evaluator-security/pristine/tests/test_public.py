import os, sys
sys.path.insert(0, os.getcwd())
import app
assert app.add(2, 3) == 5
