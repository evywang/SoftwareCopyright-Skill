from __future__ import annotations

import json
import shutil
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import common  # noqa: E402
from common import (  # noqa: E402
    check_png_layout,
    detect_cjk_font,
    detect_diagram_backends,
    diagram_install_hint,
    lint_dot_source,
    normalize_dot_source,
)
from render_design_figures import _render_with_backend, preferred_backends, render_figures  # noqa: E402


ARCHITECTURE_DOT = 'digraph G { rankdir=TB; "采集任务" -> "数据队列"; "数据队列" -> "通信任务"; }'


def design_business(figures: dict[str, str] | None = None) -> dict:
    spec: dict = {
        "requirements": ["运行在嵌入式环境中"],
        "conditions": "目标环境为微控制器",
        "architecture": "固件分为任务层、服务层和驱动层",
        "modules": [{"name": "主控调度", "description": "负责任务创建与调度"}],
        "overview": "固件以消息队列组织数据流动",
        "functions": [{"title": "采集上报", "description": "采集数据编码后上报"}],
        "api_groups": [{"title": "功能请求接口", "interfaces": [{"signature": "void init(void);", "description": "初始化", "params": [], "returns": "无。"}]}],
        "error_handling": [{"title": "日志数据", "description": "异常通过日志输出"}],
    }
    if figures is not None:
        spec["figures"] = figures
    return {"manual_kind": "design", "design_spec": spec}


class DiagramDetectionTests(unittest.TestCase):
    def test_detect_finds_chain_when_dot_available(self) -> None:
        if not shutil.which("dot"):
            self.skipTest("graphviz dot is not installed")
        result = detect_diagram_backends()
        self.assertTrue(result["available"])
        self.assertIn(result["backend"], common.DIAGRAM_BACKEND_ORDER)

    def test_detect_reports_unavailable_without_dot(self) -> None:
        with patch("shutil.which", return_value=None):
            result = detect_diagram_backends()
        self.assertFalse(result["available"])
        self.assertEqual(result["backend"], "none")
        self.assertEqual(result["backends"], [])
        self.assertIn("graphviz", result["detail"])

    def test_install_hint_is_platform_aware(self) -> None:
        hint = diagram_install_hint()
        self.assertTrue(hint)
        if sys.platform == "darwin":
            self.assertIn("brew", hint)
        elif sys.platform.startswith("linux"):
            self.assertIn("apt", hint)


class BackendDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / ".tmp-diagram-backends"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dot_png_backend_renders(self) -> None:
        if not shutil.which("dot"):
            self.skipTest("graphviz dot is not installed")
        output = self.tmp / "probe.png"
        error, _warnings = _render_with_backend(ARCHITECTURE_DOT, output, "dot-png", self.tmp)
        self.assertIsNone(error)
        self.assertTrue(output.is_file() and output.stat().st_size > 0)

    def test_unknown_backend_returns_error(self) -> None:
        output = self.tmp / "probe.png"
        error, _warnings = _render_with_backend(ARCHITECTURE_DOT, output, "mermaid-cli", self.tmp)
        self.assertIn("未知渲染后端", error)

    def test_svg_converter_backend_renders(self) -> None:
        converters = [
            (shutil.which("inkscape"), "dot-svg-inkscape"),
            (shutil.which("rsvg-convert"), "dot-svg-librsvg"),
            (shutil.which("convert"), "dot-svg-imagemagick"),
        ]
        try:
            import importlib.util

            if importlib.util.find_spec("cairosvg"):
                converters.append((True, "dot-svg-cairosvg"))
        except ImportError:
            pass
        usable = [backend for available, backend in converters if available]
        if not usable:
            self.skipTest("no SVG converter available")
        output = self.tmp / "probe-converted.png"
        error, _warnings = _render_with_backend(ARCHITECTURE_DOT, output, usable[0], self.tmp)
        self.assertIsNone(error)
        self.assertTrue(output.is_file() and output.stat().st_size > 0)


class RenderFiguresBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(__file__).resolve().parent / ".tmp-diagram-render"
        self.draft_dir = self.workdir / "草稿"
        self.draft_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    def test_manifest_records_backend_per_figure(self) -> None:
        if not shutil.which("dot"):
            self.skipTest("graphviz dot is not installed")
        business = design_business({"architecture": ARCHITECTURE_DOT})
        (self.draft_dir / "业务理解.json").write_text(json.dumps(business, ensure_ascii=False), encoding="utf-8")

        manifest = render_figures(self.workdir, business)

        self.assertEqual(len(manifest["figures"]), 1)
        self.assertEqual(manifest["figures"][0]["status"], "ok")
        self.assertIn(manifest["figures"][0]["backend"], common.DIAGRAM_BACKEND_ORDER)
        self.assertTrue((self.draft_dir / manifest["figures"][0]["path"]).is_file())

    def test_preferred_backend_comes_from_env_check(self) -> None:
        if not shutil.which("dot"):
            self.skipTest("graphviz dot is not installed")
        business = design_business({"architecture": ARCHITECTURE_DOT})
        (self.draft_dir / "业务理解.json").write_text(json.dumps(business, ensure_ascii=False), encoding="utf-8")
        preferred = "dot-svg-imagemagick" if shutil.which("convert") else "dot-png"
        (self.workdir / "环境检查.json").write_text(
            json.dumps({"capabilities": {"diagram_backend": preferred}}, ensure_ascii=False), encoding="utf-8"
        )

        self.assertEqual(preferred_backends(self.workdir)[0], preferred)
        manifest = render_figures(self.workdir, business)
        self.assertEqual(manifest["backends"][0], preferred)

    def test_no_backend_yields_error_status_not_fake_success(self) -> None:
        business = design_business({"architecture": ARCHITECTURE_DOT})
        (self.draft_dir / "业务理解.json").write_text(json.dumps(business, ensure_ascii=False), encoding="utf-8")
        (self.workdir / "环境检查.json").write_text(
            json.dumps({"capabilities": {"diagram_backend": "none", "backends": []}}, ensure_ascii=False),
            encoding="utf-8",
        )

        with patch("shutil.which", return_value=None):
            manifest = render_figures(self.workdir, business)

        self.assertEqual(manifest["figures"][0]["status"], "error")
        self.assertIn("graphviz", manifest["figures"][0]["error"])
        self.assertFalse((self.draft_dir / "图纸" / "01-architecture.png").exists())


class DotLayoutQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / ".tmp-dot-layout"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lint_flags_long_unbroken_label_as_blocking(self) -> None:
        bad = 'digraph G { "传感器采集任务负责周期轮询网络中的温湿度人体感应等传感器节点并解析采集数据" -> B; }'
        blocking, _advisory = lint_dot_source(bad)
        self.assertEqual(len(blocking), 1)
        self.assertIn("未换行", blocking[0])

    def test_lint_flags_missing_splines_as_advisory(self) -> None:
        source = 'digraph G { rankdir=LR; nodesep=0.4; ranksep=0.6; A -> B; }'
        blocking, advisory = lint_dot_source(source)
        self.assertEqual(blocking, [])
        self.assertTrue(any("splines" in issue for issue in advisory))

    def test_lint_accepts_well_formed_source(self) -> None:
        source = (
            'digraph G {\n rankdir=TB;\n nodesep=0.45;\n ranksep=0.7;\n splines=ortho;\n'
            '  "采集任务\\n周期轮询" -> "通信任务\\n编码上报";\n}'
        )
        blocking, advisory = lint_dot_source(source)
        self.assertEqual(blocking, [])
        self.assertEqual(advisory, [])

    def test_normalize_injects_defaults_but_model_overrides_win(self) -> None:
        source = 'digraph G {\n rankdir=LR;\n A -> B;\n}'
        normalized = normalize_dot_source(source)
        self.assertIn("nodesep=0.45", normalized)
        self.assertIn("fontname=", normalized)
        self.assertLess(normalized.index("rankdir=TB"), normalized.index("rankdir=LR"))

    def test_normalize_preserves_graph_content(self) -> None:
        source = 'digraph G { A -> B [label="数据"]; }'
        self.assertIn('label="数据"', normalize_dot_source(source))

    def test_detect_cjk_font_finds_chinese_font(self) -> None:
        if sys.platform.startswith("linux") and not shutil.which("fc-list"):
            self.skipTest("fc-list is not available")
        font = detect_cjk_font()
        self.assertTrue(font)

    def test_check_png_layout_flags_extreme_ratio(self) -> None:
        png = self.tmp / "wide.png"
        header = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 2000, 100)
            + b"\x08\x06\x00\x00\x00"
        )
        png.write_bytes(header)
        issues = check_png_layout(png)
        self.assertTrue(any("宽高比" in issue for issue in issues))

    def test_check_png_layout_accepts_balanced_ratio(self) -> None:
        png = self.tmp / "balanced.png"
        header = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 800, 600)
            + b"\x08\x06\x00\x00\x00"
        )
        png.write_bytes(header)
        self.assertEqual(check_png_layout(png), [])

    def test_check_png_layout_allows_wide_for_lr_diagrams(self) -> None:
        def png_with_size(name: str, width: int, height: int) -> Path:
            path = self.tmp / name
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + struct.pack(">II", width, height)
                + b"\x08\x06\x00\x00\x00"
            )
            return path

        moderately_wide = png_with_size("wide-moderate.png", 1800, 500)
        self.assertTrue(any("宽高比" in issue for issue in check_png_layout(moderately_wide)))
        self.assertEqual(check_png_layout(moderately_wide, allow_wide=True), [])

        extreme = png_with_size("wide-extreme.png", 2000, 300)
        self.assertTrue(any("过于扁平" in issue for issue in check_png_layout(extreme, allow_wide=True)))

    def test_render_blocks_long_label_instead_of_ugly_output(self) -> None:
        if not shutil.which("dot"):
            self.skipTest("graphviz dot is not installed")
        workdir = self.tmp / "work"
        draft_dir = workdir / "草稿"
        draft_dir.mkdir(parents=True)
        business = design_business(
            {"architecture": 'digraph G { "传感器采集任务负责周期轮询网络中的温湿度人体感应等传感器节点并解析采集数据" -> B; }'}
        )
        (draft_dir / "业务理解.json").write_text(json.dumps(business, ensure_ascii=False), encoding="utf-8")

        manifest = render_figures(workdir, business)

        self.assertEqual(manifest["figures"][0]["status"], "error")
        self.assertIn("未换行", manifest["figures"][0]["error"])
        self.assertFalse((draft_dir / "图纸" / "01-architecture.png").exists())


if __name__ == "__main__":
    unittest.main()
