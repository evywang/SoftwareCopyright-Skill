#!/usr/bin/env python3
"""Shared helpers for the software copyright materials skill."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    "coverage",
    "target",
    "vendor",
    "软件著作权申请资料",
    "software-copyright-materials",
}

KNOWN_CONFIG_FILES = {
    ".babelrc",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yaml",
    ".prettierrc.yml",
    ".swcrc",
    "angular.json",
    "app.json",
    "astro.config.mjs",
    "astro.config.ts",
    "babel.config.js",
    "babel.config.json",
    "Cargo.lock",
    "Cargo.toml",
    "composer.json",
    "docker-compose.yaml",
    "docker-compose.yml",
    "eslint.config.cjs",
    "eslint.config.js",
    "eslint.config.mjs",
    "go.mod",
    "go.sum",
    "jsconfig.json",
    "lerna.json",
    "manifest.json",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "nuxt.config.js",
    "nuxt.config.ts",
    "nx.json",
    "package-lock.json",
    "package.json",
    "playwright.config.js",
    "playwright.config.ts",
    "postcss.config.cjs",
    "postcss.config.js",
    "prettier.config.cjs",
    "prettier.config.js",
    "prettier.config.mjs",
    "project.json",
    "pyproject.toml",
    "rollup.config.js",
    "rollup.config.mjs",
    "rollup.config.ts",
    "svelte.config.js",
    "stylelintrc.json",
    "tailwind.config.js",
    "tailwind.config.ts",
    "tsconfig.app.json",
    "tsconfig.json",
    "tsconfig.node.json",
    "tslint.json",
    "turbo.json",
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.ts",
    "vitest.config.js",
    "vitest.config.ts",
    "webpack.config.js",
    "webpack.config.ts",
    "workspace.json",
    ".env.example",
}

FRONTEND_EXTS = {
    ".vue",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".html",
    ".svelte",
    ".astro",
}

LOCK_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "bun.lock",
}

# Source discovery intentionally uses a denylist plus content detection instead
# of an extension allowlist. New languages and engine-specific scripts should be
# inventoried automatically; the model/user selection gate decides relevance.
DOCUMENT_EXTS = {
    ".adoc",
    ".doc",
    ".docx",
    ".md",
    ".odt",
    ".pdf",
    ".rst",
    ".rtf",
    ".txt",
    ".wps",
}

BINARY_EXTS = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".db",
    ".dll",
    ".dmg",
    ".eot",
    ".exe",
    ".flac",
    ".gif",
    ".gz",
    ".ico",
    ".iso",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lib",
    ".lockb",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".obj",
    ".ogg",
    ".otf",
    ".pdb",
    ".png",
    ".pyc",
    ".rar",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".zip",
}

NON_SOURCE_TEXT_EXTS = {
    ".csv",
    ".log",
    ".tsv",
}

DOCUMENT_FILE_PREFIXES = (
    "changelog",
    "code_of_conduct",
    "contributing",
    "license",
    "readme",
    "security",
)

DOCUMENT_DIR_NAMES = {
    "doc",
    "docs",
    "documentation",
    "spec",
    "specs",
    "设计文档",
    "需求文档",
}

DOCUMENT_NAME_HINTS = (
    "architecture",
    "design",
    "manual",
    "prd",
    "requirement",
    "设计",
    "需求",
    "手册",
    "文档",
    "架构",
    "说明",
)

# Used only to keep obvious source files out of document evidence when their
# names contain words such as "design" or "manual". It is not a discovery gate.
KNOWN_SOURCE_HINT_EXTS = FRONTEND_EXTS | {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".cxx",
    ".dart",
    ".gd",
    ".gml",
    ".go",
    ".h",
    ".hh",
    ".hpp",
    ".java",
    ".kt",
    ".lua",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
}

MAX_SOURCE_FILE_BYTES = 800_000

# Shared code-document layout. The extractor uses the physical-line estimate
# only to choose enough material; Word still performs the final pagination.
CODE_FONT_NAME = "Consolas"
CODE_FONT_SIZE = "8pt"
CODE_LINE_SPACING = "13pt"
CODE_LINES_PER_PAGE = 55
CODE_MAX_COLUMNS = 90

CONFIRMATION_METADATA_KEYS = {
    "user_confirmed",
    "confirmation_note",
    "confirmed_at",
    "confirmed_content_sha256",
}

KNOWN_CODE_DRAFTS = {
    "代码.md",
}

# Legacy split-file names cleaned up when regenerating.
STALE_CODE_DRAFTS = {
    "代码-前30页.md",
    "代码-后30页.md",
    "代码-全部.md",
}


def is_excluded(path: Path) -> bool:
    # iter_project_files checks every directory entry while descending. Looking
    # at all absolute path parts would wrongly exclude a project merely because
    # one of its parent folders happens to be named "build" or like this skill,
    # "software-copyright-materials".
    if path.name in EXCLUDE_DIRS:
        return True
    name = path.name
    if name.startswith(".") and name not in {".env.example"}:
        return True
    if name in LOCK_FILES:
        return True
    if name.endswith(".map") or name.endswith(".min.js") or name.endswith(".min.css"):
        return True
    return False


def iter_project_files(project: Path, exts: set[str] | None = None) -> Iterable[Path]:
    project = project.resolve()
    for root, dirs, files in os.walk(project):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not is_excluded(root_path / d)]
        for filename in files:
            path = root_path / filename
            if is_excluded(path):
                continue
            if exts is not None and path.suffix.lower() not in exts:
                continue
            yield path


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_text(path: Path, limit: int | None = None) -> str:
    data = path.read_bytes()
    if limit is not None:
        data = data[:limit]
    encodings = ["utf-8", "utf-8-sig", "gb18030", "latin-1"]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encodings.insert(0, "utf-32")
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def file_sha256(path: Path) -> str:
    """Return a stable digest used to invalidate stale user confirmations."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def confirmation_payload_sha256(data: dict[str, Any]) -> str:
    """Hash JSON content while excluding confirmation bookkeeping fields."""
    payload = {key: value for key, value in data.items() if key not in CONFIRMATION_METADATA_KEYS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def confirmation_is_current(data: dict[str, Any]) -> bool:
    expected = str(data.get("confirmed_content_sha256") or "")
    return bool(expected) and expected == confirmation_payload_sha256(data)


def draft_snapshot(workdir: Path) -> dict[str, str]:
    """Hash user-reviewable drafts plus the selected screenshot inputs."""
    draft_dir = workdir / "草稿"
    if not draft_dir.is_dir():
        return {}
    paths = [
        path
        for path in sorted(draft_dir.rglob("*"))
        if path.is_file()
        and path.name != "最终生成确认.json"
        and path.suffix.lower() in {".md", ".json"}
    ]
    screenshot_confirmation = workdir / "截图方式确认.json"
    if screenshot_confirmation.is_file():
        paths.append(screenshot_confirmation)
    screenshot_manifest = workdir / "截图/截图清单.json"
    if screenshot_manifest.is_file():
        paths.append(screenshot_manifest)
        try:
            entries = read_json(screenshot_manifest).get("screenshots") or []
            for entry in entries:
                if not isinstance(entry, dict) or not entry.get("path"):
                    continue
                image_path = Path(str(entry["path"]))
                if not image_path.is_absolute():
                    image_path = screenshot_manifest.parent / image_path
                if image_path.is_file():
                    paths.append(image_path.resolve())
        except Exception:
            pass
    snapshot: dict[str, str] = {}
    resolved_workdir = workdir.resolve()
    for index, path in enumerate(paths, start=1):
        resolved = path.resolve()
        try:
            key = resolved.relative_to(resolved_workdir).as_posix()
        except ValueError:
            key = f"external-screenshot/{index}-{resolved.name}"
        snapshot[key] = file_sha256(resolved)
    return snapshot


PROSE_DOC_FILES = {
    "operation": ("操作手册.md", "操作手册自检记录.md", "操作手册自检记录.json", "_操作手册.docx"),
    "design": ("技术方案文档.md", "技术方案文档自检记录.md", "技术方案文档自检记录.json", "_技术方案文档.docx"),
}

DIAGRAM_PROBE_DOT = "digraph G { 图纸能力检测 -> 渲染输出; }"
DIAGRAM_BACKEND_ORDER = (
    "dot-png",
    "dot-svg-cairosvg",
    "dot-svg-inkscape",
    "dot-svg-librsvg",
    "dot-svg-imagemagick",
)

CJK_FONT_PREFERENCE = (
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "Droid Sans Fallback",
    "AR PL UMing CN",
    "SimHei",
    "Microsoft YaHei",
)

DOT_LAYOUT_DPI = 150

DOT_DEFAULTS_TEMPLATE = (
    'graph [rankdir=TB, nodesep=0.45, ranksep=0.7, splines=ortho, '
    'fontname="{font}", fontsize=12, bgcolor="white", pad="0.3", labeljust=l];\n'
    'node [shape=box, style="rounded,filled", fillcolor="#F5F7FA", color="#4A6FA5", '
    'fontname="{font}", fontsize=12, width=2.2, margin="0.18,0.1"];\n'
    'edge [color="#4A6FA5", fontname="{font}", fontsize=10, arrowsize=0.7];\n'
)

DOT_GRAPH_OPEN_RE = re.compile(r"\b(?:strict\s+)?(?:digraph|graph)\s+[^\s{]+\s*\{")


def detect_cjk_font() -> str | None:
    """Pick a CJK-capable font for DOT text, preferring fonts known to render Chinese."""
    if os.name == "nt":
        return "Microsoft YaHei"
    if sys.platform == "darwin":
        return "PingFang SC"
    try:
        completed = subprocess.run(
            ["fc-list", ":lang=zh", "family"], capture_output=True, text=True, timeout=30, check=False
        )
        if completed.returncode == 0:
            available = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
            for font in CJK_FONT_PREFERENCE:
                if font in available:
                    return font
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _label_lines(value: str) -> list[str]:
    """Split a DOT label into visual lines; \\n, \\l and \\r are all line breaks."""
    return re.split(r"\\[nlr]", value)


def normalize_dot_source(dot_source: str) -> str:
    """Inject canonical layout defaults right after the graph opening brace.

    DOT semantics: later attribute statements override earlier ones, so
    defaults injected before the model's content lose to any explicit
    graph/node/edge statement the model wrote. Orthogonal edges cannot carry
    edge labels (graphviz misplaces them), so diagrams with edge labels get
    polyline splines instead unless the model chose splines explicitly.
    """
    match = DOT_GRAPH_OPEN_RE.search(dot_source)
    if not match:
        return dot_source
    font = detect_cjk_font() or "Droid Sans Fallback"
    has_edge_labels = bool(re.search(r"->[^;\[]*\[[^\]]*label\s*=", dot_source))
    model_chose_splines = bool(re.search(r"\bsplines\s*=", dot_source))
    spline = "polyline" if has_edge_labels and not model_chose_splines else "ortho"
    preamble = DOT_DEFAULTS_TEMPLATE.format(font=font).replace("splines=ortho", f"splines={spline}")
    position = match.end()
    return dot_source[:position] + "\n" + preamble + dot_source[position:]


def lint_dot_source(dot_source: str) -> tuple[list[str], list[str]]:
    """Check DOT source for layout anti-patterns. Returns (blocking, advisory) issues."""
    blocking: list[str] = []
    advisory: list[str] = []
    cleaned = re.sub(r"//[^\n]*", "", dot_source)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)
    for match in re.finditer(r"label\s*=\s*\"((?:[^\"\\]|\\.)*)\"", cleaned):
        for line in _label_lines(match.group(1)):
            if len(line) > 24:
                blocking.append(f"标签单行 {len(line)} 字未换行，渲染会撑宽节点导致排版混乱：{line[:16]}…")
                break
    for match in re.finditer(r'"((?:[^"\\]|\\.)*)"', cleaned):
        prefix = cleaned[max(0, match.start() - 12):match.start()]
        if re.search(r"=\s*$", prefix):
            continue
        for line in _label_lines(match.group(1)):
            if len(line) > 24:
                blocking.append(f"节点名单行 {len(line)} 字未换行，渲染会撑宽节点导致排版混乱：{line[:16]}…")
                break
    for match in re.finditer(r"label\s*=\s*<(.*?)>", cleaned, flags=re.S):
        label = match.group(1)
        if "<BR/>" not in label.upper() and max((len(line) for line in label.splitlines()), default=0) > 24:
            blocking.append("HTML 标签内容过长且缺少 <BR/> 换行，渲染会溢出节点")
    if len(re.findall(r"->", cleaned)) > 12:
        advisory.append(f"连线 {cleaned.count('->')} 条，过多易交叉重叠，建议按层拆分或减少跨层连线")
    if len(re.findall(r"label\s*=", cleaned)) > 4:
        advisory.append("标签文字过多，边标签容易与节点重叠，建议精简或移到正文")
    if not re.search(r"\bsplines\s*=", cleaned):
        advisory.append("未指定 splines，曲线边在密集图中容易互相穿越，建议 splines=ortho")
    return blocking, advisory


