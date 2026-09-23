"""Load optional NVIDIA Windows wheels without changing system PATH."""
import os
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path


@contextmanager
def cuda_libraries(device):
    with ExitStack() as stack:
        if os.name == "nt" and device == "cuda":
            root = Path(sys.prefix) / "Lib/site-packages/nvidia"
            directories = sorted(root.glob("*/bin"))
            # CTranslate2 uses LoadLibrary, which also searches the process PATH.
            # This is scoped to this worker call; no persistent Windows changes.
            previous_path = os.environ.get("PATH", "")
            os.environ["PATH"] = os.pathsep.join([*(str(p.resolve()) for p in directories), previous_path])
            stack.callback(os.environ.__setitem__, "PATH", previous_path)
            for directory in directories:
                stack.enter_context(os.add_dll_directory(str(directory.resolve())))
        yield
