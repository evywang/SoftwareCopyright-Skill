#!/usr/bin/env python3
"""Generate a reviewer-oriented operation manual Markdown draft."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import ensure_dir, read_json


def join_items(items: list[str], limit: int = 4) -> str:
    values = [str(item) for item in items if str(item).strip()]
    if not values:
        return "业务用户"
    return "、".join(values[:limit])


def plain_manual_text(text: str) -> str:
    value = text
    replacements = {
        "多 Agent": "多智能体",
        "多 agent": "多智能体",
        "业务逻辑": "使用过程",
        "前端页面": "软件页面",
        "前端": "界面",
        "后端服务": "系统服务",
        "后端": "系统服务",
        "接口": "数据通道",
        "组件": "页面组成部分",
        "路由": "页面入口",
        "状态管理": "状态记录",
        "数据持久化": "数据保存",
        "异步任务": "后台处理任务",
        "任务队列": "任务处理服务",
        "模型": "智能服务",
        "调度中心": "协调中心",
        "结构化依据": "后续说明",
        "高成本生成": "耗时较长的内容生成",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"(?<![A-Za-z])Agent(?![A-Za-z])", "智能体", value)
    value = re.sub(r"(?<![A-Za-z])agent(?![A-Za-z])", "智能体", value)
    value = re.sub(r"\b(?!Node\.js\b)[A-Za-z]+\.js\b", "相关软件能力", value)
    value = re.sub(r"\bReact\b|\bVue\b|\bVite\b|\bNext\b|\bNext\.js\b|\bFastAPI\b|\bLangGraph\b|\bCelery\b|\bSSE\b", "相关软件能力", value)
    value = re.sub(r"相关软件能力、相关软件能力", "相关软件能力", value)
    value = re.sub(r"多智能体\s+协作", "多智能体协作", value)
    return value


def plain_feature_name(name: str) -> str:
    value = plain_manual_text(str(name))
    value = value.replace("Chat", "对话")
    return value.strip() or "核心功能"


TECHNICAL_TERMS = [
    "技术实现",
    "代码实现",
    "源码结构",
    "框架",
    "接口封装",
    "状态管理",
    "异步任务",
    "任务队列",
    "数据持久化",
    "业务逻辑",
    "React",
    "Next.js",
    "FastAPI",
    "LangGraph",
    "Celery",
]

TEMPLATE_MARKERS = [
    "重要功能之一",
    "通过清晰的页面入口、信息展示和结果反馈",
    "对应操作环节",
    "审核时可重点查看",
    "审核人员可通过",
    "按照页面提示填写内容、选择资料、确认方案或点击提交按钮",
    "系统处理完成后显示结果或提示信息",
    "帮助用户用户",
    "帮助用户系统",
    "主要用于在",
    "项目管理或资产中心项目管理",
    "进入方式：",
    "页面内容：",
    "操作步骤：",
    "操作规则：",
    "操作结果与反馈：",
    "功能特点根据当前项目资料",
    "软件围绕",
]

AI_TONE_MARKERS = [
    "旨在",
    "赋能",
    "一站式",
    "智能化",
    "高效便捷",
    "显著提升",
    "强大能力",
    "丰富功能",
    "极大地",
    "全方位",
    "多维度",
    "闭环",
    "降本增效",
    "优化体验",
    "提升效率",
]


def manual_section_body(text: str, title: str) -> str:
    number_pattern = r"(?:\(\d+\)、|[零一二三四五六七八九十百]+、)"
    pattern = re.compile(rf"^##\s+{number_pattern}\s*{re.escape(title)}\s*$", flags=re.M)
    match = pattern.search(text)
    if not match:
        return ""
    next_match = re.search(rf"^##\s+{number_pattern}", text[match.end() :], flags=re.M)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.end() : end].strip()


def manual_quality_issues(text: str, modules: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    required_sections = ["相关文档", "说明", "功能特点", "系统要求", "常见问题解答", "术语表"]
    for title in required_sections:
        if not manual_section_body(text, title):
            issues.append(f"缺少通用手册章节：{title}")
    if re.search(r"^##\s+\(\d+\)、", text, flags=re.M):
        issues.append("章节标题仍使用括号数字，应使用中文大写序号")
    related_body = manual_section_body(text, "相关文档")
    if related_body and "| 文档名称 |" not in related_body:
        issues.append("相关文档章节应使用表格指向配套文档")
    for term in TECHNICAL_TERMS:
        if term in text:
            issues.append(f"存在偏技术表达：{term}")
    for marker in TEMPLATE_MARKERS:
        if marker in text:
            issues.append(f"存在模板化表达：{marker}")
    for marker in AI_TONE_MARKERS:
        if marker in text:
            issues.append(f"存在疑似 AI 味/空泛表达：{marker}")
    if text.count("【截图预留：") < len(modules):
        issues.append("截图预留数量少于核心模块数量")
    list_lines = [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^(?:[-*+]\s+|\d+\.\s+)", line.strip())
    ]
    if list_lines:
        issues.append(f"正文仍存在项目符号或编号列表：{list_lines[0][:40]}")
    for module in modules:
        title = str(module.get("feature") or "").strip()
        if not title:
            continue
        body = manual_section_body(text, title)
        if not body:
            issues.append(f"缺少核心模块章节：{title}")
            continue
        if len(body) < 390:
            issues.append(f"模块内容偏薄：{title}")
        for label in ("进入方式：", "页面内容：", "操作步骤：", "操作规则：", "操作结果与反馈："):
            if label in body:
                issues.append(f"模块仍使用制式小标题：{title} / {label}")
    return issues


def clean_field(value: str, default: str) -> str:
    text = plain_manual_text(str(value or "")).strip()
    if not text or text == "待用户确认":
        return default
    return text + ("。" if not text.endswith(("。", "！", "？")) else "")


def as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [plain_manual_text(str(item)).strip() for item in value if str(item).strip()]
    text = plain_manual_text(str(value)).strip()
    if not text:
        return []
    return [item.strip() for item in re.split(r"[；;\n]+", text) if item.strip()]


def required_module_text(item: dict[str, Any], field: str, title: str) -> str:
    value = plain_manual_text(str(item.get(field) or "")).strip()
    if not value:
        raise SystemExit(
            "STOP_FOR_USER\n"
            f"NEXT_ACTION: 操作手册页面模块“{title}”缺少 `{field}`。请回到业务理解阶段，"
            "由模型根据真实页面证据补全 manual_modules 后再生成操作手册。"
        )
    return value


def required_module_list(item: dict[str, Any], field: str, title: str) -> list[str]:
    values = as_text_list(item.get(field))
    if not values:
        raise SystemExit(
            "STOP_FOR_USER\n"
            f"NEXT_ACTION: 操作手册页面模块“{title}”缺少 `{field}`。请回到业务理解阶段，"
            "由模型根据真实页面证据补全 manual_modules 后再生成操作手册。"
        )
    return values


def normalize_manual_modules(
    business: dict[str, Any] | None,
    fallback_modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    manual_modules = business.get("manual_modules") if business else []
    if not manual_modules:
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 业务理解缺少 `manual_modules`。不要由脚本按 auth/query/form 等模板猜测操作手册。"
            "请模型阅读项目真实页面、路由、按钮、输入项、提示和结果反馈，补全 manual_modules 后再生成操作手册。"
        )

    modules: list[dict[str, Any]] = []
    for index, item in enumerate(manual_modules, start=1):
        if not isinstance(item, dict):
            raise SystemExit(
                "STOP_FOR_USER\n"
                f"NEXT_ACTION: manual_modules 第 {index} 项不是对象，无法生成真实操作手册。请补全 title、purpose、entry、operation_steps、feedback 等字段。"
            )
        title = plain_feature_name(item.get("title") or item.get("feature") or f"功能模块 {index}")
        purpose = required_module_text(item, "purpose", title)
        entry = required_module_text(item, "entry", title)
        usage = plain_manual_text(
            str(item.get("usage") or item.get("usage_scenario") or item.get("description") or "")
        ).strip()
        if not usage:
            raise SystemExit(
                "STOP_FOR_USER\n"
                f"NEXT_ACTION: 操作手册页面模块“{title}”缺少 `usage` 或 `usage_scenario`。请回到业务理解阶段，"
                "补充用户在什么场景下会使用该页面、处理什么具体事务，再生成操作手册。"
            )
        steps = required_module_list(item, "operation_steps", title)
        feedback = required_module_list(item, "feedback", title)
        screenshot_note = plain_manual_text(str(item.get("screenshot") or "")).strip()
        if not screenshot_note:
            screenshot_note = f"请在此处插入“{title}”页面或操作结果截图"
        modules.append(
            {
                "feature": title,
                "raw_feature": title,
                "purpose": purpose + ("。" if not purpose.endswith(("。", "！", "？")) else ""),
                "entry": entry + ("。" if not entry.endswith(("。", "！", "？")) else ""),
                "usage": usage,
                "visible_elements": as_text_list(item.get("visible_elements") or item.get("page_elements")),
                "steps": steps,
                "validation_rules": as_text_list(item.get("validation_rules") or item.get("rules") or item.get("limits")),
                "feedback": feedback,
                "result": "；".join(feedback),
                "screenshot": f"【截图预留：{screenshot_note.strip('。')}。】",
            }
        )
    return modules


def normalize_system_requirements(business: dict[str, Any] | None) -> list[dict[str, str]]:
    raw_items = business.get("system_requirements") if business else None
    rows: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                name = str(item.get("item") or item.get("name") or "").strip()
                minimum = str(item.get("minimum") or item.get("min") or "").strip()
                recommended = str(item.get("recommended") or item.get("recommend") or "").strip()
                if name:
                    rows.append(
                        {
                            "item": plain_manual_text(name),
                            "minimum": plain_manual_text(minimum or "按实际部署环境配置"),
                            "recommended": plain_manual_text(recommended or minimum or "按实际部署环境配置"),
                        }
                    )
    if not rows:
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 业务理解缺少 `system_requirements`。请根据真实项目运行形态和已确认申请表环境补全后再生成操作手册。"
        )
    return rows


def normalize_faq(business: dict[str, Any] | None, software_name: str) -> list[dict[str, str]]:
    raw_items = business.get("faq") if business else None
    items: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                question = str(item.get("question") or item.get("q") or "").strip()
                answer = str(item.get("answer") or item.get("a") or "").strip()
                if question and answer:
                    items.append({"question": plain_manual_text(question), "answer": plain_manual_text(answer)})
    if not items:
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 业务理解缺少 `faq`。请根据当前软件真实使用场景补全常见问题后再生成操作手册。"
        )
    return items


def normalize_glossary(business: dict[str, Any] | None, modules: list[dict[str, Any]], software_name: str) -> list[dict[str, str]]:
    raw_items = business.get("glossary") if business else None
    items: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                term = str(item.get("term") or item.get("name") or "").strip()
                definition = str(item.get("definition") or item.get("description") or "").strip()
                if term and definition:
                    items.append({"term": plain_manual_text(term), "definition": plain_manual_text(definition)})
    if items:
        return items
    raise SystemExit(
        "STOP_FOR_USER\n"
        "NEXT_ACTION: 业务理解缺少 `glossary`。请根据当前软件真实业务对象和页面术语补全术语表后再生成操作手册。"
    )


def chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value <= 0:
        return str(value)
    if value < 10:
        return digits[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + digits[value % 10]
    if value < 100:
        tens, ones = divmod(value, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    return str(value)


def section_heading(index: int, title: str) -> str:
    return f"## {chinese_number(index)}、{title}"


def strip_sentence_punctuation(text: str) -> str:
    return str(text or "").strip().strip("。；;，, ")


def natural_join(items: list[str], limit: int | None = None) -> str:
    values = [strip_sentence_punctuation(item) for item in items if strip_sentence_punctuation(item)]
    if limit is not None:
        values = values[:limit]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "、".join(values[:-1]) + "和" + values[-1]


def ensure_sentence(text: str) -> str:
    value = strip_sentence_punctuation(plain_manual_text(text))
    if not value:
        return ""
    return value + "。"


def remove_opening_definition(text: str, software_name: str) -> str:
    value = plain_manual_text(text).strip()
    if not value:
        return ""
    sentences = re.findall(r"[^。！？]+[。！？]?", value)
    if sentences and sentences[0].startswith(software_name) and "是一款" in sentences[0]:
        sentences = sentences[1:]
    return "".join(sentences).strip()


def flow_summary(flow: list[str], modules: list[dict[str, Any]]) -> str:
    if flow:
        pieces = [strip_sentence_punctuation(plain_manual_text(item)) for item in flow[:4]]
        pieces = [item for item in pieces if item]
        if pieces:
            return "；".join(pieces) + "。"
    names = [module["feature"] for module in modules[:4]]
    if names:
        return f"用户可依次使用{natural_join(names)}等页面完成主要工作。"
    return "用户可按照页面提示完成主要业务操作。"


def describe_related_doc(name: str) -> str:
    if "总体" in name:
        return "说明软件整体功能、页面组成、运行环境和业务边界。"
    if "详细" in name:
        return "说明各功能页面、输入输出、状态变化和处理规则。"
    if "测试" in name or "案例" in name:
        return "记录主要功能的操作场景、预期结果和异常提示。"
    return "记录与本软件功能、操作或验证相关的配套说明。"


def normalize_related_documents(business: dict[str, Any] | None) -> list[dict[str, str]]:
    raw_items = business.get("related_documents") if business else None
    rows: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or item.get("document") or "").strip()
                target = str(item.get("target") or item.get("path") or item.get("file") or "").strip()
                description = str(item.get("description") or item.get("purpose") or "").strip()
                if name:
                    rows.append(
                        {
                            "name": plain_manual_text(name),
                            "target": plain_manual_text(target or f"《{name}》"),
                            "description": plain_manual_text(description or describe_related_doc(name)),
                        }
                    )
            elif str(item).strip():
                name = str(item).strip()
                rows.append(
                    {
                        "name": plain_manual_text(name),
                        "target": f"《{plain_manual_text(name)}》",
                        "description": describe_related_doc(name),
                    }
                )
    if not rows:
        for name in ("总体设计", "详细设计", "测试案例"):
            rows.append({"name": name, "target": f"《{name}》", "description": describe_related_doc(name)})
    return rows


def clean_purpose_text(feature: str, purpose: str) -> str:
    value = strip_sentence_punctuation(plain_manual_text(purpose))
    value = re.sub(rf"^{re.escape(feature)}(页面|功能|模块|环节)?(主要)?用于", "", value)
    value = re.sub(r"^[^，。；;]{1,30}(页面|功能|模块|环节|状态栏|面板)?(主要)?用于", "", value)
    value = re.sub(r"^用于", "", value)
    value = value.strip("。；;，, ")
    return value or "完成本页面相关操作"


def page_label(feature: str) -> str:
    value = strip_sentence_punctuation(feature)
    if value.startswith("用户") and len(value) > 2:
        value = value[2:]
    return value


def purpose_core_sentence(feature: str, purpose: str) -> str:
    value = clean_purpose_text(feature, purpose)
    label = page_label(feature)
    if re.match(r"^(展示|集中展示|承载|提供|处理|保存|记录|辅助)", value):
        return f"{label}页面{value}"
    if value.startswith("让用户"):
        return f"{label}页面{value}"
    return f"用户可在{label}页面{value}"


def purpose_sentence(feature: str, purpose: str) -> str:
    return purpose_core_sentence(feature, purpose) + "。"


def entry_sentence(entry: str) -> str:
    value = strip_sentence_punctuation(plain_manual_text(entry))
    if not value:
        return ""
    if value.startswith("用户"):
        return value + "。"
    if re.match(r"^(登录|创建|进入|打开|点击|完成|选择|提交)", value):
        return f"用户{value}。"
    if value.startswith("当"):
        return value + "。"
    return f"用户可以通过{value}。"


def visible_elements_sentence(items: list[str], feature: str, index: int) -> str:
    value = natural_join(items, limit=8)
    if not value:
        return ""
    variants = [
        f"页面上主要呈现{value}等内容，这些内容用于帮助用户确认当前位置和可执行操作。",
        f"用户在{feature}页面会看到{value}等信息，并可依据页面显示继续处理。",
        f"该部分提供{value}等页面内容，用户可据此查看状态、填写信息或选择下一步操作。",
    ]
    return variants[(index - 1) % len(variants)]


def steps_sentence(steps: list[str], module_index: int) -> str:
    values = [strip_sentence_punctuation(step) for step in steps if strip_sentence_punctuation(step)]
    if not values:
        return ""
    connectors = ["先", "随后", "接着", "之后", "再", "继续"]
    parts: list[str] = []
    for step_index, step in enumerate(values):
        if step_index == len(values) - 1 and len(values) > 1:
            connector = "最后"
        else:
            connector = connectors[min(step_index, len(connectors) - 1)]
        parts.append(f"{connector}{step}")
    prefixes = ["实际操作时，用户", "使用该功能时，用户", "在该页面中，用户"]
    return prefixes[(module_index - 1) % len(prefixes)] + "，".join(parts) + "。"


def rules_feedback_sentence(rules: list[str], feedback: list[str], index: int) -> str:
    parts: list[str] = []
    rule_text = natural_join(rules, limit=6)
    if rule_text:
        rule_templates = [
            f"操作过程中需要注意{rule_text}。",
            f"页面会按照{rule_text}等规则限制或提示用户。",
            f"如果不满足{rule_text}等要求，用户需要根据页面提示调整后再继续。",
        ]
        parts.append(rule_templates[(index - 1) % len(rule_templates)])
    feedback_text = natural_join(feedback, limit=6)
    if feedback_text:
        feedback_templates = [
            f"操作完成后，系统会显示{feedback_text}。",
            f"处理结束后，用户可以看到{feedback_text}。",
            f"页面反馈通常包括{feedback_text}。",
        ]
        parts.append(feedback_templates[(index - 1) % len(feedback_templates)])
    return "".join(parts)


def feature_paragraph(module: dict[str, Any], index: int) -> str:
    feature = module["feature"]
    purpose = clean_purpose_text(feature, module.get("purpose") or "")
    label = page_label(feature)
    core = purpose_core_sentence(feature, module.get("purpose") or "")
    elements = natural_join(as_text_list(module.get("visible_elements")), limit=5)
    feedback = natural_join(as_text_list(module.get("feedback")), limit=3)
    variants = [
        f"{core}。页面上的{elements or '相关业务信息'}会集中呈现当前可操作内容，用户处理完成后可以看到{feedback or '相应的处理结果'}。",
        f"在{label}页面中，用户主要处理{purpose}。系统把{elements or '页面显示内容'}放在当前操作区域，处理结束后会反馈{feedback or '处理结果'}。",
        f"{label}页面关注的是{purpose}。用户通过{elements or '必要的页面信息'}确认当前状态，并在操作结束后获得{feedback or '当前状态反馈'}。",
    ]
    return variants[(index - 1) % len(variants)]


def tidy_manual_output(text: str) -> str:
    replacements = {
        "用户主要处理处理": "用户主要处理",
        "主要处理承载一次": "主要围绕一次",
        "用户可以看到用户可以看到": "用户可以看到",
        "处理结束后会反馈空对话": "处理结束后会显示空对话",
        "在AI ": "在 AI ",
        "把StudioAgent": "把 StudioAgent",
        "页面上的StudioAgent": "页面上的 StudioAgent",
        "看到StudioAgent": "看到 StudioAgent",
        "提供StudioAgent": "提供 StudioAgent",
        "进入StudioAgent": "进入 StudioAgent",
        "保证StudioAgent": "保证 StudioAgent",
    }
    value = text
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"(?<=[\u4e00-\u9fff])([A-Za-z][A-Za-z0-9.+-]*)(?=[\u4e00-\u9fff])", r" \1 ", value)
    value = re.sub(r" {2,}", " ", value)
    return value


def append_modules_canonical(lines: list[str], modules: list[dict[str, Any]], start_index: int) -> int:
    for i, module in enumerate(modules, start=start_index):
        visible_elements = as_text_list(module.get("visible_elements"))
        validation_rules = as_text_list(module.get("validation_rules"))
        feedback = as_text_list(module.get("feedback")) or [module["result"]]
        lines.extend(
            [
                section_heading(i, module["feature"]),
                "",
                purpose_sentence(module["feature"], module["purpose"]) + entry_sentence(module["entry"]),
                "",
            ]
        )
        if module.get("usage"):
            lines.extend([ensure_sentence(module["usage"]), ""])
        element_text = visible_elements_sentence(visible_elements, module["feature"], i)
        if element_text:
            lines.extend([element_text, ""])
        step_text = steps_sentence(module["steps"], i)
        if step_text:
            lines.extend([step_text, ""])
        rule_feedback = rules_feedback_sentence(validation_rules, feedback, i)
        if rule_feedback:
            lines.extend([rule_feedback, ""])
        lines.extend(["", module["screenshot"], ""])
    return start_index + len(modules)


def append_flow_canonical(lines: list[str], software_name: str, flow: list[str], start_index: int) -> int:
    lines.extend(
        [
            section_heading(start_index, "典型使用流程"),
            "",
            f"用户完成一次完整业务时，通常先进入{software_name}，再选择或创建业务对象，随后按照页面提示处理内容并查看结果。",
            "",
            flow_summary(flow, []),
            "",
        ]
    )
    return start_index + 1


DESIGN_GUI_WORDS = ("页面", "点击", "按钮", "弹窗", "下拉", "菜单", "登录", "输入框", "截图预留")
DESIGN_REQUIRED_HEADINGS = (
    "## 一、引言",
    "## 二、软件总体设计",
    "### 2.1 软件需求概括",
    "### 2.2 需求概述",
    "### 2.3 条件与限制",
    "### 2.4 总体结构和模块接口设计",
    "### 2.5 模块功能逻辑关系",
    "### 2.6 设计和描述",
    "## 三、软件功能描述",
    "## 四、接口设计",
    "### 4.1 软件界面",
    "### 4.2 API接口",
    "### 4.4 出错处理设计",
)


def normalize_design_spec_from_business(business: dict[str, Any]) -> dict[str, Any]:
    """Validate the design spec in the confirmed business context before rendering."""
    spec = business.get("design_spec")
    if not isinstance(spec, dict):
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 业务理解缺少 `design_spec`。无界面软件（manual_kind=design）必须由模型按真实项目设计"
            "补全 design_spec（需求、条件与限制、总体结构、模块表、功能设计、接口设计、出错处理）后再生成技术方案文档。"
        )
    for field in ("requirements", "conditions", "architecture", "modules", "overview", "functions", "api_groups", "error_handling"):
        value = spec.get(field)
        if field in ("requirements", "modules", "functions", "api_groups", "error_handling"):
            valid = isinstance(value, list) and bool(value)
        else:
            valid = bool(str(value or "").strip())
        if not valid:
            raise SystemExit(
                "STOP_FOR_USER\n"
                f"NEXT_ACTION: design_spec.{field} 不能为空。请模型按真实项目设计补全后再生成技术方案文档。"
            )
    return spec


def interface_short_name(signature: str) -> str:
    match = re.match(r"^[A-Za-z_][\w\s\*&:<>,]*?\b([A-Za-z_]\w*)\s*\(", signature.strip())
    if match:
        return match.group(1)
    return signature.strip()[:40]


def rendered_figure(figures: list[dict[str, Any]] | None, key: str) -> dict[str, Any] | None:
    for figure in figures or []:
        if isinstance(figure, dict) and figure.get("key") == key and figure.get("status") == "ok":
            return figure
    return None


def figure_markup(
    figures: list[dict[str, Any]] | None,
    key: str,
    title: str,
    figure_text: str,
    default_placeholder: str = "",
) -> str:
    rendered = rendered_figure(figures, key)
    if rendered:
        return f"![{title}]({rendered['path']})"
    if str(figure_text or "").strip():
        return f"【图预留：请在此处插入“{title}”{figure_text}。】"
    return default_placeholder


def rendered_sequence(sequences: list[dict[str, Any]] | None, sequence_id: str) -> dict[str, Any] | None:
    for sequence in sequences or []:
        if isinstance(sequence, dict) and sequence.get("key") == sequence_id and sequence.get("status") == "ok":
            return sequence
    return None


def sequence_markup(sequences: list[dict[str, Any]] | None, sequence_id: str, title: str) -> str:
    rendered = rendered_sequence(sequences, sequence_id)
    if rendered:
        return f"![{title}]({rendered['path']})"
    return f"【图预留：请在此处插入“{title}”时序图。】"


def render_design_doc(
    software_name: str,
    version: str,
    business: dict[str, Any],
    spec: dict[str, Any],
    figures: list[dict[str, Any]] | None = None,
    sequences: list[dict[str, Any]] | None = None,
) -> str:
    positioning = plain_manual_text(business.get("product_positioning") or "")
    if positioning and not positioning.endswith("。"):
        positioning += "。"
    features = [plain_manual_text(item) for item in (business.get("business_features") or []) if str(item).strip()]

    lines: list[str] = [f"# {software_name}技术方案文档", ""]

    lines.extend(["## 一、引言", ""])
    lines.append(f"本技术方案文档提供了对{software_name} {version}软件静态和动态形态的描述，是软件编码过程中的指导文档。")
    intro_note = str(spec.get("intro_note") or "").strip()
    if intro_note:
        lines.extend(["", intro_note])

    lines.extend(["", "## 二、软件总体设计", ""])
    lines.extend(["### 2.1 软件需求概括", ""])
    if positioning:
        lines.extend([positioning, ""])
    if features:
        lines.extend([f"{software_name} {version}主要有以下几方面的功能：", ""])
        for index, feature in enumerate(features, start=1):
            lines.append(f"（{index}）{feature}；")
        lines.append("")

    lines.extend(["### 2.2 需求概述", ""])
    requirements = [str(item).strip() for item in spec.get("requirements") or [] if str(item).strip()]
    for index, item in enumerate(requirements, start=1):
        lines.append(f"{index}. {item}")
    lines.append("")

    lines.extend(["### 2.3 条件与限制", ""])
    lines.extend([str(spec.get("conditions") or "").strip(), ""])

    lines.extend(["### 2.4 总体结构和模块接口设计", ""])
    lines.extend([str(spec.get("architecture") or "").strip(), ""])
    architecture_markup = figure_markup(
        figures, "architecture", "软件整体结构框架图", "",
        default_placeholder="【图预留：请在此处插入“软件整体结构框架图”。】",
    )
    if architecture_markup:
        lines.extend([architecture_markup, ""])

    lines.extend(["### 2.5 模块功能逻辑关系", ""])
    lines.append("软件详细的模块信息如下表所示：")
    lines.extend(["", "| 模块名 | 功能描述 |", "| --- | --- |"])
    for module in spec.get("modules") or []:
        name = str(module.get("name") or "").strip()
        description = str(module.get("description") or "").strip()
        lines.append(f"| {name} | {description} |")
    module_note = str(spec.get("module_note") or "").strip()
    lines.append("")
    if module_note:
        lines.extend([module_note, ""])

    lines.extend(["### 2.6 设计和描述", ""])
    lines.extend([str(spec.get("overview") or "").strip(), ""])
    for index, item in enumerate(spec.get("key_designs") or [], start=1):
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        lines.extend([f"#### 2.6.{index} {title}", "", description, ""])
        key_markup = figure_markup(figures, f"key_{index}", title, str(item.get("figure") or ""))
        if key_markup:
            lines.extend([key_markup, ""])

    lines.extend(["## 三、软件功能描述", ""])
    for index, item in enumerate(spec.get("functions") or [], start=1):
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        lines.extend([f"### 3.{index} {title}", "", description, ""])
        function_markup = figure_markup(figures, f"function_{index}", title, str(item.get("figure") or ""))
        if function_markup:
            lines.extend([function_markup, ""])

    lines.extend(["## 四、接口设计", ""])
    lines.extend(["### 4.1 软件界面", ""])
    lines.extend([str(spec.get("ui_statement") or "无。").strip(), ""])

    lines.extend(["### 4.2 API接口", ""])
    for group_index, group in enumerate(spec.get("api_groups") or [], start=1):
        group_title = str(group.get("title") or "").strip()
        summary = str(group.get("summary") or "").strip()
        lines.extend([f"#### 4.2.{group_index} {group_title}", ""])
        if summary:
            lines.extend([summary, ""])
        for iface_index, iface in enumerate(group.get("interfaces") or [], start=1):
            signature = str(iface.get("signature") or "").strip()
            description = str(iface.get("description") or "").strip()
            params = iface.get("params") or []
            returns = str(iface.get("returns") or "").strip()
            lines.extend([f"##### 4.2.{group_index}.{iface_index} {interface_short_name(signature)}", ""])
            lines.extend(["**接口名称**", "", signature, ""])
            lines.extend(["**接口说明**", "", description, ""])
            lines.extend(["**参数说明**", ""])
            if params:
                lines.extend(["| 序号 | 参数名称 | 类型 | 取值说明 |", "| --- | --- | --- | --- |"])
                for param_index, param in enumerate(params, start=1):
                    lines.append(
                        f"| {param_index} | {param.get('name', '')} | {param.get('type', '')} | {param.get('detail', '')} |"
                    )
            else:
                lines.append("无。")
                lines.append("")
                lines.extend(["**返回结果**", "", returns or "无。", ""])

    if spec.get("sequences"):
        lines.extend(["### 4.3 时序图", ""])
        for index, item in enumerate(spec["sequences"], start=1):
            sequence_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            lines.extend([f"#### 4.3.{index} {title}", ""])
            lines.extend([sequence_markup(sequences, sequence_id, title), ""])

    lines.extend(["### 4.4 出错处理设计", ""])
    for index, item in enumerate(spec.get("error_handling") or [], start=1):
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        lines.extend([f"#### 4.3.{index} {title}", "", description, ""])

    lines.extend(
        [
            "```text",
            "STOP_FOR_USER",
            "NEXT_ACTION: 请一次性确认完整技术方案文档草稿是否与真实设计一致；必要时先统一修改段落内容，再运行 confirm_stage.py --stage markdown。",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def append_sequence_quality_issues(issues: list[str], text: str, spec: dict[str, Any], sequences: list[dict[str, Any]] | None) -> None:
    declared_ids = [str(item.get("id") or "").strip() for item in (spec.get("sequences") or []) if str(item.get("id") or "").strip()]
    if not declared_ids:
        return
    rendered_ids = {
        str(sequence.get("key") or "")
        for sequence in sequences or []
        if isinstance(sequence, dict) and sequence.get("status") == "ok"
    }
    missing = [sequence_id for sequence_id in declared_ids if sequence_id not in rendered_ids]
    if missing:
        issues.append("声明了序列图但未渲染成功：" + "、".join(missing) + "；正文保留【图预留】占位")
    if declared_ids and "4.3 时序图" not in text and "【图预留" not in text:
        issues.append("缺少序列图章节（4.3 时序图）")


def design_quality_issues(
    text: str, spec: dict[str, Any], figures: list[dict[str, Any]] | None = None,
    sequences: list[dict[str, Any]] | None = None,
) -> list[str]:
    issues: list[str] = []
    for heading in DESIGN_REQUIRED_HEADINGS:
        if heading not in text:
            issues.append(f"缺少必备章节标题：{heading}")
    found_gui_words = sorted({word for word in DESIGN_GUI_WORDS if word in text})
    if found_gui_words:
        issues.append(
            "正文出现面向图形界面的词汇（" + "、".join(found_gui_words) + "）；无界面软件的技术方案文档不应描述页面或界面操作，请改写为设备/模块行为"
        )
    for module in spec.get("modules") or []:
        name = str(module.get("name") or "").strip()
        if name and f"| {name} |" not in text:
            issues.append(f"模块信息表缺少模块行：{name}")
    declared_figure_keys = [str(key) for key in (spec.get("figures") or {}) if str(key).strip()]
    if declared_figure_keys:
        rendered_keys = {
            str(figure.get("key") or "")
            for figure in figures or []
            if isinstance(figure, dict) and figure.get("status") == "ok"
        }
        missing = [key for key in declared_figure_keys if key not in rendered_keys]
        if text.count("【图预留") < len(missing):
            issues.append("声明的架构图/流程图缺少可见的【图预留】占位说明")
    declared_slots = [("architecture", "结构框架图")]
    for index, item in enumerate(spec.get("key_designs") or [], start=1):
        if str(item.get("figure") or "").strip():
            declared_slots.append((f"key_{index}", str(item["figure"])))
    for index, item in enumerate(spec.get("functions") or [], start=1):
        if str(item.get("figure") or "").strip():
            declared_slots.append((f"function_{index}", str(item["figure"])))
    rendered_keys = {
        str(figure.get("key") or "")
        for figure in figures or []
        if isinstance(figure, dict) and figure.get("status") == "ok"
    }
    unrendered = [key for key, _figure in declared_slots if key not in rendered_keys]
    if text.count("【图预留") < len(unrendered):
        issues.append("声明的架构图/流程图缺少可见的【图预留】占位说明")
    for group in spec.get("api_groups") or []:
        for iface in group.get("interfaces") or []:
            signature = str(iface.get("signature") or "").strip()
            if signature and signature not in text:
                issues.append(f"接口设计缺少接口签名：{interface_short_name(signature)}")
    append_sequence_quality_issues(issues, text, spec, sequences)
    for leftover in ("待用户确认", "按项目实际填写"):
        if leftover in text:
            issues.append(f"正文残留占位文字：{leftover}")
    return issues


def build_design_text(
    analysis: dict[str, Any],
    software_name: str,
    version: str,
    business: dict[str, Any],
    spec: dict[str, Any],
    figures: list[dict[str, Any]] | None = None,
    sequences: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    text = render_design_doc(software_name, version, business, spec, figures, sequences)
    records = [
        {"round": 1, "action": "初稿生成", "issues": design_quality_issues(text, spec, figures, sequences)},
        {"round": 2, "action": "设计要素复核", "issues": design_quality_issues(text, spec, figures, sequences)},
        {"round": 3, "action": "界面词汇与结构复核", "issues": design_quality_issues(text, spec, figures, sequences)},
    ]
    if records[-1]["issues"]:
        records.append(
            {
                "round": 4,
                "action": "复核仍需模型回到业务理解补写",
                "issues": design_quality_issues(text, spec, figures, sequences),
            }
        )
    return text, records


def collect_layout_notes(manifest: dict[str, Any]) -> list[str]:
    """Collect advisory layout notes from the figure/sequence manifest for the self-check record."""
    notes: list[str] = []
    for figure in manifest.get("figures") or []:
        if figure.get("status") != "ok":
            continue
        for issue in figure.get("lint") or []:
            notes.append(f"{figure['key']}：{issue}")
        for issue in figure.get("layout") or []:
            notes.append(f"{figure['key']}：{issue}")
    for sequence in manifest.get("sequences") or []:
        if sequence.get("status") != "ok":
            notes.append(f"序列图 {sequence.get('key')} 渲染失败：{sequence.get('error')}")
        for issue in sequence.get("layout") or []:
            notes.append(f"序列图 {sequence.get('key')}：{issue}")
    return notes


def write_design_review_records(
    out_dir: Path,
    records: list[dict[str, Any]],
    spec: dict[str, Any],
    figures: list[dict[str, Any]] | None = None,
    layout_notes: list[str] | None = None,
) -> None:
    (out_dir / "技术方案文档自检记录.json").write_text(
        json.dumps(
            {
                "rounds": records,
                "module_count": len(spec.get("modules") or []),
                "interface_count": sum(len(group.get("interfaces") or []) for group in spec.get("api_groups") or []),
                "figure_count": len(figures or []),
                "layout_notes": layout_notes or [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    lines = ["# 技术方案文档自检记录", ""]
    for record in records:
        lines.extend([f"## 第 {record['round']} 轮：{record['action']}", ""])
        if record["issues"]:
            lines.extend(f"- {issue}" for issue in record["issues"])
        else:
            lines.append("- 未发现需继续修正的问题")
        lines.append("")
    if layout_notes:
        lines.extend(["## 图纸布局提示", ""])
        lines.extend(f"- {note}" for note in layout_notes)
        lines.append("")
    lines.extend(["## 模块清单", ""])
    lines.extend(f"- {module.get('name', '')}" for module in spec.get("modules") or [])
    (out_dir / "技术方案文档自检记录.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_design_doc(
    path: Path,
    analysis: dict[str, Any],
    software_name: str,
    version: str,
    business: dict[str, Any],
    figures: list[dict[str, Any]] | None = None,
    sequences: list[dict[str, Any]] | None = None,
    layout_notes: list[str] | None = None,
) -> list[dict[str, Any]]:
    spec = normalize_design_spec_from_business(business)
    text, records = build_design_text(analysis, software_name, version, business, spec, figures, sequences)
    path.write_text(text, encoding="utf-8")
    write_design_review_records(path.parent, records, spec, figures, layout_notes)
    return records


def render_manual_canonical(
    software_name: str,
    version: str,
    industry: str,
    users: list[str],
    positioning: str,
    core_value: str,
    modules: list[dict[str, Any]],
    operation_flow: list[str],
    manual_sections: list[Any] | None = None,
    business: dict[str, Any] | None = None,
) -> str:
    industry_text = "相关业务" if not industry or industry == "待用户确认" else industry
    user_text = join_items([user for user in users if user != "待用户确认"]) or "实际使用人员"
    positioning_text = remove_opening_definition(positioning, software_name)
    core_value_text = clean_field(core_value, "软件可以帮助用户统一处理相关业务资料，并减少重复操作。")
    flow = operation_flow
    related_documents = normalize_related_documents(business)
    system_rows = normalize_system_requirements(business)
    faq_items = normalize_faq(business, software_name)
    glossary_items = normalize_glossary(business, modules, software_name)
    overview_paragraphs: list[str] = []
    for section in manual_sections or []:
        if isinstance(section, dict) and section.get("paragraphs") and len(overview_paragraphs) < 4:
            overview_paragraphs.extend(as_text_list(section.get("paragraphs"))[:2])

    lines = [f"# {software_name}操作手册", "", section_heading(1, "相关文档"), ""]
    lines.extend(["| 文档名称 | 指向资料 | 说明 |", "| --- | --- | --- |"])
    for item in related_documents:
        lines.append(f"| {item['name']} | {item['target']} | {item['description']} |")
    lines.extend(
        [
            "",
            section_heading(2, "说明"),
            "",
            f"{software_name} {version}适用于{industry_text}场景。用户进入系统后，可以围绕实际工作内容完成账号进入、业务创建、过程查看、结果确认和资料管理等操作。",
            "",
            f"日常使用时，{user_text}可以按照页面提示从入口进入相应页面，查看当前业务状态，并根据页面中的按钮、输入框、列表或弹窗继续处理。{core_value_text}",
            "",
        ]
    )
    if positioning_text:
        lines.extend([positioning_text, ""])
    for paragraph in overview_paragraphs:
        lines.extend([paragraph, ""])
    lines.extend(
        [
            "本手册用于说明软件的用途、功能特点、运行要求和页面操作流程。各功能章节按用户能够看到的页面、入口、按钮、输入项、提示信息和处理结果进行说明。",
            "",
            section_heading(3, "功能特点"),
            "",
        ]
    )
    for i, module in enumerate(modules[:8], start=1):
        lines.extend([feature_paragraph(module, i), ""])
    lines.extend([section_heading(4, "系统要求"), "", "| 系统要求 | 最低配置 | 推荐配置 |", "| --- | --- | --- |"])
    for row in system_rows:
        lines.append(f"| {row['item']} | {row['minimum']} | {row['recommended']} |")
    lines.extend(
        [
            "",
            f"请确保实际运行环境满足以上要求，以保证{software_name}能够正常打开页面、提交操作和展示处理结果。若部署方式、客户端形态或服务器环境与本表不同，应以实际确认的申请表环境字段为准。",
            "",
        ]
    )
    next_index = append_modules_canonical(lines, modules, start_index=5)
    if flow:
        next_index = append_flow_canonical(lines, software_name, flow, start_index=next_index)
    lines.extend([section_heading(next_index, "常见问题解答"), ""])
    for item in faq_items:
        lines.extend([f"问题：{item['question']}", f"解决方法：{item['answer']}", ""])
    next_index += 1
    lines.extend([section_heading(next_index, "术语表"), "", "| 术语 | 解释 |", "| --- | --- |"])
    for item in glossary_items:
        lines.append(f"| {item['term']} | {item['definition']} |")
    lines.append("")
    append_stop(lines)
    return tidy_manual_output("\n".join(lines))


def append_stop(lines: list[str]) -> None:
    lines.extend(
        [
            "```text",
            "STOP_FOR_USER",
            "NEXT_ACTION: 请一次性确认完整操作手册草稿是否符合真实业务；必要时先统一修改段落内容，再运行 confirm_stage.py --stage markdown。",
            "```",
            "",
        ]
    )


def build_manual_text(
    analysis: dict[str, Any],
    software_name: str,
    version: str,
    business: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    positioning = plain_manual_text(business.get("product_positioning") if business else f"{software_name} {version}是一款基于项目实际功能整理的软件系统。")
    core_value = plain_manual_text(business.get("core_value") if business else "系统通过清晰的软件界面为用户提供主要业务入口，支持用户完成信息查看、业务处理、数据维护和结果反馈等操作。")
    users = business.get("target_users") if business else ["业务用户"]
    operation_flow = business.get("operation_flow") if business else []
    manual_sections = business.get("manual_sections") if business else []
    industry = business.get("industry") if business else "业务应用"
    if positioning.rstrip("。") == software_name.rstrip("。"):
        positioning = "用户可以根据项目资料中体现的业务场景完成相应操作。"
    elif not positioning.endswith("。"):
        positioning += "。"
    modules = normalize_manual_modules(business, [])
    records: list[dict[str, Any]] = []

    text = render_manual_canonical(software_name, version, industry, users, positioning, core_value, modules, operation_flow, manual_sections, business)
    records.append({"round": 1, "action": "初稿生成", "issues": manual_quality_issues(text, modules)})

    text = render_manual_canonical(software_name, version, industry, users, positioning, core_value, modules, operation_flow, manual_sections, business)
    records.append({"round": 2, "action": "真实页面字段复核", "issues": manual_quality_issues(text, modules)})

    text = render_manual_canonical(software_name, version, industry, users, positioning, core_value, modules, operation_flow, manual_sections, business)
    records.append({"round": 3, "action": "制式模板和 AI 味复核", "issues": manual_quality_issues(text, modules)})

    for round_no in range(4, 7):
        issues = records[-1]["issues"]
        if not issues:
            break
        text = render_manual_canonical(software_name, version, industry, users, positioning, core_value, modules, operation_flow, manual_sections, business)
        records.append(
            {
                "round": round_no,
                "action": "复核仍需模型回到业务理解补写",
                "issues": manual_quality_issues(text, modules),
            }
        )
        break
    return text, records, modules


def write_review_records(out_dir: Path, records: list[dict[str, Any]], modules: list[dict[str, Any]]) -> None:
    (out_dir / "操作手册自检记录.json").write_text(
        json.dumps({"rounds": records, "module_count": len(modules)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = ["# 操作手册自检记录", ""]
    for record in records:
        lines.extend([f"## 第 {record['round']} 轮：{record['action']}", ""])
        if record["issues"]:
            lines.extend(f"- {issue}" for issue in record["issues"])
        else:
            lines.append("- 未发现需继续修正的问题")
        lines.append("")
    lines.extend(["## 模块清单", ""])
    lines.extend(f"- {module['feature']}" for module in modules)
    (out_dir / "操作手册自检记录.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manual(path: Path, analysis: dict[str, Any], software_name: str, version: str, business: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    text, records, modules = build_manual_text(analysis, software_name, version, business)
    path.write_text(text, encoding="utf-8")
    write_review_records(path.parent, records, modules)
    return records


def require_confirmed_business(business: dict[str, Any] | None) -> None:
    if business is None:
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 文档草稿必须基于已确认的业务理解生成。请先生成并确认 草稿/业务理解.md。"
        )
    if business.get("confirmation_required") and not business.get("user_confirmed"):
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 业务理解尚未确认。请先确认 草稿/业务理解.md，"
            "再运行 `python3 <SKILL_DIR>/scripts/confirm_stage.py --workdir 软件著作权申请资料 --stage business --note \"<用户确认内容>\"`。"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--business-context", help="Business context JSON generated before manual drafting")
    parser.add_argument("--out-dir", default="软件著作权申请资料/草稿")
    args = parser.parse_args()

    analysis = read_json(Path(args.analysis))
    business = read_json(Path(args.business_context)) if args.business_context else None
    require_confirmed_business(business)
    out_dir = ensure_dir(Path(args.out_dir))
    doc_kind = "design" if business and business.get("manual_kind") == "design" else "operation"
    if doc_kind == "design":
        out_path = out_dir / "技术方案文档.md"
        figures: list[dict[str, Any]] = []
        sequences: list[dict[str, Any]] = []
        manifest_path = out_dir / "图纸清单.json"
        layout_notes: list[str] = []
        if manifest_path.is_file():
            manifest = read_json(manifest_path)
            figures = manifest.get("figures") or []
            sequences = manifest.get("sequences") or []
            layout_notes = collect_layout_notes(manifest)
        records = write_design_doc(out_path, analysis, args.software_name, args.version, business, figures, sequences, layout_notes)
        print(f"OK technical design draft: {out_path}")
        print(f"OK technical design self-review: {out_dir / '技术方案文档自检记录.md'}")
        for record in records:
            print(f"Review round {record['round']}: {record['action']} issues={len(record['issues'])}")
        if records[-1]["issues"]:
            print("STOP_FOR_USER")
            print(
                "NEXT_ACTION: 技术方案文档自检仍有问题。请回到业务理解阶段补全 design_spec 中的真实模块、功能、接口和出错处理设计后再重新生成。"
            )
            raise SystemExit(1)
        print("STOP_FOR_USER")
        print(
            "NEXT_ACTION: 请一次性确认完整技术方案文档草稿是否与真实设计一致；必要时先统一修改段落内容，再运行 confirm_stage.py --stage markdown。"
        )
        return

    out_path = out_dir / "操作手册.md"
    records = write_manual(out_path, analysis, args.software_name, args.version, business)
    print(f"OK manual draft: {out_path}")
    print(f"OK manual self-review: {out_dir / '操作手册自检记录.md'}")
    for record in records:
        print(f"Review round {record['round']}: {record['action']} issues={len(record['issues'])}")
    if records[-1]["issues"]:
        print("STOP_FOR_USER")
        print("NEXT_ACTION: 操作手册自检仍有问题。请回到业务理解阶段补全 manual_modules 中的真实页面内容、操作规则和结果反馈后再重新生成。")
        raise SystemExit(1)
    print("STOP_FOR_USER")
    print("NEXT_ACTION: 请一次性确认完整操作手册草稿是否符合真实业务；必要时先统一修改段落内容，再运行 confirm_stage.py --stage markdown。")


if __name__ == "__main__":
    main()
