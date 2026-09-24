#!/usr/bin/env python3
"""Collect project evidence and write a model-authored business context."""

from __future__ import annotations

import argparse
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from common import ensure_dir, is_document_candidate, iter_project_files, read_json, read_text, rel, write_json


MAX_DOC_CHARS = 80_000
MAX_DOCS = 40
MAX_DOCUMENT_FILE_BYTES = 25_000_000
MAX_DOCUMENT_XML_BYTES = 5_000_000


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_md(text: str) -> str:
    text = re.sub(r"`{3}.*?`{3}", " ", text, flags=re.S)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"[>#*_`|]", " ", text)
    return normalize_space(text)


def skip_doc(path: Path, project: Path) -> bool:
    r = rel(path, project).lower()
    skip_parts = (
        "node_modules",
        ".git/",
        "dist/",
        "build/",
        ".next/",
        "coverage/",
        "软件著作权申请资料",
    )
    return any(part in r for part in skip_parts)


def extract_headings(text: str, limit: int = 24) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            title = clean.lstrip("#").strip()
            if title and title not in headings:
                headings.append(title[:120])
        if len(headings) >= limit:
            break
    return headings


def extract_opening(text: str, limit: int = 900) -> str:
    clean = strip_md(text)
    return clean[:limit].strip()


def extract_zip_xml_text(path: Path, member: str) -> str:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(member)
        if info.file_size > MAX_DOCUMENT_XML_BYTES:
            raise ValueError("document XML is too large to extract safely")
        with archive.open(info) as stream:
            data = stream.read(MAX_DOCUMENT_XML_BYTES + 1)
        if len(data) > MAX_DOCUMENT_XML_BYTES:
            raise ValueError("document XML is too large to extract safely")
    root = ET.fromstring(data)
    paragraphs: list[str] = []
    for node in root.iter():
        if not node.tag.endswith("}p"):
            continue
        text = "".join(child.text or "" for child in node.iter() if child.tag.endswith("}t"))
        if text.strip():
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)[:MAX_DOC_CHARS]
    return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))[:MAX_DOC_CHARS]


