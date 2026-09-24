from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_docx_from_md import manual_format_commands  # noqa: E402
from common import PROSE_DOC_FILES, draft_completeness_issues, draft_manual_kind  # noqa: E402
from generate_business_context import normalize_model_context  # noqa: E402
from generate_manual_draft import design_quality_issues, render_design_doc  # noqa: E402
from render_design_figures import render_figures  # noqa: E402


LONG_MAIN_FUNCTIONS = (
    "网关固件基于实时操作系统调度多个任务：采集任务周期性轮询传感器节点并解析数据；"
    "通信任务把数据编码后通过消息协议上报服务器，支持断网缓存与自动重连；"
    "指令任务监听总线下行控制帧，校验后驱动外设执行动作并回传结果；"
    "系统维护任务负责看门狗喂狗、运行统计和异常恢复，保证长期无人值守运行的稳定性。"
    "固件将通信参数保存在片内存储参数区，支持在线修改且重启后生效，"
    "并可根据节点类型自动调整轮询间隔，在数据完整性与节点功耗之间取得平衡。"
) * 3


def design_model() -> dict:
    return {
        "manual_kind": "design",
        "product_positioning": "运行于微控制器的智能家居网关固件",
        "industry": "物联网",
        "target_users": ["智能家居集成商"],
        "core_value": "在无主机环境下完成数据采集与控制",
        "business_features": ["传感器采集", "总线下行控制"],
        "business_feature_details": {
            "传感器采集": "周期轮询传感器节点并解析数据。",
            "总线下行控制": "监听控制帧并驱动外设。",
        },
        "operation_flow": ["上电自检", "数据采集", "指令响应"],
        "application_purpose": "为智能家居系统提供数据采集与控制网关",
        "main_functions": LONG_MAIN_FUNCTIONS,
        "technical_characteristics": "基于实时操作系统的多任务架构",
        "software_category": "嵌入式软件",
        "design_spec": {
            "requirements": ["运行在嵌入式环境中", "控制接收机"],
            "conditions": "目标环境为微控制器；开发使用交叉编译工具链；语言为 C。",
            "architecture": "固件分为主控调度、通信和驱动三层。",
            "modules": [
                {"name": "主控调度", "description": "负责任务创建与调度"},
                {"name": "驱动接口", "description": "提供总线读写能力"},
            ],
            "module_note": "上层业务模块依赖驱动接口。",
            "overview": "固件以消息队列为枢纽组织数据流动。",
            "key_designs": [{"title": "自检流程", "description": "上电后依次初始化各模块。", "figure": "流程图"}],
            "functions": [{"title": "采集上报", "description": "采集数据编码后上报。", "figure": "序列图"}],
            "ui_statement": "无。",
            "api_groups": [
                {
                    "title": "功能请求接口",
                    "summary": "基于总线协议的请求应答接口。",
                    "interfaces": [
                        {
                            "signature": "int fullscan(uint fc, uint bandwidth)",
                            "description": "发起一次全频段扫描。",
                            "params": [
                                {"name": "fc", "type": "uint", "detail": "中心频率"},
                                {"name": "bandwidth", "type": "uint", "detail": "带宽"},
                            ],
                            "returns": "返回 0 为成功，其他值为错误码。",
                        }
                    ],
                }
            ],
            "error_handling": [{"title": "日志数据", "description": "异常通过日志输出。"}],
        },
    }


def base_evidence() -> dict:
    return {"software_name": "SmartHub网关软件", "documents": [], "code_evidence": {}}


class DesignModelContextTests(unittest.TestCase):
    def test_design_context_passes_and_normalizes(self) -> None:
        context = normalize_model_context(design_model(), base_evidence(), "")

        self.assertEqual(context["manual_kind"], "design")
        spec = context["design_spec"]
        self.assertEqual(spec["modules"][0]["name"], "主控调度")
        self.assertEqual(spec["api_groups"][0]["interfaces"][0]["params"][1]["name"], "bandwidth")
        self.assertEqual(context["software_category"], "嵌入式软件")

    def test_design_kind_accepts_alias_and_requires_design_spec(self) -> None:
        model = design_model()
        model["manual_kind"] = "设计说明书"
        context = normalize_model_context(model, base_evidence(), "")
        self.assertEqual(context["manual_kind"], "design")

        missing = design_model()
        del missing["design_spec"]
        with self.assertRaises(SystemExit):
            normalize_model_context(missing, base_evidence(), "")

    def test_design_kind_rejects_manual_modules(self) -> None:
        model = design_model()
        model["manual_modules"] = [{"title": "页面"}]
        with self.assertRaises(SystemExit):
            normalize_model_context(model, base_evidence(), "")

    def test_operation_kind_still_requires_manual_modules(self) -> None:
        model = design_model()
        del model["manual_kind"]
        del model["design_spec"]
        with self.assertRaises(SystemExit):
            normalize_model_context(model, base_evidence(), "")


