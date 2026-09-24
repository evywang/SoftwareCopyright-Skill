# 业务理解规则

申请表信息和申请文档不能只根据代码结构泛泛生成，必须先理解软件业务。

## 文档类型判定（manual_kind）

模型研判业务时必须先判定软件是否存在面向用户的图形界面/页面，并在业务理解模型稿中设置 `manual_kind`：

- `operation`（默认）：软件有用户可见页面或图形界面（Web、桌面、移动端），后续生成操作手册，填写 `manual_modules`。
- `design`：软件没有用户界面（嵌入式固件、驱动、库、后端服务、命令行工具等），后续生成技术方案文档，填写 `design_spec`，不要填写 `manual_modules`。

`manual_kind` 与文档类型必须在业务理解门禁中让用户确认；判定不符合实际时用户可以要求改回另一种类型。

## design_spec 字段要求（manual_kind=design 时）

`design_spec` 必须由模型阅读真实项目后填写，脚本只校验结构：

- `requirements`：需求条目列表。
- `conditions`：目标运行环境、开发环境、工具链和编程语言。
- `architecture`：软件总体结构和部署形态描述。
- `modules`：`{name, description}` 模块列表，与真实模块对应。
- `overview`：设计和描述总述。
- `key_designs`（可选）：`{title, description, figure}` 关键设计点。
- `functions`：`{title, description, figure}` 真实功能设计。
- `ui_statement`：软件界面说明，无界面软件默认“无。”。
- `api_groups`：`{title, summary, interfaces: [{signature, description, params: [{name, type, detail}], returns}]}` 接口分组，接口必须能在源码中回溯。
- `error_handling`：`{title, description}` 出错处理机制。

文档骨架见 [technical_design_structure.md](technical_design_structure.md)。

## 证据收集

先用脚本收集证据，输出 `草稿/业务理解证据.md/json` 和 `草稿/业务理解模型稿模板.json`。证据通常包括：

- `README.md`
- `docs/*PRD*.md`
- `docs/*BRD*.md`
- `docs/*ARCHITECTURE*.md`
- 产品说明、需求文档、设计文档
- 前端页面标题、按钮文案、路由、核心组件名
- 后端 API 路由和模型名称

这些只是候选证据，不代表最终行业、功能和手册结构。

## 输出业务理解草稿

模型必须阅读证据和必要源码，自行判断应该抽取哪些业务信息，再生成业务理解模型稿 JSON。不得用关键字表或固定模板决定行业、功能和结构。

模型稿经脚本校验后生成 `草稿/业务理解.md` 和 `草稿/业务理解.json`，至少包含：

- 产品定位
- 面向领域 / 行业
- 目标用户
- 用户痛点和核心价值
- 主要业务功能
- 典型操作流程
- 文档类型（manual_kind：operation=操作手册 / design=技术方案文档）
- 操作手册结构建议（operation 时）
- 操作手册页面/流程模块（operation 时），必须说明每个真实页面或核心流程的使用场景、进入位置、用户可见元素、用户动作、输入/状态规则、结果反馈和截图预留
- design_spec 技术方案设计要点（design 时），见上文
- 申请表建议口径
- 证据来源
- 待用户确认项

申请表直接复用的 `application_purpose`、`industry`、`main_functions`、`technical_characteristics` 必须在业务理解阶段满足申请表限制：开发目的和行业各不超过 50 字，主要功能为 500~1300 个非空白字符，技术特点描述不超过 100 字。校验不通过时回到模型稿补写，不能用脚本生成的空泛段落掩盖缺失内容。

## 外部调研

如果项目材料不足、业务类型较新，或用户明确希望参考竞品，可联网搜索相近产品和行业资料。

外部调研只用于帮助理解行业表达，不能编造项目不存在的功能。需要把调研结论写入业务理解草稿，并区分“项目证据”和“行业参考”。

## 生成材料约束

- `申请表信息.md/txt` 的开发目的、行业、主要功能、技术特点必须优先来自业务理解。
- `操作手册.md/docx`（operation）的说明、功能特点、系统要求、核心页面/流程、常见问题、术语表和章节结构必须优先来自模型确认后的业务理解。
- `技术方案文档.md/docx`（design）的模块表、关键设计、功能设计和接口表必须来自模型确认后的 `design_spec`，与项目源码一致。
- 操作手册不应只生成抽象“功能列表”。模型应把路由、页面、按钮、输入框、列表、弹窗、状态提示、额度或权限规则等用户可见证据整理到 `manual_modules`，供脚本按通用操作手册骨架排版。最终成稿应是段落化用户手册，不是“进入方式/页面内容/操作步骤/结果反馈”的字段列表。
- operation 模式缺少 `manual_modules`、`system_requirements`、`faq` 或 `glossary`，或 design 模式缺少 `design_spec`，都应回到业务理解阶段补充真实内容；脚本不得用分类模板兜底生成。
- 如果业务理解仍不充分，先提示用户补充产品说明，而不是直接生成泛泛描述。
