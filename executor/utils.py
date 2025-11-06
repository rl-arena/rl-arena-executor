"""
Utility functions for the executor service.
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO", format_type: str = "json") -> None:
    """
    Setup logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Format type ("json" or "text")
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if format_type == "json":
        # TODO: Implement JSON logging formatter
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(module)s", "message": "%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(handler)


def extract_zip(zip_data: bytes, target_dir: str) -> Path:
    """
    Extract zip file to target directory.

    Args:
        zip_data: Zip file as bytes
        target_dir: Target directory path

    Returns:
        Path to extracted directory

    Raises:
        ValueError: If zip is invalid or extraction fails
    """
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    # Create temporary zip file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
        tmp_zip.write(zip_data)
        tmp_zip_path = tmp_zip.name

    try:
        with zipfile.ZipFile(tmp_zip_path, "r") as zip_ref:
            # Security check: ensure no path traversal
            for member in zip_ref.namelist():
                if member.startswith("/") or ".." in member:
                    raise ValueError(f"Unsafe zip entry: {member}")

            zip_ref.extractall(target_path)

        logger.info(f"Extracted zip to {target_path}")
        return target_path

    except zipfile.BadZipFile as e:
        raise ValueError(f"Invalid zip file: {e}")
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_zip_path):
            os.unlink(tmp_zip_path)


def create_zip(source_dir: str, output_path: Optional[str] = None) -> str:
    """
    Create zip file from directory.

    Args:
        source_dir: Source directory to zip
        output_path: Output zip file path (optional)

    Returns:
        Path to created zip file
    """
    source_path = Path(source_dir)

    if output_path is None:
        output_path = str(source_path.with_suffix(".zip"))

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_path)
                zipf.write(file_path, arcname)

    logger.info(f"Created zip file: {output_path}")
    return output_path


def get_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """
    Calculate file hash.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm (md5, sha1, sha256)

    Returns:
        Hex digest of file hash
    """
    hash_obj = hashlib.new(algorithm)

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


def get_dir_size(path: str) -> int:
    """
    Get total size of directory in bytes.

    Args:
        path: Directory path

    Returns:
        Total size in bytes
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
    return total_size


def safe_remove_dir(path: str) -> None:
    """
    Safely remove directory and all contents.

    Args:
        path: Directory path to remove
    """
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
            logger.debug(f"Removed directory: {path}")
    except Exception as e:
        logger.warning(f"Failed to remove directory {path}: {e}")


def save_json(data: Dict[str, Any], file_path: str, indent: int = 2) -> None:
    """
    Save data to JSON file.

    Args:
        data: Data to save
        file_path: Output file path
        indent: JSON indentation
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)

    logger.debug(f"Saved JSON to {file_path}")


def load_json(file_path: str) -> Dict[str, Any]:
    """
    Load data from JSON file.

    Args:
        file_path: Input file path

    Returns:
        Loaded data
    """
    with open(file_path, "r") as f:
        return json.load(f)


def format_bytes(size_bytes: int) -> str:
    """
    Format bytes to human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "1m 30s")
    """
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.2f}s"