def check_png_layout(png_path: Path, *, allow_wide: bool = False) -> list[str]:
    """Return advisory issues for a rendered PNG whose aspect ratio looks unbalanced.

    allow_wide is set for rankdir=LR diagrams where a wide canvas is intended.
    """
    issues: list[str] = []
    try:
        with png_path.open("rb") as handle:
            header = handle.read(33)
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            return issues
        width, height = struct.unpack(">II", header[16:24])
        if width == 0 or height == 0:
            return ["PNG 尺寸异常"]
        ratio = width / height
        if allow_wide:
            if ratio > 6:
                issues.append(
                    f"横向图过于扁平（{width}×{height}，比值 {ratio:.1f}），插入竖版 Word 后文字不可读，"
                    "建议改用 rankdir=TB 或把长链拆成多行"
                )
            elif ratio < 1 / 5:
                issues.append(f"图片宽高比失衡（{width}×{height}），纵向流程图可能拉得过长")
        elif ratio > 3.5 or ratio < 1 / 3.5:
            issues.append(f"图片宽高比失衡（{width}×{height}，比值 {ratio:.1f}），布局可能拉扁或拥挤")
    except OSError:
        issues.append("PNG 无法读取，布局无法校验")
    return issues


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def _run_probe(command: list[str], *, input_bytes: bytes | None = None, stdout_path: Path | None = None) -> bool:
    try:
        if stdout_path is not None:
            with stdout_path.open("wb") as handle:
                completed = subprocess.run(
                    command, input=input_bytes, stdout=handle, stderr=subprocess.PIPE,
                    timeout=120, check=False,
                )
        else:
            completed = subprocess.run(
                command, input=input_bytes, capture_output=True, timeout=120, check=False,
            )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _probe_dot_png(dot: str, probe_dir: Path) -> bool:
    output = probe_dir / "probe.png"
    return _run_probe([dot, "-Tpng"], input_bytes=DIAGRAM_PROBE_DOT.encode("utf-8"), stdout_path=output) and (
        output.is_file() and output.stat().st_size > 0
    )


