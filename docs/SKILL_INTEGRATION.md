# Agent Skill 集成说明

日期：2026-10-28。状态：项目级 Skill 集成说明；v0.1.0 的 Skill 契约测试通过。宿主兼容性和未验证边界见 README 与 SECURITY。

## 官方规范核对

已按一手来源核对（2026-10-28）：

- [Agent Skills Specification](https://agentskills.io/specification)：Skill 是包含 `SKILL.md` 的目录；`name` 必填，1–64 字符，仅小写字母/数字/连字符，不能以连字符开头或结尾、不能连续连字符，且必须与父目录名一致；`description` 必填，1–1024 字符；可选 `license`、`compatibility`、`metadata`、实验性 `allowed-tools`；建议 `SKILL.md` 少于 500 行；引用文件使用相对路径且尽量一层深。
- [Claude Code Skills](https://code.claude.com/docs/en/skills)：项目级发现路径为 `.claude/skills/<skill-name>/SKILL.md`；从启动目录向上到仓库根加载；支持 `/skill-name` 显式调用与基于 description 的自动调用；`allowed-tools` 是实验性、按调用回合预授权，且不限制其他工具；脚本可用 `${CLAUDE_SKILL_DIR}` 相对定位；Windows 上 `shell` 字段决定 Bash/PowerShell。
- [Codex Build skills](https://learn.chatgpt.com/docs/build-skills)：项目级发现路径为 `.agents/skills`，从当前工作目录向上扫描到仓库根；显式 `$skill`（或在 Codex IDE 中用 `/skills`）与基于 description 的自动选择；`SKILL.md` 必须含 `name` 与 `description`；可选 `agents/openai.yaml` 策略；脚本可选；支持符号链接的 skill 目录。

本 Skill 只用跨宿主规范字段：`name`、`description`、`compatibility`、`metadata`。未使用 `allowed-tools`、`disable-model-invocation`、`agents/openai.yaml` 或宿主私有字段，因此不声称对任何宿主的权限行为做统一保证。

## 文件布局

项目内保留两份**内容完全相同**的 Skill（不使用符号链接，避免宿主差异）：

```text
.claude/skills/ml-experiment-preflight/SKILL.md   # Claude Code 项目级发现
.agents/skills/ml-experiment-preflight/SKILL.md   # Codex 项目级发现
```

当前 SHA-256：

```text
a7cf67ff94fac04186530e1318b115c4d77504d8d87d52951baa42befa1f3a1c
```

两份文件由 `tests/test_skill_contract.py` 断言逐字节一致。修改时必须同步两份；不要只改一份。

`SKILL.md` 共 153 行（低于规范的 500 行建议上限），正文约 9.6k 字符；未包含规则实现代码或第二套检查引擎。

## CLI 前置条件

Skill 调用现有 Python CLI，不重新实现六条规则。前置条件：

- Python 3.11+；
- 安装包可导入：`python -m pip install .`（或开发时 `PYTHONPATH=<repo>/src`）；
- 可选 Git；Git 缺失时 Git 规则为 unknown，其余规则仍运行；
- 不需要网络或第三方运行时依赖。

安装后优先使用：

```text
ml-experiment-preflight check --root ROOT --entry ENTRY \
  --input-file INPUT --output-file OUTPUT --format json
```

如果没有 console script 但模块可导入，使用：

```text
python -m ml_experiment_preflight check --root ROOT --entry ENTRY \
  --input-file INPUT --output-file OUTPUT --format json
```

Skill 明确要求显式 `--root`、`--entry`、至少一个输入和一个输出；不遍历目录、不猜路径、不读取数据内容、不导入用户代码、不运行训练、不写项目文件。

## 宿主发现与调用

### Claude Code

- 发现路径：项目根 `.claude/skills/ml-experiment-preflight/SKILL.md`。
- 显式调用：消息开头使用 `/ml-experiment-preflight ...`；Skill 正文随即被加载。
- 自动调用：description 中的 "pre-training preflight / 训练前预检 / Git entry / input output conflict" 等触发词参与选择；是否自动加载由宿主版本、配置和权限决定。
- 权限：`SKILL.md` 未声明 `allowed-tools`。真实调用中 Bash 是否可用由宿主权限决定；Skill 要求用户确认，不自动写文件。
- Windows 注意：Claude Code 的 Bash/PowerShell 行为取决于宿主环境；本 Skill 的 CLI 本身不依赖 shell 特性。

### Codex

- 发现路径：项目根 `.agents/skills/ml-experiment-preflight/SKILL.md`；Codex 从 cwd 向上扫描到 repo root。
- 显式调用：`$ml-experiment-preflight ...`（IDE 中可用 `/skills`）。
- 自动调用：description 匹配；`agents/openai.yaml` 可禁用隐式调用，但本 Skill 未添加该文件，保持默认。
- Codex 按项目级发现路径读取 `SKILL.md`；console script 不可用时按正文回退到 `python -m`。

### AionUi

当前通过 **成员 Agent 手动方式**接入：成员 Agent 读取 `SKILL.md`，按其指令在本地运行 CLI。没有验证 AionUi 原生 Skill 目录发现、原生自动触发或原生权限模型，因此**不宣称 AionUi 原生 Skill 兼容**。

## 调用与安全边界

Skill 正文要求 Agent：

- 只用 CLI 的 JSON 结果，不把规则重写成提示词或模型判断；
- 对 `critical`、`warning`、`unknown` 都给出可执行整改建议，但不执行整改；
- 不把 `unknown` 说成 pass；不隐藏 `blocked`；不把 `incomplete` 说成 clear；
- 不运行训练、不导入项目代码、不读取训练数据内容、不递归扫描；
- 不执行 `git add/commit/checkout/restore/clean` 等写操作；
- 不上传报告或路径；私有项目建议本地运行并只分享脱敏 JSON；
- 在任何写操作、联网、安装依赖或 Git 状态变更前请求用户确认。

## 验证记录

合成示例的 CLI 结果（系统临时目录，非科研项目）：

| 场景 | 输入/输出 | CLI 实际结果 | 退出码 |
| --- | --- | --- | --- |
| normal | 已提交 `train.py`；存在 `data/input.bin`；输出 `runs/model.bin` 不存在 | 六规则全 pass；`overall=clear`，finding/unknown 均 0 | 0 |
| risk | 入口已修改；`data/missing.bin` 缺失；`runs/model.bin` 已存在 | GIT-002 warning `ENTRY_CHANGED`；PATH-001 critical `INPUT_MISSING`；OUT-001 warning `OUTPUT_EXISTS`；OUT-002 unknown；`overall=blocked`，3 findings/1 unknown | 2 |
| conflict | 输入=输出=`data/input.bin` | OUT-001 warning `OUTPUT_EXISTS`；OUT-002 critical `OUTPUT_EQUALS_INPUT_OR_ENTRY`；`overall=blocked`，2 findings/0 unknown | 1 |

两份 `SKILL.md` 字节一致；`tests/test_skill_contract.py` 7 项通过，检查两份副本一致、frontmatter/name/description 规范、CLI/JSON 解释、unknown/blocked 语义、边界词和绝对路径/宿主私有字段缺失。宿主原生发现、自动选择与权限行为随版本/配置变化，不作跨版本保证；AionUi 原生 Skill 发现未验证，成员 Agent 可手动读取 `SKILL.md` 并运行 CLI。

## 未验证事项

- 原生自动 Skill 选择未验证；AionUi 原生发现、自动触发、权限模型未验证，目前只声明项目级目录与成员 Agent 手动方式。
- Linux、Windows Python 3.12 本地和最终公开提交上的 GitHub Actions 运行未在本文件内验证；以 README/SECURITY 的兼容性声明为准。
- Skill 依赖 CLI 已安装或可导入；未测试未安装 CLI 时的用户提示与安装流程。
- 未验证所有宿主版本、策略/企业配置、Windows PowerShell/Bash 差异、真实科研项目的误报/接受度。
- 未修改全局 Agent 配置。
