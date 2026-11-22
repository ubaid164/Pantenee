"""Build a Windows x64 ZIP with a pinned Whisper Small model."""

import argparse
import hashlib
import importlib.metadata
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_SHA256 = "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"
MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "README.md")
SOURCE_FILES = ("pantenee.py", "desktop_pet.py", "speech.py", "win_input.py",
                "translation.py", "setup_translation.py", "Set up translation.cmd",
                "Run with Python.cmd", "requirements.txt", "README.md", "CHANGELOG.md",
                "THIRD_PARTY.md")


def verify_model(directory):
    for filename in MODEL_FILES:
        if not (directory / filename).is_file():
            raise ValueError(f"Missing model file: {filename}")
    with (directory / "model.bin").open("rb") as weights:
        if hashlib.file_digest(weights, "sha256").hexdigest() != MODEL_SHA256:
            raise ValueError("Whisper Small weights did not match the pinned SHA-256.")


def prepare_model(directory):
    if not (directory / "model.bin").is_file():
        from huggingface_hub import snapshot_download

        snapshot_download(MODEL_REPO, revision=MODEL_REVISION, local_dir=directory,
                          allow_patterns=list(MODEL_FILES))
    verify_model(directory)


def copy_notices(target):
    notices = target / "third-party-notices"
    for distribution in importlib.metadata.distributions():
        package = distribution.metadata.get("Name", "")
        for entry in distribution.files or ():
            if not entry.name.lower().startswith(("license", "licence", "notice", "copying", "thirdpartynotices")):
                continue
            if not any(part.endswith(".dist-info") for part in entry.parts):
                continue
            original = Path(distribution.locate_file(entry))
            if original.is_file():
                folder = notices / package
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, folder / entry.name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        notices.mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_license, notices / "Python.txt")


def write_archive(result, entries):
    result.parent.mkdir(parents=True, exist_ok=True)
    pending = result.with_suffix(".tmp")
    with ZipFile(pending, "w", compression=ZIP_DEFLATED, compresslevel=3) as archive:
        for path, name in entries:
            archive.write(path, name.as_posix())
    with ZipFile(pending) as archive:
        failed = archive.testzip()
        if failed:
            raise ValueError(f"Release archive failed its CRC check: {failed}")
    pending.replace(result)
    print(f"{result} ({result.stat().st_size:,} bytes)")


def build_setup(model, output):
    folder = Path("Pantenee")
    license_file = ROOT / "licenses" / "Whisper-MIT.txt"
    entries = [(ROOT / name, folder / name) for name in SOURCE_FILES]
    entries += [(model / name, folder / "model" / name) for name in MODEL_FILES]
    entries.extend([(license_file, folder / "model" / "LICENSE"),
                    (license_file, folder / "licenses" / license_file.name)])
    write_archive(output / "Pantenee-Setup.zip", entries)


def build(model, output):
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine() != "AMD64":
        raise RuntimeError("Build the release using x64 Python on Windows.")
    target = ROOT / "dist" / "Pantenee"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
        "--name", "Pantenee", "--specpath", str(ROOT / "build"),
        "--distpath", str(target.parent), "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--collect-data", "faster_whisper", "--collect-data", "_sounddevice_data",
        "--collect-binaries", "ctranslate2", "--copy-metadata", "huggingface_hub",
        *[argument for package in ("torch", "transformers", "pandas", "scipy", "IPython", "matplotlib", "PIL")
          for argument in ("--exclude-module", package)], str(ROOT / "pantenee.py"),
    ], cwd=ROOT, check=True)

    (target / "model").mkdir(exist_ok=True)
    for filename in MODEL_FILES:
        shutil.copy2(model / filename, target / "model" / filename)
    shutil.copy2(ROOT / "licenses" / "Whisper-MIT.txt", target / "model" / "LICENSE")
    (target / "licenses").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "licenses" / "Whisper-MIT.txt", target / "licenses" / "Whisper-MIT.txt")
    for filename in SOURCE_FILES:
        shutil.copy2(ROOT / filename, target / filename)
    copy_notices(target)

    entries = ((path, path.relative_to(target.parent)) for path in sorted(target.rglob("*"))
               if path.is_file())
    write_archive(output / "Pantenee-Windows-x64.zip", entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "model")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--model-only", action="store_true")
    mode.add_argument("--setup-only", action="store_true")
    options = parser.parse_args()
    prepare_model(options.model.resolve())
    if options.setup_only:
        build_setup(options.model.resolve(), options.output.resolve())
    elif not options.model_only:
        build(options.model.resolve(), options.output.resolve())
