#!/usr/bin/env python3
"""Render DOT and Archify figures declared in the design spec into PNG files.

DOT figures are declared in design_spec.figures keyed by slot: architecture,
key_1..key_N (key_designs) and function_1..function_N (functions). Archify
sequence/interaction diagrams are declared in design_spec.sequences. All PNGs
go to 软件著作权申请资料/草稿/图纸/ and a 图纸清单.json is written for the
draft generator to reference.

DOT rendering uses the first working backend on this system, detected at
runtime: dot -Tpng, or dot -Tsvg plus an external SVG converter (cairosvg /
inkscape / librsvg / imagemagick). Archify sequences are delivered to self-
contained HTML and screenshotted to PNG via a headless browser. The preferred
backend is read from 环境检查.json when present, otherwise probed on the fly.
Rendering failures never fake success: failed slots keep their visible
【图预留】 text and are recorded with status "error" in the manifest.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import (
    DIAGRAM_BACKEND_ORDER,
    DOT_LAYOUT_DPI,
    archify_install_hint,
    check_png_layout,
    detect_archify,
    detect_diagram_backends,
    diagram_install_hint,
    ensure_dir,
    lint_dot_source,
    normalize_dot_source,
    read_json,
    safe_filename,
    screenshot_html_to_png,
    write_json,
)


FIGURE_KEY_RE = re.compile(r"^(architecture|key_[1-9][0-9]*|function_[1-9][0-9]*)$")

ARCHIFY_ESSENTIAL_TYPES = {"sequence", "workflow", "architecture", "dataflow", "lifecycle"}


def normalize_figures(spec: dict[str, Any]) -> dict[str, str]:
    figures = spec.get("figures")
    if figures is None:
        return {}
    if not isinstance(figures, dict):
        raise SystemExit("design_spec field must be an object: figures")
    normalized: dict[str, str] = {}
    for key, value in figures.items():
        key = str(key).strip()
        if not FIGURE_KEY_RE.fullmatch(key):
            raise SystemExit(
                f"design_spec.figures key must be architecture, key_<n> or function_<n>; got: {key}"
            )
        dot = str(value or "").strip()
        if not dot:
            raise SystemExit(f"design_spec.figures.{key} 不能为空，请填写 DOT 图源或删除该条目")
        normalized[key] = dot
    key_designs = spec.get("key_designs") or []
    functions = spec.get("functions") or []
    for key in normalized:
        match = re.fullmatch(r"key_(\d+)", key)
        if match and int(match.group(1)) > len(key_designs):
            raise SystemExit(f"design_spec.figures.{key} 超出 key_designs 范围")
        match = re.fullmatch(r"function_(\d+)", key)
        if match and int(match.group(1)) > len(functions):
            raise SystemExit(f"design_spec.figures.{key} 超出 functions 范围")
    return normalized


def figure_order(keys: list[str]) -> list[str]:
    def sort_key(key: str) -> tuple[int, int]:
        if key == "architecture":
            return (0, 0)
        match = re.fullmatch(r"(key|function)_(\d+)", key)
        slot = 1 if match.group(1) == "key" else 2
        return (slot, int(match.group(2)))

    return sorted(keys, key=sort_key)


def normalize_sequences(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate Archify sequence specs declared under design_spec.sequences.

    Archify uses its own JSON schema (participants/messages, not nodes/edges).
    The model authors Archify-native specs, so this check is intentionally
    light — Archify's own validator catches schema errors at render time.
    """
    raw = spec.get("sequences")
    if not raw:
        return []
    if not isinstance(raw, list):
        raise SystemExit("design_spec field must be a list: sequences")
    archify = detect_archify()
    sequences: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"design_spec.sequences item {index} must be an object")
        sequence_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        sequence_type = str(item.get("type") or item.get("diagram_type") or "sequence").strip()
        spec_data = item.get("spec")
        if not sequence_id or not title or not isinstance(spec_data, dict):
            raise SystemExit(
                f"design_spec.sequences item {index} requires id, title and spec (Archify JSON)"
            )
        if sequence_type not in ARCHIFY_ESSENTIAL_TYPES:
            raise SystemExit(
                f"design_spec.sequences item {index} type must be one of "
                f"{sorted(ARCHIFY_ESSENTIAL_TYPES)}; got: {sequence_type}"
            )
        if not archify:
            raise SystemExit(
                f"sequence {sequence_id} 需要 Archify 但未检测到。{archify_install_hint()}"
            )
        # Coerce diagram_type inside the spec to match the declared type.
        spec_data = dict(spec_data)
        spec_data.setdefault("diagram_type", sequence_type)
        spec_data.setdefault("schema_version", spec_data.get("schema_version", 1))
        sequences.append({
            "id": sequence_id,
            "title": title,
            "type": sequence_type,
            "spec": spec_data,
        })
    return sequences


