import hashlib
import re
from pathlib import Path, PurePosixPath
from .config import settings


def artifact_path(kind, identity):
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid artifact identity")
    path = settings.data_dir / kind / identity
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def safe_member(name):
    if "\\" in name or "\x00" in name or re.match(r"^[A-Za-z]:", name):
        raise ValueError("Unsafe archive path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe archive path")
    return str(path)


def redact(text):
    text = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+", r"\1[REDACTED]", text)
    text = re.sub(r'(?i)([\"\']?(?:password|passwd|api[_-]?key|secret|access[_-]?token|token)[\"\']?\s*[:=]\s*)([\"\']?)[^\s,;\"\'}]+\2', r'\1"[REDACTED]"', text)
    return text
