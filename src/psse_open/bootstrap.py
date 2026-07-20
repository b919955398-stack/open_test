from __future__ import annotations

import importlib
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


# Python 3.8+ removes DLL-directory handles when they are garbage-collected.
# Keep them alive for the complete PSS/E process lifetime.
_DLL_DIRECTORY_HANDLES = []


def _values(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _unique_existing(paths: Iterable[Any]) -> List[Path]:
    result: List[Path] = []
    seen = set()
    for value in paths:
        if value in (None, ""):
            continue
        expanded = Path(os.path.expandvars(os.path.expanduser(str(value))))
        key = str(expanded).lower()
        if key not in seen and expanded.is_dir():
            seen.add(key)
            result.append(expanded)
    return result


def psse_search_paths(config: Dict[str, Any]) -> Tuple[List[Path], List[Path], List[Path]]:
    """Return PSSPY, binary and all attempted install directories.

    Explicit configuration wins. On Windows, the standard PTI installation
    locations are then checked using the running Python major/minor version.
    """
    version = str(config.get("version", "34"))
    python_tag = "PSSPY{}{}".format(sys.version_info[0], sys.version_info[1])

    roots: List[Path] = []
    for value in _values(config.get("install_root")):
        roots.append(Path(os.path.expandvars(os.path.expanduser(value))))

    if os.name == "nt":
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        roots.extend([
            Path(program_files_x86) / "PTI" / ("PSSE" + version),
            Path(program_files) / "PTI" / ("PSSE" + version),
        ])

    configured_python = _values(config.get("python_path"))
    configured_bin = _values(config.get("bin_path"))
    python_attempts = [Path(os.path.expandvars(os.path.expanduser(value))) for value in configured_python]
    bin_attempts = [Path(os.path.expandvars(os.path.expanduser(value))) for value in configured_bin]
    for root in roots:
        python_attempts.append(root / python_tag)
        bin_attempts.append(root / "PSSBIN")

    python_paths = _unique_existing(python_attempts)
    bin_paths = _unique_existing(bin_attempts)
    attempted = []
    for path in python_attempts + bin_attempts:
        if str(path).lower() not in {str(item).lower() for item in attempted}:
            attempted.append(path)
    return python_paths, bin_paths, attempted


def _activate_paths(python_paths: Iterable[Path], bin_paths: Iterable[Path]) -> None:
    global _DLL_DIRECTORY_HANDLES
    ordered = list(python_paths) + list(bin_paths)
    for path in reversed(list(python_paths)):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    existing_path = os.environ.get("PATH", "")
    additions = [str(path) for path in ordered if str(path) not in existing_path.split(os.pathsep)]
    if additions:
        os.environ["PATH"] = os.pathsep.join(additions + [existing_path])

    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for path in bin_paths:
            try:
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(path)))
            except OSError:
                # PATH remains the compatibility fallback used by PSS/E 34.
                pass


def import_psse(config: Dict[str, Any]):
    """Import PSS/E without making SPEC validation depend on a PSS/E install."""
    python_paths, bin_paths, attempted = psse_search_paths(config)
    _activate_paths(python_paths, bin_paths)
    version = str(config.get("version", "34"))
    try:
        importlib.import_module("psse{}".format(version))
    except ImportError:
        # Newer PSS/E installations can expose psspy without a psseXX bootstrap module.
        pass
    try:
        psspy = importlib.import_module("psspy")
        redirect = importlib.import_module("redirect")
        redirect.psse2py()
        dyntools = importlib.import_module("dyntools")
        return psspy, dyntools
    except ImportError as exc:
        searched = ", ".join(str(path) for path in attempted) or "no configured/standard paths"
        raise RuntimeError(
            "Could not import PSS/E {} from {} ({}-bit). Searched: {}. "
            "Set psse.python_path and psse.bin_path in MODEL_DIR\\open_psse_config.json if PSS/E is installed elsewhere.".format(
                version, sys.executable, platform.architecture()[0].replace("bit", ""), searched
            )
        ) from exc
