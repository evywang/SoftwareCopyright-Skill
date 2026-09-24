# AGENTS.md

Skill repository that generates Chinese software copyright (软件著作权/软著) application
materials from a real user project. The actual skill is `software-copyright-materials/`
only — the repo root is a wrapper (README, demo, plugin manifest), not a skill. Users
install by copying `software-copyright-materials/` into their agent's skills directory;
never treat the repo root as the skill.

## Layout

- `software-copyright-materials/SKILL.md` — the skill itself; normative workflow spec.
  Any behavior change must be reflected here (and its `version` frontmatter bumped).
- `software-copyright-materials/references/` — stage-specific reference docs
  (application_fields, business_understanding_rules, code_selection_rules,
  copyright_material_rules, manual_structure, technical_design_structure,
  officecli_backend, playwright_cli_screenshots). Read per stage, not all at
  once; keep in sync with SKILL.md.
- `software-copyright-materials/scripts/` — stdlib-only Python 3.10+ CLI tools
  (argparse in, JSON out with `ensure_ascii=False`). No third-party Python deps
  (no python-docx, ever). `common.py` holds shared helpers/exclusions.
- `software-copyright-materials/tests/` — unittest suite.
- `software-copyright-materials/agents/openai.yaml` — agent metadata.
- `.claude-plugin/plugin.json` — plugin manifest (own version number).
- `生成demo/软件著作权申请资料/` — committed sample output. `.gitignore` blocks
  `软件著作权申请资料/`, images, and PDFs everywhere but re-includes this demo; don't
  commit generated materials anywhere else.
- `docs/screenshots/` — README images only.

## Commands

```bash
# Run tests (from the skill directory)
cd software-copyright-materials && python3 -m unittest discover -s tests

# Syntax check scripts
python3 -m compileall -q software-copyright-materials/scripts
```

The suite is platform-portable (run it on any OS). User-facing runtime strings say
"coding agent", never a specific agent product, and the OfficeCLI install command is
platform-aware via `officecli_install_command()` — keep both properties when editing.
There is no linter/formatter config; match existing style.

## Architecture rules (load-bearing)

- **Division of labor:** Python scripts only collect evidence, validate fields,
  paginate/wrap code, run gates, and orchestrate OfficeCLI. Business judgment
  (industry, target users, features, manual structure, which code to extract) is made
  by the model reading the project — never by script keyword tables or templates.
- **DOCX only via OfficeCLI:** globally installed, pinned to `1.0.151`,
  `OFFICECLI_SKIP_UPDATE=1` + `OFFICECLI_NO_AUTO_RESIDENT=1`. Python never
  unpacks/writes DOCX packages. No Pandoc/LibreOffice/python-docx/.NET/portable
  fallbacks. If OfficeCLI is missing/mismatched: stop, ask the user; never fake a DOCX.
- **No fabricated code:** code material must come from real project source files,
  extracted whole-file (blank lines dropped); no invented source.
- **Source discovery is content-based:** no language-extension whitelists; scan
  readable text and exclude known docs/config/binaries/generated files.
- **Two prose document kinds:** `manual_kind` in 业务理解.json decides the user-facing
  document — `operation` (GUI software → 操作手册 with page modules and screenshots) or
  `design` (no-GUI software: embedded firmware, drivers, libraries, services →
  技术方案文档, a design-spec skeleton with module/interface tables, no screenshot
  stage, visible 【图预留】 placeholders). File names come from
  `PROSE_DOC_FILES` in common.py; keep both kinds' gates/filenames in sync when editing.
- **Mandatory human gates** recorded via `scripts/confirm_stage.py`: environment,
  project, business, application-fields, code-selection, screenshot-method
  (operation kind only), markdown. No "default continue if user silent".
  Confirmations are content-fingerprinted; editing a confirmed draft invalidates
  its gate.
- **Fixed output tree:** everything under `软件著作权申请资料/` in the user's project
  directory (never /tmp for real runs): drafts in `草稿/`, final Word/TXT only in
  `正式资料/`. Software name/version in final files come from the confirmed
  `草稿/申请表信息.md`.
- **Pagination:** code docs use continuous paragraphs (no manual page breaks); Word
  auto-paginates. Front-30/back-30 pages mode must yield exactly 30+30 pages,
  verified via `officecli view ... stats --page-count`; recalibrate selection instead
  of forcing page breaks.
- **Screenshots:** only Playwright CLI (`@playwright/cli@0.1.20`, global npm, resolved
  via PATH then `npm prefix -g`) or user-supplied images; `skip` is a valid choice and
  must leave visible screenshot placeholders. Never fake capture success.

## Conventions

- Skill docs, prompts, and generated output are in Chinese (output filenames like
  `草稿`, `正式资料`, `技术方案文档.md`, `截图清单.json` are literal). Commit messages
  are English conventional-commit style (`feat:`, `fix:`, `docs:`, `refactor:`);
  integration lands via a `dev` branch merged into `main`.
- Final Word text is plain black; no hyperlinks/theme colors; Markdown links become
  plain text; DOCX theme fonts normalized to SimSun/Times New Roman (WPS compat).
- Operation manuals follow the traditional skeleton (一、相关文档 … 术语表) with
  Chinese-numeral headings, tables only for 相关文档/系统要求, prose over bullet
  lists, and an anti-"AI flavor" self-check log (`操作手册自检记录.md/json`).
  Design documents follow the 设计说明书 skeleton (一、引言 / 二、软件总体设计 /
  三、软件功能描述 / 四、接口设计) with self-check `技术方案文档自检记录.md/json`;
  GUI vocabulary (页面/按钮/点击…) is forbidden in design docs.

## Before editing sensitive areas

Read first: `software-copyright-materials/SKILL.md` (whole workflow),
`references/officecli_backend.md` (DOCX backend contract), and the tests matching the
area you touch — tests encode many SKILL.md rules (pagination, gates, source
discovery, builder behavior).
