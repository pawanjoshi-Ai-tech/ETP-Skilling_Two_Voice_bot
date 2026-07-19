"""Entry point — runs src/main.py as if invoked directly (python app.py <cmd>)."""

import os
import runpy

SRC_MAIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "main.py")

if __name__ == "__main__":
    runpy.run_path(SRC_MAIN, run_name="__main__")