def _probe_dot_svg(dot: str, probe_dir: Path) -> Path | None:
    output = probe_dir / "probe.svg"
    if not _run_probe([dot, "-Tsvg"], input_bytes=DIAGRAM_PROBE_DOT.encode("utf-8"), stdout_path=output):
        return None
    if not (output.is_file() and output.stat().st_size > 0):
        return None
    return output


def _probe_svg_converter(svg: Path, converter: str, probe_dir: Path) -> bool:
    output = probe_dir / f"probe-{converter}.png"
    if converter == "cairosvg":
        command = [sys.executable, "-m", "cairosvg", str(svg), "-o", str(output)]
    elif converter == "inkscape":
        command = ["inkscape", str(svg), "-o", str(output)]
    elif converter == "librsvg":
        command = ["rsvg-convert", "-o", str(output), str(svg)]
    else:
        command = ["convert", str(svg), str(output)]
    return _run_probe(command) and output.is_file() and output.stat().st_size > 0


def detect_diagram_backends() -> dict[str, Any]:
    """Probe the system for a working DOT -> PNG rendering chain.

    Returns the ordered list of usable backends. The first entry is the
    preferred backend; an empty list means no chain works on this system.
    """
    dot = shutil.which("dot")
    if not dot:
        return {
            "available": False,
            "backend": "none",
            "backends": [],
            "detail": "未安装 graphviz（dot 命令不可用）",
        }
    probe_dir = Path(tempfile.mkdtemp(prefix="diagram-probe-"))
    try:
        backends: list[str] = []
        if _probe_dot_png(dot, probe_dir):
            backends.append("dot-png")
        svg = _probe_dot_svg(dot, probe_dir)
        if svg is not None:
            converters = []
            if _module_available("cairosvg"):
                converters.append("cairosvg")
            if shutil.which("inkscape"):
                converters.append("inkscape")
            if shutil.which("rsvg-convert"):
                converters.append("librsvg")
            if shutil.which("convert"):
                converters.append("imagemagick")
            for converter in converters:
                if _probe_svg_converter(svg, converter, probe_dir):
                    backends.append(f"dot-svg-{converter}")
        if not backends:
            return {
                "available": False,
                "backend": "none",
                "backends": [],
                "detail": "已安装 graphviz 但 PNG/SVG 输出均不可用，且缺少可用的 SVG 转换器"
                "（cairosvg / inkscape / librsvg / imagemagick 任一即可）",
            }
        return {
            "available": True,
            "backend": backends[0],
            "backends": backends,
            "detail": "可用渲染链：" + "、".join(backends),
        }
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def diagram_install_hint() -> str:
    """Return a platform-aware graphviz install command for the current OS."""
    if os.name == "nt":
        return "winget install graphviz（或 choco install graphviz / scoop install graphviz）"
    if sys.platform == "darwin":
        return "brew install graphviz"
    return "sudo apt install graphviz（或对应发行版的包管理器安装 graphviz）"


