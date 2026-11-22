"""Download verified Qwen3.5 model weights for optional offline translation."""

import hashlib
import os
import subprocess
from pathlib import Path

from translation import MODEL_FILENAME


SHA256 = "e8bf47d40c5ba68baf8f3e503ee36710da6e8641cb0a670a508cff5b3f0cfbf7"
WEIGHTS = f"https://registry.ollama.ai/v2/library/qwen3.5/blobs/sha256:{SHA256}"


def verified(path):
    if not path.is_file():
        return False
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest() == SHA256


def main():
    app_data = Path(os.environ.get("PANTENEE_DATA_DIR") or Path(os.environ["LOCALAPPDATA"]) / "Pantenee")
    destination = Path(os.environ.get("PANTENEE_TRANSLATION_MODEL") or app_data / "translation" / MODEL_FILENAME)
    if verified(destination):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".partial")
    if not verified(partial):
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "3", "--connect-timeout", "25",
                        "--continue-at", "-",
                        "--output", str(partial), WEIGHTS], check=True)
    if not verified(partial):
        partial.unlink()
        raise ValueError("Qwen3.5 model checksum did not match. Run setup again to restart the download.")
    partial.replace(destination)


if __name__ == "__main__":
    main()
