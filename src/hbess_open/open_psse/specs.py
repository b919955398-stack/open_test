from __future__ import annotations

from datetime import datetime
from difflib import get_close_matches
from fnmatch import fnmatchcase
from pathlib import Path
import re
from typing import Any, List, Mapping, Sequence

import pandas as pd


_FALSE_VALUES = {"", "0", "false", "f", "no", "n", "off", "disabled", "nan", "none"}
_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on", "enabled"}
_METADATA_SHEETS = {"revision history", "revisions", "legend", "contents", "readme"}


def now_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M_%S%f")


def find_files(directory: str, extension: str) -> List[str]:
    return sorted(str(path) for path in Path(directory).rglob("*" + extension))


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    return list(value)


def _enabled(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in _FALSE_VALUES:
        return False
    if text in _TRUE_VALUES:
        return True
    return bool(text)


def _resolve_sheets(path: Path, selectors: Sequence[str], strict: bool) -> list[str]:
    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        available = workbook.sheet_names

    included: list[str] = []
    excluded: list[str] = []
    for raw_selector in selectors:
        selector = str(raw_selector).strip()
        if not selector:
            continue
        is_exclusion = selector.startswith("!")
        pattern = selector[1:] if is_exclusion else selector
        matches = [name for name in available if fnmatchcase(name, pattern)]
        if pattern == "*":
            matches = [name for name in matches if name.strip().lower() not in _METADATA_SHEETS]
        if not matches and strict:
            hint = get_close_matches(pattern, available, n=3, cutoff=0.45)
            message = "SPEC sheet selector {!r} matched nothing in {}".format(selector, path.name)
            if hint:
                message += "; closest: {}".format(", ".join(hint))
            raise ValueError(message)
        target = excluded if is_exclusion else included
        for name in matches:
            if name not in target:
                target.append(name)
    return [name for name in included if name not in excluded]


def _matches_any(value: Any, patterns: Sequence[str]) -> bool:
    text = str(value)
    return any(fnmatchcase(text, str(pattern)) for pattern in patterns)


def _compare(series: pd.Series, operator: str, value: Any, column: str) -> pd.Series:
    operator = str(operator).strip().lower()
    aliases = {
        "eq": "==", "equals": "==", "ne": "!=", "not_equals": "!=",
        "gt": ">", "ge": ">=", "gte": ">=", "lt": "<", "le": "<=", "lte": "<=",
        "notin": "not in", "nin": "not in",
    }
    operator = aliases.get(operator, operator)
    if operator == "==":
        return series == value
    if operator == "!=":
        return series != value
    if operator in {">", ">=", "<", "<="}:
        try:
            if operator == ">":
                return series > value
            if operator == ">=":
                return series >= value
            if operator == "<":
                return series < value
            return series <= value
        except TypeError as exc:
            raise ValueError(
                "SPEC filter {!r} {} {!r} compares incompatible values".format(column, operator, value)
            ) from exc
    if operator == "in":
        return series.isin(_as_list(value))
    if operator == "not in":
        return ~series.isin(_as_list(value))
    if operator == "between":
        bounds = _as_list(value)
        if len(bounds) != 2:
            raise ValueError("SPEC between filter for {!r} needs [minimum, maximum]".format(column))
        return series.between(bounds[0], bounds[1], inclusive="both")
    raise ValueError(
        "Unsupported SPEC operator {!r} for {!r}; use ==, !=, >, >=, <, <=, in, not in or between".format(
            operator, column
        )
    )


def _filter_mask(series: pd.Series, condition: Any, column: str) -> pd.Series:
    if isinstance(condition, Mapping):
        mask = pd.Series(True, index=series.index)
        for operator, value in condition.items():
            mask &= _compare(series, operator, value, column)
        return mask
    if isinstance(condition, str):
        match = re.fullmatch(r"\s*(==|!=|>=|<=|>|<)\s*(.*?)\s*", condition)
        if match:
            raw_value = match.group(2)
            try:
                value = float(raw_value) if "." in raw_value else int(raw_value)
            except ValueError:
                value = raw_value.strip("'\"")
            return _compare(series, match.group(1), value, column)
    values = _as_list(condition)
    return series.isin(values) if values else pd.Series(True, index=series.index)


def _apply_filters(frame: pd.DataFrame, options: Mapping[str, Any]) -> pd.DataFrame:
    result = frame
    enabled_column = str(options.get("enabled_column", "PSSE"))
    if options.get("enabled_only", True):
        if enabled_column not in result.columns:
            raise ValueError("SPEC enabled column {!r} was not found".format(enabled_column))
        result = result[result[enabled_column].map(_enabled)]

    for column, wanted in dict(options.get("filters") or {}).items():
        if column not in result.columns:
            raise ValueError("SPEC filter column {!r} was not found".format(column))
        result = result[_filter_mask(result[column], wanted, column)]

    category_column = str(options.get("category_column", "Test Category"))
    includes = _as_list(options.get("include_categories"))
    excludes = _as_list(options.get("exclude_categories"))
    if (includes or excludes) and category_column not in result.columns:
        raise ValueError("SPEC category column {!r} was not found".format(category_column))
    if includes:
        result = result[result[category_column].map(lambda value: _matches_any(value, includes))]
    if excludes:
        result = result[~result[category_column].map(lambda value: _matches_any(value, excludes))]

    filename_column = str(options.get("filename_column", "File_Name"))
    includes = _as_list(options.get("include_file_names"))
    excludes = _as_list(options.get("exclude_file_names"))
    if (includes or excludes) and filename_column not in result.columns:
        raise ValueError("SPEC filename column {!r} was not found".format(filename_column))
    if includes:
        result = result[result[filename_column].map(lambda value: _matches_any(value, includes))]
    if excludes:
        result = result[~result[filename_column].map(lambda value: _matches_any(value, excludes))]

    text_filter = options.get("text_filter")
    if text_filter:
        needle = str(text_filter).casefold()
        searchable = result.select_dtypes(include=["object", "string"]).fillna("").astype(str)
        result = result[searchable.apply(lambda column: column.str.casefold().str.contains(needle, regex=False)).any(axis=1)]

    limit = options.get("limit")
    if limit is not None:
        limit = int(limit)
        if limit < 0:
            raise ValueError("SPEC limit must be zero or greater")
        result = result.head(limit)
    return result.copy()


def load_spec_options(options: Mapping[str, Any]) -> pd.DataFrame:
    """Load and filter all SPEC sources from one master configuration block.

    Sheet selectors support exact names, ``*``/``?`` globs and exclusions such
    as ``!5255_*_OLD``. Disabled sources are not opened.
    """
    strict = bool(options.get("strict_sheets", True))
    frames: list[pd.DataFrame] = []
    loaded: list[str] = []
    for number, source in enumerate(options.get("sources") or [], start=1):
        if not source.get("enabled", True):
            continue
        name = str(source.get("name") or "source_{}".format(number))
        selectors = _as_list(source.get("sheets"))
        if not selectors:
            loaded.append("{}:<none>".format(name))
            continue
        raw_path = source.get("path")
        if not raw_path:
            raise ValueError("SPEC source {!r} has no path".format(name))
        path = Path(str(raw_path)).expanduser()
        if not path.is_file():
            raise FileNotFoundError("SPEC source {!r} does not exist: {}".format(name, path))
        selected = _resolve_sheets(path, selectors, strict)
        for sheet_name in selected:
            frame = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
            frame = frame.dropna(how="all").copy()
            frame["Spec_Source"] = name
            frame["Spec_Path"] = str(path.resolve())
            frame["Xlsx_Name"] = path.stem
            frame["Sheet_Name"] = sheet_name
            frame["Spec_Row"] = frame.index + 2
            frames.append(frame)
        loaded.append("{}:{}".format(name, ",".join(selected) or "<none>"))

    result = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    if not result.empty:
        result = _apply_filters(result, options)

        filename_column = str(options.get("filename_column", "File_Name"))
        duplicate_policy = str(options.get("duplicate_policy", "error")).lower()
        if duplicate_policy not in {"error", "first", "last", "allow"}:
            raise ValueError("SPEC duplicate_policy must be error, first, last or allow")
        if filename_column in result.columns and duplicate_policy != "allow":
            populated = result[filename_column].notna() & result[filename_column].astype(str).str.strip().ne("")
            duplicate = populated & result.duplicated(filename_column, keep=False)
            if duplicate.any() and duplicate_policy == "error":
                detail = result.loc[duplicate, [filename_column, "Spec_Source", "Sheet_Name", "Spec_Row"]]
                raise ValueError("Duplicate SPEC File_Name values:\n{}".format(detail.to_string(index=False)))
            if duplicate_policy in {"first", "last"}:
                result = result[~populated | ~result.duplicated(filename_column, keep=duplicate_policy)]

    result = result.reset_index(drop=True)
    print("Loaded {} scenarios [{}]".format(len(result), "; ".join(loaded) or "no enabled sources"))
    return result


def spec_source_lists(options: Mapping[str, Any], workflow: str = "studies") -> tuple[list[str], list[list[str]]]:
    """Expose central sources to legacy appendix/report-table functions."""
    paths: list[str] = []
    sheets: list[list[str]] = []
    for source in options.get("sources") or []:
        workflows = _as_list(source.get("workflows") or ["studies", "appendix", "tables"])
        if source.get("enabled", True) and workflow in workflows:
            paths.append(str(source["path"]))
            sheets.append([str(value) for value in _as_list(source.get("sheets")) if not str(value).startswith("!")])
    return paths, sheets


def load_specs_from_xlsx(path: str, sheet_names: Sequence[str]) -> pd.DataFrame:
    return load_spec_options({
        "sources": [{"name": Path(path).stem, "path": path, "sheets": sheet_names}],
        "enabled_only": False,
        "duplicate_policy": "allow",
    })


def load_specs_from_csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["Xlsx_Name"] = Path(path).stem
    frame["Sheet_Name"] = Path(path).stem
    return frame


def load_specs_from_multiple_xlsx(paths: Sequence[str], sheet_names: Sequence[Sequence[str]]) -> pd.DataFrame:
    if len(paths) != len(sheet_names):
        raise ValueError("paths and sheet_names must have matching lengths")
    return load_spec_options({
        "sources": [
            {"name": Path(path).stem, "path": path, "sheets": names, "enabled": bool(names)}
            for path, names in zip(paths, sheet_names)
        ],
        "enabled_only": False,
        "duplicate_policy": "allow",
    })