class DesignDocRenderTests(unittest.TestCase):
    def context(self) -> dict:
        return normalize_model_context(design_model(), base_evidence(), "")

    def test_render_design_doc_structure(self) -> None:
        context = self.context()
        text = render_design_doc("SmartHub网关软件", "V1.0", context, context["design_spec"])

        for heading in ("## 一、引言", "## 二、软件总体设计", "### 2.5 模块功能逻辑关系",
                        "## 三、软件功能描述", "### 4.1 软件界面", "### 4.2 API接口"):
            self.assertIn(heading, text)
        self.assertIn("| 主控调度 | 负责任务创建与调度 |", text)
        self.assertIn("int fullscan(uint fc, uint bandwidth)", text)
        self.assertIn("| 2 | bandwidth | uint | 带宽 |", text)
        self.assertIn("无。", text)
        self.assertIn("【图预留：请在此处插入“软件整体结构框架图”。】", text)
        self.assertNotIn("页面", text)
        self.assertEqual(design_quality_issues(text, context["design_spec"]), [])

    def test_design_quality_issues_flag_gui_words(self) -> None:
        context = self.context()
        spec = context["design_spec"]
        text = render_design_doc("SmartHub网关软件", "V1.0", context, spec) + "\n用户点击按钮开始扫描。\n"

        issues = design_quality_issues(text, spec)
        self.assertTrue(any("图形界面" in issue for issue in issues))

    def test_design_figure_placeholder_is_centered(self) -> None:
        children = [
            {"type": "paragraph", "path": "/body/p[1]", "text": "【图预留：请在此处插入“软件整体结构框架图”。】"}
        ]
        commands = manual_format_commands(children, [])
        self.assertEqual(commands[0]["props"]["align"], "center")


class DraftCompletenessDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(__file__).resolve().parent / ".tmp-design-doc"
        shutil.rmtree(self.workdir, ignore_errors=True)
        self.draft_dir = self.workdir / "草稿"
        self.draft_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    def write_full_design_drafts(self) -> None:
        context = normalize_model_context(design_model(), base_evidence(), "")
        (self.draft_dir / "业务理解.json").write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")
        (self.draft_dir / "业务理解.md").write_text("# 业务理解", encoding="utf-8")
        (self.draft_dir / "代码文件选择.json").write_text("{}", encoding="utf-8")
        (self.draft_dir / "代码提取清单.md").write_text("# 清单", encoding="utf-8")
        (self.draft_dir / "代码提取清单.json").write_text(
            json.dumps({"outputs": ["代码-全部.md"]}, ensure_ascii=False), encoding="utf-8"
        )
        (self.draft_dir / "代码-全部.md").write_text("## 第 1 页", encoding="utf-8")
        (self.draft_dir / "申请表信息.md").write_text("➤软件全称：SmartHub网关软件", encoding="utf-8")
        (self.draft_dir / "技术方案文档.md").write_text("# SmartHub网关软件技术方案文档", encoding="utf-8")
        (self.draft_dir / "技术方案文档自检记录.md").write_text("# 自检", encoding="utf-8")
        (self.draft_dir / "技术方案文档自检记录.json").write_text(
            json.dumps({"rounds": [{"round": 1, "issues": []}]}, ensure_ascii=False), encoding="utf-8"
        )

    def test_design_kind_requires_design_drafts(self) -> None:
        self.write_full_design_drafts()
        self.assertEqual(draft_manual_kind(self.draft_dir), "design")
        self.assertEqual(draft_completeness_issues(self.workdir), [])

        (self.draft_dir / "技术方案文档.md").unlink()
        issues = draft_completeness_issues(self.workdir)
        self.assertTrue(any("技术方案文档.md" in issue for issue in issues))

    def test_design_kind_flags_stale_operation_manual(self) -> None:
        self.write_full_design_drafts()
        (self.draft_dir / "操作手册.md").write_text("# 旧操作手册", encoding="utf-8")

        issues = draft_completeness_issues(self.workdir)
        self.assertTrue(any("冲突的旧草稿" in issue and "操作手册.md" in issue for issue in issues))

    def test_operation_kind_requires_manual_drafts(self) -> None:
        self.write_full_design_drafts()
        context = json.loads((self.draft_dir / "业务理解.json").read_text(encoding="utf-8"))
        context["manual_kind"] = "operation"
        (self.draft_dir / "业务理解.json").write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")
        (self.draft_dir / "技术方案文档.md").unlink()
        (self.draft_dir / "技术方案文档自检记录.md").unlink()
        (self.draft_dir / "技术方案文档自检记录.json").unlink()

        self.assertEqual(draft_manual_kind(self.draft_dir), "operation")
        issues = draft_completeness_issues(self.workdir)
        self.assertTrue(any("操作手册.md" in issue for issue in issues))

    def test_prose_doc_file_names(self) -> None:
        self.assertEqual(PROSE_DOC_FILES["design"][0], "技术方案文档.md")
        self.assertEqual(PROSE_DOC_FILES["design"][3], "_技术方案文档.docx")
        self.assertEqual(PROSE_DOC_FILES["operation"][0], "操作手册.md")


