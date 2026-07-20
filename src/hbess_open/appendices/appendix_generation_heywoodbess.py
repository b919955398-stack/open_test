"""LaTeX appendix generator refactored from the supplied project source."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CLASS_ASSETS_LIST = [
    PACKAGE_DIR / "grid-link-appendix-template.cls",
    PACKAGE_DIR / "report-assets",
]


def _natural_sort_key(path: Path):
    matches = re.findall(r"(\d+)", path.stem)
    return [int(matches[-1]) if matches else 10**12, path.name.lower()]


def _tex_escape(value) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _xelatex_executable() -> str:
    executable = shutil.which("xelatex") or shutil.which("xelatex.exe")
    if executable is None:
        raise RuntimeError(
            "XeLaTeX was not found on PATH. Install MiKTeX/TeX Live with XeLaTeX "
            "to generate appendix PDFs."
        )
    return executable


def generate_appendix_heywoodbess(
    project_name: str,
    client: str,
    title: str,
    doc_number: str,
    issued_date: str,
    revision: str,
    revision_history_csv_path: str,
    plots_directory: str,
    output_path: str,
    class_assets: List[str] = None,
    bess_charging: Optional[bool] = False,
    caption_preprocessor_fn: Optional[Callable] = None,
):
    """Compile one appendix PDF from the PNG plots below a category folder."""
    del client, revision_history_csv_path  # retained for master/API compatibility
    plots_root = Path(plots_directory)
    if not plots_root.is_dir():
        raise FileNotFoundError("Plots directory does not exist: {}".format(plots_root))

    png_files = sorted(plots_root.rglob("*.png"), key=_natural_sort_key)
    if bess_charging is not None:
        png_files = [path for path in png_files if ("CRG" in path.name.upper()) == bess_charging]
    if not png_files:
        raise ValueError("No matching PNG plots found below {}".format(plots_root))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = [Path(item) for item in (class_assets or DEFAULT_CLASS_ASSETS_LIST)]

    with tempfile.TemporaryDirectory(prefix="hbess_appendix_") as temporary:
        temp_dir = Path(temporary)
        for asset in assets:
            destination = temp_dir / asset.name
            if asset.is_file():
                shutil.copy2(asset, destination)
            elif asset.is_dir():
                shutil.copytree(asset, destination)
            else:
                raise FileNotFoundError("Appendix asset does not exist: {}".format(asset))

        temp_plots = temp_dir / "plots"
        temp_plots.mkdir()
        prepared = []
        for number, source in enumerate(png_files, start=1):
            destination = temp_plots / "figure_{:04d}.png".format(number)
            shutil.copy2(source, destination)
            caption = source.stem
            if caption_preprocessor_fn is not None:
                caption = caption_preprocessor_fn(caption)
            prepared.append((destination.relative_to(temp_dir).as_posix(), caption, number))

        lines = [
            r"\documentclass{grid-link-appendix-template}",
            r"\project{" + _tex_escape(project_name) + "}",
            r"\client{Atmos}",
            r"\title{" + _tex_escape(title) + "}",
            r"\docnumber{" + _tex_escape(doc_number) + "}",
            r"\issueddate{" + _tex_escape(issued_date) + "}",
            r"\revision{" + _tex_escape(revision) + "}",
            r"\revisionhistorycsvpath{}",
            r"\begin{document}",
            r"\frontmatter",
            r"\maketitle",
            r"\listoffigures",
            r"\mainmatter",
            r"\uselandscape",
        ]
        for image_path, caption, number in prepared:
            lines.extend(
                [
                    r"\begin{figure}[htbp]",
                    r"\centering",
                    r"\begin{textblock*}{\paperwidth}(0cm,3.5cm)",
                    r"\includegraphics[height=15cm,keepaspectratio]{" + image_path + "}",
                    r"\caption{" + _tex_escape(caption) + "}",
                    r"\label{fig:hbess-" + str(number) + "}",
                    r"\end{textblock*}",
                    r"\end{figure}",
                    r"\clearpage",
                ]
            )
        lines.append(r"\end{document}")

        tex_path = temp_dir / "appendix.tex"
        tex_path.write_text("\n".join(lines), encoding="utf-8")
        command = [_xelatex_executable(), "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
        for _ in range(2):
            completed = subprocess.run(
                command,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                errors="replace",
            )
            if completed.returncode != 0:
                tail = "\n".join((completed.stdout + "\n" + completed.stderr).splitlines()[-40:])
                raise RuntimeError("XeLaTeX failed while creating {}:\n{}".format(output, tail))
        shutil.copy2(temp_dir / "appendix.pdf", output)

    print("Created appendix: {}".format(output))
    return str(output)