def detect_archify() -> str | None:
    """Locate the Archify CLI (archify.mjs). Returns the absolute path or None."""
    env_path = os.environ.get("ARCHIFY_PATH")
    if env_path and Path(env_path).is_file():
        return str(Path(env_path).resolve())
    candidates = [
        Path.home() / ".agents" / "skills" / "archify" / "archify" / "bin" / "archify.mjs",
        Path.home() / ".agents" / "skills" / "archify" / "bin" / "archify.mjs",
    ]
    on_path = shutil.which("archify.mjs")
    if on_path:
        candidates.insert(0, Path(on_path))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def archify_install_hint() -> str:
    """Return Archify install guidance."""
    return (
        "安装 Archify：将 Archify 技能目录放置到 ~/.agents/skills/archify/ 后，"
        "脚本会自动检测 archify/bin/archify.mjs。参考："
        "https://github.com/tt-a1i/archify"
    )


def screenshot_html_to_png(html_path: Path, output: Path, *, width: int = 1400, height: int = 1000) -> str | None:
    """Screenshot a self-contained HTML file to PNG via a headless browser.

    Tries Chrome/Chromium headless first (simplest, no extra deps), then falls
    back to Playwright CLI if available. Returns an error description or None.
    """
    browser = _find_chrome()
    if browser:
        return _screenshot_with_chrome(browser, html_path, output, width, height)
    return "无可用的无头浏览器截图 Archify HTML（请安装 google-chrome 或配置 Playwright CLI）"