def render_sequence(sequence: dict[str, Any], figure_dir: Path, work_root: Path, index: int) -> dict[str, Any]:
    """Render one Archify sequence to PNG via CLI + headless screenshot."""
    archify = detect_archify()
    sequence_id = sequence["id"]
    prefix = f"seq-{index:02d}-{safe_filename(sequence_id)}"
    json_path = work_root / "草稿" / f".archify-{prefix}.json"
    html_path = work_root / "草稿" / f"{prefix}.html"
    output = figure_dir / f"{prefix}.png"
    manifest: dict[str, Any] = {
        "key": sequence_id, "path": f"图纸/{output.name}",
        "title": sequence["title"], "kind": "sequence", "type": sequence["type"],
    }
    try:
        json_path.write_text(json.dumps(sequence["spec"], ensure_ascii=False, indent=2), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, archify, "deliver", sequence["type"], str(json_path), str(html_path),
             "--quality", "showcase"],
            capture_output=True, timeout=180, check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
            manifest["status"] = "error"
            manifest["error"] = detail[-1] if detail else f"archify deliver exit {completed.returncode}"
            return manifest
        error = screenshot_html_to_png(html_path, output)
        if error:
            manifest["status"] = "error"
            manifest["error"] = error
            return manifest
        manifest["status"] = "ok"
        manifest["backend"] = "archify"
        allow_wide = bool(re.search(r"\brankdir\s*=\s*LR\b", str(sequence.get("layout") or "")))
        manifest["layout"] = check_png_layout(output, allow_wide=allow_wide)
        return manifest
    except (OSError, subprocess.SubprocessError) as exc:
        manifest["status"] = "error"
        manifest["error"] = f"Archify 渲染异常：{exc}"
        return manifest
    finally:
        for path in (json_path, html_path):
            path.unlink(missing_ok=True)


def _render_with_backend(dot_source: str, output: Path, backend: str, work_root: Path) -> tuple[str | None, list[str]]:
    """Render DOT source to PNG with one backend. Returns (error, warnings)."""
    dot_binary = shutil.which("dot")
    if not dot_binary:
        return "未安装 graphviz（dot 命令不可用）", []
    source = normalize_dot_source(dot_source)
    warnings: list[str] = []
    try:
        if backend == "dot-png":
            with output.open("wb") as handle:
                completed = subprocess.run(
                    [dot_binary, "-Tpng", f"-Gdpi={DOT_LAYOUT_DPI}"],
                    input=source.encode("utf-8"),
                    stdout=handle,
                    stderr=subprocess.PIPE,
                    timeout=120,
                    check=False,
                    cwd=str(work_root),
                )
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
                reason = detail[0] if detail else f"exit {completed.returncode}"
                return f"dot 渲染失败：{reason}", []
            warnings = _dot_warnings(completed.stderr)
        elif backend.startswith("dot-svg-"):
            converter = backend[len("dot-svg-"):]
            svg_path = output.with_suffix(".svg")
            with svg_path.open("wb") as handle:
                completed = subprocess.run(
                    [dot_binary, "-Tsvg"],
                    input=source.encode("utf-8"),
                    stdout=handle,
                    stderr=subprocess.PIPE,
                    timeout=120,
                    check=False,
                    cwd=str(work_root),
                )
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
                reason = detail[0] if detail else f"exit {completed.returncode}"
                return f"dot SVG 渲染失败：{reason}", []
            warnings = _dot_warnings(completed.stderr)
            if converter == "cairosvg":
                command = [sys.executable, "-m", "cairosvg", str(svg_path), "-o", str(output), "--dpi", str(DOT_LAYOUT_DPI)]
            elif converter == "inkscape":
                command = ["inkscape", str(svg_path), "-o", str(output), "-d", str(DOT_LAYOUT_DPI)]
            elif converter == "librsvg":
                command = ["rsvg-convert", "-o", str(output), "--dpi-x", str(DOT_LAYOUT_DPI), "--dpi-y", str(DOT_LAYOUT_DPI), str(svg_path)]
            else:
                command = ["convert", "-density", str(DOT_LAYOUT_DPI), str(svg_path), str(output)]
            completed = subprocess.run(command, capture_output=True, timeout=120, check=False)
            svg_path.unlink(missing_ok=True)
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
                reason = detail[0] if detail else f"exit {completed.returncode}"
                return f"SVG 转换失败（{converter}）：{reason}", []
        else:
            return f"未知渲染后端：{backend}", []
        if not output.is_file() or output.stat().st_size == 0:
            return "渲染输出为空", warnings
        _trim_png(output)
        return None, warnings
    except (OSError, subprocess.SubprocessError) as exc:
        return f"渲染异常：{exc}", []


def _dot_warnings(stderr: bytes) -> list[str]:
    """Turn graphviz warnings about layout into advisory notes."""
    text = stderr.decode("utf-8", errors="replace")
    notes: list[str] = []
    if "do not currently handle edge labels" in text:
        notes.append("graphviz 提示正交边不支持边标签，已自动改用折线；若仍有错位请精简边标签")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Warning:") and "edge labels" not in line:
            notes.append(f"graphviz 渲染提示：{line[len('Warning:'):].strip()}")
    return list(dict.fromkeys(note for note in notes if note))[:4]