def read_project_document(path: Path) -> tuple[str, str]:
    """Extract useful evidence text when possible and retain unsupported documents."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            return extract_zip_xml_text(path, "word/document.xml"), "已提取 DOCX 正文"
        if suffix == ".odt":
            return extract_zip_xml_text(path, "content.xml"), "已提取 ODT 正文"
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore[import-not-found]

                reader = PdfReader(str(path))
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                return text[:MAX_DOC_CHARS], "已提取 PDF 文本"
            except Exception:
                return "", "已发现 PDF；当前环境无法自动提取文本，请由模型直接阅读该文件"
        if suffix in {".doc", ".wps"}:
            return "", f"已发现 {suffix.lstrip('.').upper()} 文档；请由模型使用可用的文档工具读取"
        return read_text(path, limit=MAX_DOC_CHARS), "已提取文本"
    except Exception as exc:
        return "", f"文档已发现但读取失败：{type(exc).__name__}"


def collect_documents(project: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in iter_project_files(project):
        if skip_doc(path, project) or not is_document_candidate(path, project):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_DOCUMENT_FILE_BYTES:
            text = ""
            extraction_note = "文档已发现但文件过大，未自动提取；请由模型按需直接阅读"
        else:
            text, extraction_note = read_project_document(path)
        docs.append(
            {
                "path": rel(path, project),
                "size": size,
                "headings": extract_headings(text),
                "opening": extract_opening(text),
                "format": path.suffix.lower().lstrip(".") or "text",
                "text_extracted": bool(text.strip()),
                "extraction_note": extraction_note,
            }
        )
    docs.sort(
        key=lambda item: (
            0 if Path(item["path"]).suffix.lower() in {".md", ".txt", ".rst", ".adoc", ".docx", ".pdf"} else 1,
            item["path"].count("/"),
            item["path"],
        )
    )
    return docs[:MAX_DOCS]


def collect_code_evidence(analysis: dict[str, Any]) -> dict[str, Any]:
    source = analysis.get("source") or {}
    categorized = source.get("categorized_files") or {}
    return {
        "project_name": analysis.get("project_name"),
        "software_name_candidate": analysis.get("software_name_candidate"),
        "frameworks": analysis.get("frameworks") or [],
        "language": analysis.get("language"),
        "routes": analysis.get("routes") or [],
        "feature_name_candidates": analysis.get("feature_candidates") or [],
        "entry_files": categorized.get("entry") or [],
        "page_files": categorized.get("page") or [],
        "component_files": categorized.get("component") or [],
        "api_files": categorized.get("api") or [],
        "run_command_candidates": analysis.get("run_command_candidates") or [],
        "package": analysis.get("package") or {},
    }


def build_evidence(project: Path, analysis: dict[str, Any], software_name: str, web_notes: str) -> dict[str, Any]:
    return {
        "software_name": software_name,
        "project_root": str(project.resolve()),
        "instruction": (
            "本文件只收集证据，不决定行业、功能或手册结构。"
            "请由模型阅读这些证据以及必要的项目源码后，另行编写业务理解模型稿。"
        ),
        "documents": collect_documents(project),
        "code_evidence": collect_code_evidence(analysis),
        "external_research_notes": web_notes,
    }


def write_evidence_md(path: Path, evidence: dict[str, Any]) -> None:
    lines = [
        "# 业务理解证据",
        "",
        f"- 软件名称：{evidence['software_name']}",
        f"- 项目目录：`{evidence['project_root']}`",
        "",
        "本文件只列出可供模型研判的项目证据，不代表最终申报口径。",
        "模型需要自行判断应阅读哪些文档、抽取哪些功能、采用什么操作手册结构。",
        "",
        "## 代码与页面证据",
        "",
    ]
    code = evidence["code_evidence"]
    for key in ("frameworks", "language", "routes", "feature_name_candidates", "entry_files", "page_files", "component_files", "api_files"):
        value = code.get(key)
        if value:
            lines.append(f"- {key}：{value}")
    lines.extend(["", "## 文档证据", ""])
    for doc in evidence["documents"]:
        lines.extend(
            [
                f"### {doc['path']}",
                "",
                f"- 大小：{doc['size']} bytes",
                f"- 格式：{doc['format'] or 'text'}",
                f"- 读取状态：{doc['extraction_note']}",
                f"- 标题线索：{'；'.join(doc['headings']) if doc['headings'] else '无'}",
                "",
                doc["opening"] or "（已登记文件路径，等待模型进一步读取）",
                "",
            ]
        )
    if evidence.get("external_research_notes"):
        lines.extend(["## 外部调研摘要", "", evidence["external_research_notes"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_model_template(path: Path, evidence: dict[str, Any]) -> None:
    template = {
        "software_name": evidence["software_name"],
        "manual_kind": "operation 或 design：软件有用户可见页面/图形界面时用 operation（生成操作手册）；"
        "软件没有用户界面（嵌入式固件、驱动、库、后端服务、命令行工具等）时用 design（生成技术方案文档）",
        "product_positioning": "",
        "industry": "",
        "target_users": [],
        "core_value": "",
        "business_features": [],
        "business_feature_details": {},
        "operation_flow": [],
        "application_purpose": "",
        "main_functions": "",
        "technical_characteristics": "",
        "software_technical_option": "应用软件",
        "software_category": "应用软件",
        "manual_sections": [
            {
                "title": "模型自行命名章节",
                "intent": "说明该章节为什么适合当前项目。",
                "paragraphs": [],
                "include_feature_overview": False,
                "include_operation_modules": False,
                "include_operation_flow": False,
            }
        ],
        "manual_modules": [
            {
                "title": "真实页面或核心流程名称",
                "evidence": ["页面、路由、组件、README 或需求文档路径"],
                "purpose": "该页面或流程在当前软件中的用途。",
                "usage": "用户在什么业务场景下会使用该页面，正在处理什么具体事务。",
                "entry": "用户从哪里进入该页面或流程。",
                "visible_elements": ["用户实际能看到的输入框、按钮、列表、状态或结果区域"],
                "operation_steps": ["按真实页面顺序描述用户动作，不写代码实现。"],
                "validation_rules": ["输入限制、必填项、额度、权限、异常提示等规则；没有则留空数组。"],
                "feedback": ["操作完成后用户能看到的结果、提示或状态变化。"],
                "screenshot": "截图预留说明",
            }
        ],
        "design_spec": {
            "_说明": "仅 manual_kind 为 design 时填写；此时不要填写 manual_modules。",
            "intro_note": "可选：引言补充说明。",
            "requirements": ["按项目真实需求逐条填写，如运行在嵌入式环境中、控制接收机等"],
            "conditions": "运行环境、开发环境、操作系统、交叉编译工具链和编程语言等条件与限制",
            "architecture": "软件总体结构描述：部署形态、分层、与硬件/其他软件的关系",
            "modules": [{"name": "真实模块名", "description": "该模块的功能描述"}],
            "module_note": "可选：模块分层、依赖或调用关系的补充说明",
            "overview": "2.6 设计和描述总述：主要功能如何组织、数据如何流动、重点设计是什么",
            "key_designs": [{"title": "关键设计点名称", "description": "该设计的原理和流程说明", "figure": "流程图/类图等图类型；没有图则留空"}],
            "functions": [{"title": "真实功能名称", "description": "该功能的设计说明和数据处理过程", "figure": "序列图/处理流等图类型；没有图则留空"}],
            "ui_statement": "软件界面说明；无界面软件默认填 无。",
            "api_groups": [
                {
                    "title": "接口分组名称，如 功能请求接口/数据传输接口/事件通知接口/串口协议",
                    "summary": "该组接口的整体说明，如传输方式、端口、协议",
                    "interfaces": [
                        {
                            "signature": "接口签名或名称，如 int fullscan(uint fc, uint bandwidth)",
                            "description": "接口调用后的行为和效果说明",
                            "params": [{"name": "fc", "type": "uint", "detail": "指定频段中心频率"}],
                            "returns": "返回 0 为成功，其他值为错误码",
                        }
                    ],
                }
            ],
            "error_handling": [{"title": "出错处理机制名称，如 事件通知/日志数据", "description": "该机制的说明"}],
            "figures": {
                "_说明": "可选。DOT 图源按插槽命名：architecture（总体结构框架图）、key_1..key_N（对应 key_designs）、function_1..function_N（对应 functions）。"
                "声明后由 scripts/render_design_figures.py 渲染成 PNG 并嵌入正文；不声明或渲染失败时正文保留【图预留】占位。",
                "architecture": "digraph G { rankdir=TB; 调度器 [shape=box]; 采集任务 [shape=box]; 通信任务 [shape=box]; 指令任务 [shape=box]; 采集任务 -> 队列 [label=数据]; 队列 -> 通信任务; 指令任务 -> 驱动层; }",
            },
        },
        "system_requirements": [
            {"item": "操作系统", "minimum": "按项目实际填写", "recommended": "按项目实际填写"},
            {"item": "浏览器或客户端", "minimum": "按项目实际填写", "recommended": "按项目实际填写"},
        ],
        "faq": [
            {"question": "按当前软件真实使用场景填写常见问题", "answer": "给出面向普通用户的处理方法。"}
        ],
        "glossary": [
            {"term": "当前软件中的业务术语", "definition": "用普通中文解释含义。"}
        ],
        "model_review_notes": [
            "有用户界面的软件：操作手册采用软著审核友好的通用骨架（相关文档、说明、功能特点、系统要求、按真实页面/流程逐章操作、常见问题、术语表）。",
            "无用户界面的软件（嵌入式固件、驱动、库、后端服务等）：manual_kind 填 design，design_spec 按技术方案文档骨架填写（需求、条件与限制、总体结构、模块表、关键设计、功能设计、接口设计、出错处理）。",
            "manual_modules 要按当前项目真实页面、导航入口、按钮、输入限制、系统反馈和截图位置编写，不能只写抽象功能名。",
            "design_spec 的模块、功能、接口必须来自真实项目源码和文档，不得编造项目中不存在的接口或模块。",
            "figures 用 DOT 语言描述（architecture/key_n/function_n 插槽），图源必须对应真实模块结构；graphviz 不可用时不要声明 figures，保留【图预留】占位。",
            "不要照抄范本文案；范本只说明结构要求，内容必须换成当前软件的真实设计。",
            "不要用关键词表决定行业和功能；必须能从项目证据或用户补充中解释来源。",
        ],
    }
    write_json(path, template)


def load_model_context(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid model context JSON: {path}")
    return data


def required_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit(f"Model context field must be a list: {field}")
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        raise SystemExit(f"Model context field cannot be empty: {field}")
    return items


def required_text(data: dict[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise SystemExit(f"Model context field cannot be empty: {field}")
    return value


MANUAL_KIND_ALIASES = {
    "operation": "operation",
    "manual": "operation",
    "操作手册": "operation",
    "design": "design",
    "design-spec": "design",
    "technical": "design",
    "技术方案": "design",
    "技术方案文档": "design",
    "设计说明书": "design",
}


def normalize_manual_kind(model: dict[str, Any]) -> str:
    """Decide whether the prose document is an operation manual or a technical design spec."""
    raw = str(model.get("manual_kind") or "operation").strip()
    kind = MANUAL_KIND_ALIASES.get(raw.lower() if raw.isascii() else raw)
    if kind is None:
        raise SystemExit(f"Model context manual_kind must be 'operation' or 'design'; got: {raw}")
    return kind


def _design_items(raw: Any, field: str, required_fields: tuple[str, ...], *, required: bool = True) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        if raw is None and not required:
            return []
        raise SystemExit(f"design_spec field must be a list: {field}")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"design_spec {field} item {index} must be an object")
        missing = [name for name in required_fields if not str(item.get(name) or "").strip()]
        if missing:
            raise SystemExit(f"design_spec {field} item {index} missing field: {', '.join(missing)}")
        items.append({name: str(item.get(name)).strip() for name in item if str(name).strip()})
    if required and not items:
        raise SystemExit(f"design_spec field cannot be empty: {field}")
    return items


def normalize_api_groups(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise SystemExit("design_spec field must be a non-empty list: api_groups")
    groups: list[dict[str, Any]] = []
    for group_index, group in enumerate(raw, start=1):
        if not isinstance(group, dict):
            raise SystemExit(f"design_spec api_groups item {group_index} must be an object")
        title = str(group.get("title") or group.get("name") or "").strip()
        if not title:
            raise SystemExit(f"design_spec api_groups item {group_index} missing field: title")
        raw_interfaces = group.get("interfaces")
        if not isinstance(raw_interfaces, list) or not raw_interfaces:
            raise SystemExit(f"design_spec api_groups item {group_index} ({title}) missing non-empty field: interfaces")
        interfaces: list[dict[str, Any]] = []
        for iface_index, iface in enumerate(raw_interfaces, start=1):
            if not isinstance(iface, dict):
                raise SystemExit(f"api_groups {title} interfaces item {iface_index} must be an object")
            signature = str(iface.get("signature") or iface.get("name") or iface.get("title") or "").strip()
            description = str(iface.get("description") or iface.get("summary") or "").strip()
            if not signature or not description:
                raise SystemExit(
                    f"api_groups {title} interfaces item {iface_index} missing field: signature/description"
                )
            params: list[dict[str, str]] = []
            raw_params = iface.get("params") or iface.get("parameters") or []
            if isinstance(raw_params, list):
                for param_index, param in enumerate(raw_params, start=1):
                    if not isinstance(param, dict):
                        raise SystemExit(f"接口 {signature} params item {param_index} must be an object")
                    name = str(param.get("name") or "").strip()
                    if not name:
                        raise SystemExit(f"接口 {signature} params item {param_index} missing field: name")
                    params.append(
                        {
                            "name": name,
                            "type": str(param.get("type") or "").strip(),
                            "detail": str(param.get("detail") or param.get("description") or param.get("value") or "").strip(),
                        }
                    )
            interfaces.append(
                {
                    "signature": signature,
                    "description": description,
                    "params": params,
                    "returns": str(iface.get("returns") or iface.get("result") or "").strip(),
                }
            )
        groups.append(
            {
                "title": title,
                "summary": str(group.get("summary") or group.get("description") or "").strip(),
                "interfaces": interfaces,
            }
        )
    return groups


def normalize_design_spec(model: dict[str, Any]) -> dict[str, Any]:
    """Validate the model-authored design spec used for no-GUI software."""
    spec = model.get("design_spec")
    if not isinstance(spec, dict):
        raise SystemExit(
            "Model context field must be an object: design_spec。"
            "无用户界面的软件应设置 manual_kind 为 design 并提供 design_spec，不要填写 manual_modules。"
        )
    return {
        "intro_note": str(spec.get("intro_note") or "").strip(),
        "requirements": required_list(spec.get("requirements"), "design_spec.requirements"),
        "conditions": required_text(spec, "conditions"),
        "architecture": required_text(spec, "architecture"),
        "modules": [
            {
                "name": str(item.get("name") or item.get("title") or "").strip(),
                "description": str(item.get("description") or item.get("function") or "").strip(),
            }
            for item in _design_items(spec.get("modules"), "modules", ("name", "description"))
        ],
        "module_note": str(spec.get("module_note") or "").strip(),
        "overview": required_text(spec, "overview"),
        "key_designs": _design_items(
            spec.get("key_designs") or [], "key_designs", ("title", "description"), required=False
        ),
        "functions": _design_items(spec.get("functions"), "functions", ("title", "description")),
        "ui_statement": str(spec.get("ui_statement") or "无。").strip(),
        "api_groups": normalize_api_groups(spec.get("api_groups")),
        "error_handling": _design_items(spec.get("error_handling"), "error_handling", ("title", "description")),
        "figures": normalize_figures(spec),
    }


def normalize_figures(spec: dict[str, Any]) -> dict[str, str]:
    """Validate DOT figure sources keyed by slot (architecture, key_n, function_n)."""
    figures = spec.get("figures")
    if figures is None:
        return {}
    if not isinstance(figures, dict):
        raise SystemExit("design_spec field must be an object: figures")
    normalized: dict[str, str] = {}
    for key, value in figures.items():
        key = str(key).strip()
        if not re.fullmatch(r"(architecture|key_[1-9][0-9]*|function_[1-9][0-9]*)", key):
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


def effective_len(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def normalize_model_context(model: dict[str, Any], evidence: dict[str, Any], web_notes: str) -> dict[str, Any]:
    industry = required_text(model, "industry")
    application_purpose = required_text(model, "application_purpose")
    main_functions = required_text(model, "main_functions")
    technical_characteristics = required_text(model, "technical_characteristics")
    if len(industry) > 50:
        raise SystemExit("Model context field exceeds 50 characters: industry")
    if len(application_purpose) > 50:
        raise SystemExit("Model context field exceeds 50 characters: application_purpose")
    main_function_chars = effective_len(main_functions)
    if not 500 <= main_function_chars <= 1300:
        raise SystemExit(
            f"Model context field main_functions must contain 500-1300 non-whitespace characters; got {main_function_chars}"
        )
    if len(technical_characteristics) > 100:
        raise SystemExit("Model context field exceeds 100 characters: technical_characteristics")
    features = required_list(model.get("business_features"), "business_features")
    details = model.get("business_feature_details") or {}
    if not isinstance(details, dict):
        raise SystemExit("Model context field must be an object: business_feature_details")
    missing = [feature for feature in features if not str(details.get(feature) or "").strip()]
    if missing:
        raise SystemExit("Model context missing feature details: " + "、".join(missing[:12]))
    sections = model.get("manual_sections") or []
    if sections and not isinstance(sections, list):
        raise SystemExit("Model context field must be a list: manual_sections")
    manual_kind = normalize_manual_kind(model)
    design_spec: dict[str, Any] | None = None
    if manual_kind == "design":
        design_spec = normalize_design_spec(model)
        manual_modules = model.get("manual_modules") or []
        if manual_modules:
            raise SystemExit(
                "manual_kind 为 design 时不要填写 manual_modules；无界面软件的设计内容统一写入 design_spec。"
            )
    else:
        manual_modules = model.get("manual_modules") or []
        if manual_modules and not isinstance(manual_modules, list):
            raise SystemExit("Model context field must be a list: manual_modules")
        if not manual_modules:
            raise SystemExit("Model context field cannot be empty: manual_modules")
        for index, module in enumerate(manual_modules, start=1):
            if not isinstance(module, dict):
                raise SystemExit(f"manual_modules item {index} must be an object")
            title = str(module.get("title") or module.get("feature") or "").strip()
            for field in ("purpose", "usage", "entry", "operation_steps", "feedback"):
                value = module.get(field)
                if field == "usage" and not str(value or "").strip():
                    value = module.get("usage_scenario")
                if isinstance(value, list):
                    missing_value = not any(str(item).strip() for item in value)
                else:
                    missing_value = not str(value or "").strip()
                if missing_value:
                    raise SystemExit(f"manual_modules item {index} ({title or 'untitled'}) missing field: {field}")
    system_requirements = model.get("system_requirements") or []
    if system_requirements and not isinstance(system_requirements, list):
        raise SystemExit("Model context field must be a list: system_requirements")
    if not system_requirements and manual_kind != "design":
        raise SystemExit("Model context field cannot be empty: system_requirements")
    faq = model.get("faq") or []
    if faq and not isinstance(faq, list):
        raise SystemExit("Model context field must be a list: faq")
    if not faq and manual_kind != "design":
        raise SystemExit("Model context field cannot be empty: faq")
    glossary = model.get("glossary") or []
    if glossary and not isinstance(glossary, list):
        raise SystemExit("Model context field must be a list: glossary")
    if not glossary and manual_kind != "design":
        raise SystemExit("Model context field cannot be empty: glossary")
    context = {
        "software_name": evidence["software_name"],
        "business_understanding_required": True,
        "source_documents": [{"path": doc["path"], "size": doc["size"]} for doc in evidence["documents"]],
        "project_evidence_file": "业务理解证据.md",
        "manual_kind": manual_kind,
        "product_positioning": required_text(model, "product_positioning"),
        "industry": industry,
        "target_users": required_list(model.get("target_users"), "target_users"),
        "core_value": required_text(model, "core_value"),
        "business_features": features,
        "business_feature_details": {feature: str(details.get(feature)).strip() for feature in features},
        "operation_flow": required_list(model.get("operation_flow"), "operation_flow"),
        "application_purpose": application_purpose,
        "main_functions": main_functions,
        "technical_characteristics": technical_characteristics,
        "software_technical_option": str(model.get("software_technical_option") or "应用软件"),
        "software_category": str(model.get("software_category") or "应用软件"),
        "manual_sections": sections,
        "manual_modules": manual_modules,
        "system_requirements": system_requirements,
        "faq": faq,
        "glossary": glossary,
        "model_authored": True,
        "external_research_notes": web_notes,
        "confirmation_required": True,
        "user_confirmed": False,
        "confirmation_stage": "business",
        "next_action": "请确认 草稿/业务理解.md 中的软件用途、行业、目标用户、核心功能、文档类型和申请口径；确认后运行 confirm_stage.py --stage business。",
        "review_notes": (
            [
                "请确认模型判断的行业领域、目标用户和主要功能是否符合实际申报口径。",
                "请确认软件确实没有面向用户的图形界面/页面，文档类型选择技术方案文档是否正确。",
                "请确认技术方案文档中的模块划分、关键设计、功能流程和接口描述是否与项目源码一致。",
            ]
            if manual_kind == "design"
            else [
                "请确认模型判断的行业领域、目标用户和主要功能是否符合实际申报口径。",
                "请确认操作手册结构是否按真实页面和流程展开，而不是套用抽象功能列表。",
            ]
        ),
    }
    if design_spec is not None:
        context["design_spec"] = design_spec
    return context


def write_context_md(path: Path, context: dict[str, Any]) -> None:
    lines = [
        "# 业务理解",
        "",
        f"- 软件名称：{context['software_name']}",
        f"- 产品定位：{context['product_positioning']}",
        f"- 面向领域 / 行业：{context['industry']}",
        f"- 核心价值：{context['core_value']}",
        f"- 证据文件：`{context['project_evidence_file']}`",
        "",
        "## 目标用户",
        "",
    ]
    lines.extend(f"- {item}" for item in context["target_users"])
    lines.extend(["", "## 主要业务功能", ""])
    lines.extend(f"- {item}" for item in context["business_features"])
    lines.extend(["", "## 功能说明", ""])
    for item in context["business_features"]:
        lines.append(f"- {item}：{context['business_feature_details'].get(item, '')}")
    lines.extend(["", "## 典型操作流程", ""])
    lines.extend(f"{i}. {item}" for i, item in enumerate(context["operation_flow"], start=1))
    if context.get("manual_kind") == "design":
        spec = context.get("design_spec") or {}
        lines.extend(["", "## 技术方案文档设计要点", ""])
        lines.append("- 文档类型：技术方案文档（软件无用户图形界面，不生成操作手册）")
        if spec.get("modules"):
            module_names = "、".join(str(item.get("name") or "") for item in spec["modules"][:12])
            lines.append(f"- 设计模块：{module_names}")
        if spec.get("functions"):
            function_names = "、".join(str(item.get("title") or "") for item in spec["functions"][:12])
            lines.append(f"- 功能设计：{function_names}")
        for group in spec.get("api_groups") or []:
            count = len(group.get("interfaces") or [])
            lines.append(f"- 接口设计：{group.get('title')}（{count} 个接口）")
        if spec.get("error_handling"):
            handling_names = "、".join(str(item.get("title") or "") for item in spec["error_handling"])
            lines.append(f"- 出错处理：{handling_names}")
    else:
        if context.get("manual_sections"):
            lines.extend(["", "## 操作手册结构建议", ""])
            for i, section in enumerate(context["manual_sections"], start=1):
                if isinstance(section, dict):
                    title = section.get("title") or f"章节 {i}"
                    intent = section.get("intent") or ""
                else:
                    title = str(section)
                    intent = ""
                lines.append(f"{i}. {title}" + (f"：{intent}" if intent else ""))
        if context.get("manual_modules"):
            lines.extend(["", "## 操作手册页面/流程模块", ""])
            for i, module in enumerate(context["manual_modules"], start=1):
                if not isinstance(module, dict):
                    lines.append(f"{i}. {module}")
                    continue
                title = module.get("title") or module.get("feature") or f"模块 {i}"
                usage = module.get("usage") or module.get("usage_scenario") or ""
                entry = module.get("entry") or ""
                steps = module.get("operation_steps") or module.get("steps") or []
                lines.append(f"{i}. {title}" + (f"：{entry}" if entry else ""))
                if usage:
                    lines.append(f"   - 使用场景：{usage}")
                if steps:
                    lines.append(f"   - 操作要点：{'；'.join(str(item) for item in steps[:4])}")
    lines.extend(
        [
            "",
            "## 申请表建议口径",
            "",
            f"- 开发目的：{context['application_purpose']}",
            f"- 软件的主要功能：{context['main_functions']}",
            f"- 技术特点：{context['technical_characteristics']}",
            f"- 软件的技术特点选项：{context['software_technical_option']}",
            f"- 软件分类：{context['software_category']}",
            "",
            "## 证据来源",
            "",
        ]
    )
    lines.extend(f"- `{item['path']}`" for item in context["source_documents"])
    lines.extend(["", "## 待确认", ""])
    lines.extend(f"- {item}" for item in context["review_notes"])
    lines.extend(
        [
            "",
            "```text",
            "STOP_FOR_USER",
            f"NEXT_ACTION: {context['next_action']}",
            "```",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--out-dir", default="软件著作权申请资料/草稿")
    parser.add_argument("--web-notes", help="Optional plain-text notes from external/competitor research")
    parser.add_argument("--model-context", help="Model-authored business context JSON")
    args = parser.parse_args()

    project = Path(args.project)
    analysis = read_json(Path(args.analysis))
    web_notes = read_text(Path(args.web_notes)) if args.web_notes else ""
    out_dir = ensure_dir(Path(args.out_dir))

    evidence = build_evidence(project, analysis, args.software_name, web_notes)
    write_json(out_dir / "业务理解证据.json", evidence)
    write_evidence_md(out_dir / "业务理解证据.md", evidence)

    if not args.model_context:
        write_model_template(out_dir / "业务理解模型稿模板.json", evidence)
        print(f"OK business evidence: {out_dir / '业务理解证据.md'}")
        print(f"OK model template: {out_dir / '业务理解模型稿模板.json'}")
        print("NEXT_ACTION: 模型需要阅读业务理解证据和项目源码，自行编写业务理解模型稿 JSON，然后用 --model-context 生成业务理解.md/json。")
        return

    model = load_model_context(Path(args.model_context))
    context = normalize_model_context(model, evidence, web_notes)
    write_json(out_dir / "业务理解.json", context)
    write_context_md(out_dir / "业务理解.md", context)
    print(f"OK business context: {out_dir / '业务理解.md'}")
    print(f"Features: {len(context['business_features'])}")
    print("STOP_FOR_USER")
    print(f"NEXT_ACTION: {context['next_action']}")


if __name__ == "__main__":
    main()