def _find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _screenshot_with_chrome(browser: str, html_path: Path, output: Path, width: int, height: int) -> str | None:
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="archify-shot-"))
        completed = subprocess.run(
            [browser, "--headless", "--disable-gpu", "--no-sandbox",
             f"--screenshot={output}", f"--window-size={width},{height}",
             "--hide-scrollbars", "--default-background-color=00000000",
             f"file://{html_path.resolve()}"],
            capture_output=True, timeout=120, check=False,
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if completed.returncode != 0 and output.exists():
            output.unlink(missing_ok=True)
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
            return f"Chrome 截图失败：{detail[-1] if detail else f'exit {completed.returncode}'}"
        if not output.is_file() or output.stat().st_size == 0:
            return "Chrome 截图输出为空"
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Chrome 截图异常：{exc}"


def draft_manual_kind(draft_dir: Path) -> str:
    """Return the prose document kind declared by the business context."""
    business = draft_dir / "业务理解.json"
    if not business.is_file():
        return "operation"
    try:
        data = read_json(business)
    except Exception:
        return "operation"
    return "design" if isinstance(data, dict) and data.get("manual_kind") == "design" else "operation"


def draft_completeness_issues(workdir: Path) -> list[str]:
    """Validate that every draft needed by the final builder exists and is coherent."""
    draft_dir = workdir / "草稿"
    kind = draft_manual_kind(draft_dir)
    doc_md, review_md, review_json, _docx_name = PROSE_DOC_FILES[kind]
    required = [
        "业务理解.md",
        "业务理解.json",
        "代码文件选择.json",
        "代码提取清单.md",
        "代码提取清单.json",
        "申请表信息.md",
        doc_md,
        review_md,
        review_json,
    ]
    issues = [f"缺少 草稿/{name}" for name in required if not (draft_dir / name).is_file()]
    other_md = PROSE_DOC_FILES["design" if kind == "operation" else "operation"][0]
    if (draft_dir / other_md).is_file():
        issues.append(f"存在与当前文档类型（{doc_md}）冲突的旧草稿：{other_md}")
    manifest_path = draft_dir / "代码提取清单.json"
    if not manifest_path.is_file():
        return issues
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        issues.append(f"草稿/代码提取清单.json 无法读取：{exc}")
        return issues
    outputs = manifest.get("outputs") if isinstance(manifest, dict) else None
    if not isinstance(outputs, list) or not outputs:
        issues.append("草稿/代码提取清单.json 未声明代码 Markdown 输出")
        return issues
    declared = {str(name) for name in outputs}
    invalid = sorted(declared - KNOWN_CODE_DRAFTS)
    if invalid:
        issues.append("代码提取清单包含未知输出：" + "、".join(invalid))
    for name in sorted(declared & KNOWN_CODE_DRAFTS):
        if not (draft_dir / name).is_file():
            issues.append(f"缺少清单声明的 草稿/{name}")
    stale = sorted(
        name
        for name in (KNOWN_CODE_DRAFTS | STALE_CODE_DRAFTS) - declared
        if (draft_dir / name).exists()
    )
    if stale:
        issues.append("存在与当前代码提取模式冲突的旧草稿：" + "、".join(stale))
    review_path = draft_dir / review_json
    if review_path.is_file():
        try:
            review = read_json(review_path)
            rounds = review.get("rounds") if isinstance(review, dict) else None
            last_issues = rounds[-1].get("issues") if isinstance(rounds, list) and rounds else None
            if isinstance(last_issues, list) and last_issues:
                issues.append(f"{doc_md}自检仍有未解决问题：" + "；".join(str(item) for item in last_issues[:5]))
        except Exception as exc:
            issues.append(f"草稿/{review_json} 无法读取：{exc}")
    return issues


def count_text_lines(path: Path, skip_blank: bool = True) -> int:
    try:
        text = read_text(path)
    except Exception:
        return 0
    if not text:
        return 0
    if skip_blank:
        return sum(1 for line in text.splitlines() if line.strip())
    return len(text.splitlines())


def is_known_config_file(path: Path) -> bool:
    """Return True for well-known config files that shouldn't count as source code."""
    return path.name in KNOWN_CONFIG_FILES


def looks_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:8192]
    except Exception:
        return True
    if not chunk:
        return False
    if path.suffix.lower() in BINARY_EXTS:
        return True
    if chunk.startswith((b"PK\x03\x04", b"%PDF-", b"\x1f\x8b", b"\x89PNG", b"GIF8")):
        return True
    if chunk.startswith((b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return False
    if b"\x00" in chunk:
        return True
    control_count = sum(1 for byte in chunk if byte < 32 and byte not in {9, 10, 12, 13})
    return control_count / len(chunk) > 0.02


def is_document_candidate(path: Path, project: Path | None = None) -> bool:
    """Return True for explicit or strongly signalled project documentation."""
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in DOCUMENT_EXTS or name.startswith(DOCUMENT_FILE_PREFIXES):
        return True
    try:
        display_path = Path(rel(path, project)) if project is not None else path
    except ValueError:
        display_path = path
    directory_names = {part.lower() for part in display_path.parent.parts}
    in_document_directory = bool(directory_names & DOCUMENT_DIR_NAMES)
    hinted_name = any(hint in path.stem.lower() for hint in DOCUMENT_NAME_HINTS)
    return (in_document_directory or (hinted_name and suffix not in KNOWN_SOURCE_HINT_EXTS)) and not looks_binary(path)


def is_source_candidate(path: Path) -> bool:
    """Detect readable source without requiring its language extension to be known."""
    if not path.is_file() or is_known_config_file(path):
        return False
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in DOCUMENT_EXTS | BINARY_EXTS | NON_SOURCE_TEXT_EXTS:
        return False
    if name.startswith(DOCUMENT_FILE_PREFIXES):
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size <= 0 or size > MAX_SOURCE_FILE_BYTES or looks_binary(path):
        return False
    try:
        sample = read_text(path, limit=20_000)
    except Exception:
        return False
    if not sample.strip():
        return False
    if any(len(line) > 3000 for line in sample.splitlines()[:80]):
        return False
    return any(char.isalnum() for char in sample)


def iter_source_files(project: Path) -> Iterable[Path]:
    """Yield source candidates using content detection, not an extension allowlist."""
    for path in iter_project_files(project):
        if is_source_candidate(path):
            yield path


def normalize_title(value: str) -> str:
    value = re.sub(r"[-_]+", " ", value).strip()
    value = re.sub(r"\s+", " ", value)
    return value or "待命名软件"


def safe_filename(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return value or "软件"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