def _trim_png(output: Path) -> None:
    """Trim excess whitespace around the drawing when ImageMagick is available."""
    converter = shutil.which("convert")
    if not converter:
        return
    try:
        trimmed = output.with_name(f".{output.stem}-trim{output.suffix}")
        completed = subprocess.run(
            [converter, str(output), "-trim", "-bordercolor", "white", "-border", "12", str(trimmed)],
            capture_output=True, timeout=120, check=False,
        )
        if completed.returncode == 0 and trimmed.is_file() and trimmed.stat().st_size > 0:
            trimmed.replace(output)
    except (OSError, subprocess.SubprocessError):
        pass


def preferred_backends(workdir: Path) -> list[str]:
    """Return the ordered backend list: 环境检查.json preference first, then a live probe."""
    env_path = workdir / "环境检查.json"
    if env_path.is_file():
        try:
            preferred = read_json(env_path).get("capabilities", {}).get("diagram_backend")
        except Exception:
            preferred = None
        if preferred in DIAGRAM_BACKEND_ORDER:
            return [preferred] + [name for name in DIAGRAM_BACKEND_ORDER if name != preferred]
    detected = detect_diagram_backends()
    return list(detected.get("backends") or [])


def render_figures(workdir: Path, business: dict[str, Any]) -> dict[str, Any]:
    draft_dir = workdir / "草稿"
    spec = business.get("design_spec") or {}
    figure_dir = ensure_dir(draft_dir / "图纸")

    manifest: dict[str, Any] = {"figures": [], "sequences": []}

    figures = normalize_figures(spec)
    if figures:
        backends = preferred_backends(workdir)
        dot_manifest = {"method": "dot", "backends": backends, "figures": []}
        for index, key in enumerate(figure_order(list(figures)), start=1):
            filename = f"{index:02d}-{safe_filename(key)}.png"
            output = figure_dir / filename
            blocking, advisory = lint_dot_source(figures[key])
            figure_manifest: dict[str, Any] = {"key": key, "path": f"图纸/{filename}", "lint": advisory}
            if blocking:
                figure_manifest["status"] = "error"
                figure_manifest["error"] = "；".join(blocking) + "；请用 \\n 换行或 <BR/> 后重跑"
                dot_manifest["figures"].append(figure_manifest)
                continue
            error = f"无可用渲染后端（{diagram_install_hint()}）" if not backends else None
            used_backend = ""
            render_warnings: list[str] = []
            for backend in backends:
                error, render_warnings = _render_with_backend(figures[key], output, backend, draft_dir)
                if error is None:
                    used_backend = backend
                    break
            if error:
                figure_manifest["status"] = "error"
                figure_manifest["error"] = error
            else:
                figure_manifest["status"] = "ok"
                figure_manifest["backend"] = used_backend
                advisory = advisory + render_warnings
                figure_manifest["lint"] = advisory
                allow_wide = bool(re.search(r"\brankdir\s*=\s*LR\b", figures[key]))
                figure_manifest["layout"] = check_png_layout(output, allow_wide=allow_wide)
            dot_manifest["figures"].append(figure_manifest)
        manifest["dot"] = dot_manifest
        manifest["figures"] = dot_manifest["figures"]

    sequences = normalize_sequences(spec)
    for index, sequence in enumerate(sequences, start=1):
        manifest["sequences"].append(render_sequence(sequence, figure_dir, workdir, index))

    write_json(draft_dir / "图纸清单.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default="软件著作权申请资料")
    args = parser.parse_args()

    workdir = Path(args.workdir)
    business = read_json(workdir / "草稿" / "业务理解.json")
    if business.get("manual_kind") != "design":
        print("SKIP: 业务理解不是技术方案文档模式（manual_kind != design），无图纸需要渲染")
        return
    manifest = render_figures(workdir, business)
    figures = manifest.get("figures") or []
    sequences = manifest.get("sequences") or []
    if not figures and not sequences:
        print("OK figures: 业务理解未声明图纸/序列图，技术方案文档保留【图预留】占位")
        return
    for figure in figures:
        if figure.get("status") == "ok":
            print(f"OK figure: {figure['key']} -> {figure['path']}（{figure.get('backend')}）")
    for sequence in sequences:
        if sequence.get("status") == "ok":
            print(f"OK sequence: {sequence['key']} -> {sequence['path']}（archify）")
    failed = [f for f in figures if f.get("status") != "ok"] + [s for s in sequences if s.get("status") != "ok"]
    if failed:
        print("STOP_FOR_USER")
        for item in failed:
            print(f"NEXT_ACTION: {'序列图' if item.get('kind') == 'sequence' else '图纸'} {item['key']} 渲染失败：{item.get('error')}")
        return
    total = len(figures) + len(sequences)
    print(f"OK figures: {total} 张（DOT {len(figures)} / Archify {len(sequences)}）已渲染到 软件著作权申请资料/草稿/图纸/")


if __name__ == "__main__":
    main()