class DesignFigureTests(unittest.TestCase):
    def test_render_figures_declared_but_not_rendered_is_flagged(self) -> None:
        context = normalize_model_context(design_model(), base_evidence(), "")
        context["design_spec"]["figures"] = {"architecture": "digraph G { a -> b; }"}
        text = render_design_doc("SmartHub网关软件", "V1.0", context, context["design_spec"])

        issues = design_quality_issues(text, context["design_spec"], [])
        self.assertFalse(any("缺少可见的【图预留】" in issue for issue in issues))
        self.assertIn("【图预留：请在此处插入“软件整体结构框架图”。】", text)

        text_without_placeholder = text.replace("【图预留：请在此处插入“软件整体结构框架图”。】", "")
        issues = design_quality_issues(text_without_placeholder, context["design_spec"], [])
        self.assertTrue(any("缺少可见的【图预留】" in issue for issue in issues))

    def test_render_design_figures_produces_png_and_manifest(self) -> None:
        if not shutil.which("dot"):
            self.skipTest("graphviz dot is not installed")
        workdir = Path(__file__).resolve().parent / ".tmp-design-figures"
        shutil.rmtree(workdir, ignore_errors=True)
        draft_dir = workdir / "草稿"
        draft_dir.mkdir(parents=True)
        try:
            context = normalize_model_context(design_model(), base_evidence(), "")
            context["design_spec"]["figures"] = {
                "architecture": 'digraph G { rankdir=TB; "采集任务" -> "数据队列"; "数据队列" -> "通信任务"; }'
            }
            (draft_dir / "业务理解.json").write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")

            manifest = render_figures(workdir, context)

            self.assertEqual(len(manifest["figures"]), 1)
            self.assertEqual(manifest["figures"][0]["status"], "ok")
            self.assertTrue((draft_dir / manifest["figures"][0]["path"]).is_file())
            manifest_data = json.loads((draft_dir / "图纸清单.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest_data["dot"]["method"], "dot")
            self.assertEqual(manifest_data["figures"][0]["status"], "ok")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def test_render_figures_rejects_unknown_slot_keys(self) -> None:
        context = normalize_model_context(design_model(), base_evidence(), "")
        context["design_spec"]["figures"] = {"page_1": "digraph {}"}
        workdir = Path(__file__).resolve().parent / ".tmp-design-figures-invalid"
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        try:
            with self.assertRaises(SystemExit):
                render_figures(workdir, context)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def test_render_design_doc_embeds_rendered_figures(self) -> None:
        context = normalize_model_context(design_model(), base_evidence(), "")
        figures = [{"key": "architecture", "status": "ok", "path": "图纸/01-architecture.png"}]
        text = render_design_doc("SmartHub网关软件", "V1.0", context, context["design_spec"], figures)

        self.assertIn("![软件整体结构框架图](图纸/01-architecture.png)", text)
        self.assertNotIn("【图预留：请在此处插入“软件整体结构框架图”", text)


if __name__ == "__main__":
    unittest.main()
