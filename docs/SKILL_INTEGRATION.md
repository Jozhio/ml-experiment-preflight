# Agent Skill 集成说明

日期：2026-10-29。状态：项目级 Skill 集成说明；v0.1.0 的 Skill 契约测试通过。宿主兼容性和未验证边界见 README 与 SECURITY。

## CLI 与 Skill 的关系

CLI 是唯一的检查器。Agent Skill 是一份说明，让 Claude Code 或 Codex 调用同一个 CLI、解释 JSON，并避免不安全操作。

- 先安装 CLI；Skill 不会安装它，也不会替代它。
- Skill 不提供沙箱；Bash/工具权限仍由宿主控制。
- 本项目不重新实现六条规则，也不让模型自行判断 pass/finding/unknown。

## 官方发现约定

以下路径按一手文档核对（2026-10-29 可访问）：

- [Claude Code Skills](https://code.claude.com/docs/en/skills)：项目级发现路径为 `.claude/skills/<skill-name>/SKILL.md`，从启动目录向上到仓库根加载；支持 `/skill-name` 显式调用和基于 description 的自动选择。
- [Codex Build skills](https://learn.chatgpt.com/docs/build-skills)：项目级发现路径为 `.agents/skills`，从当前工作目录向上扫描到仓库根；支持 `$skill` 显式调用和基于 description 的选择。
- [Agent Skills 规范](https://agentskills.io/specification)：Skill 目录必须包含 `SKILL.md`，`name` 与 `description` 为必填字段。

宿主原生发现、自动选择和权限行为随版本/配置变化；本项目不声称跨宿主行为一致。

## 目录布局

仓库保留两份内容相同的 Skill（不使用符号链接，避免宿主差异）：

```text
.claude/skills/ml-experiment-preflight/SKILL.md   # Claude Code 项目级发现
.agents/skills/ml-experiment-preflight/SKILL.md   # Codex 项目级发现
```

当前 SHA-256：

```text
a7cf67ff94fac04186530e1318b115c4d77504d8d87d52951baa42befa1f3a1c
```

两份文件由 `tests/test_skill_contract.py` 断言逐字节一致。修改时必须同步两份，不要只改一份。`SKILL.md` 共 153 行（低于规范的 500 行建议上限），正文约 9.6k 字符；不包含规则实现代码或第二套检查引擎。

## 安装 CLI 前置条件

Skill 调用现有 Python CLI，不重新实现六条规则。前置条件：

- Python 3.11+；
- 已按 [README 快速开始](../README.zh-CN.md#快速开始) 安装 CLI，或开发时设置 `PYTHONPATH=<repo>/src`；
- Git 可选；Git 缺失时 Git 规则为 unknown，其余规则仍运行；
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

Skill 要求显式提供 `--root`、`--entry`、至少一个输入和一个输出；不遍历目录、不猜路径、不读取数据内容、不导入用户代码、不运行训练、不写项目文件。

## 把 Skill 复制到自己的项目

Windows PowerShell——在 `ml-experiment-preflight` 克隆目录中执行：

```powershell
$src = (Resolve-Path .\.claude\skills\ml-experiment-preflight).Path
cd C:\path\to\your-project
New-Item -ItemType Directory -Force .\.claude\skills\ml-experiment-preflight | Out-Null
Copy-Item -Recurse -Force "$src\*" .\.claude\skills\ml-experiment-preflight
```

使用 Codex 时，把 `$src` 和目标路径中的 `.claude` 改为 `.agents`。

Linux——在 `ml-experiment-preflight` 克隆目录中执行：

```bash
src="$(pwd)/.claude/skills/ml-experiment-preflight"
cd "$HOME/projects/your-project"
mkdir -p .claude/skills/ml-experiment-preflight
cp -R "$src/." .claude/skills/ml-experiment-preflight/
```

使用 Codex 时，把 `src` 和目标路径中的 `.claude` 改为 `.agents`。请把示例中的项目路径替换为你自己的目录。

## 调用方式

### Claude Code

- 项目级路径：`.claude/skills/ml-experiment-preflight/SKILL.md`。
- 显式调用：消息开头使用 `/ml-experiment-preflight ...`。
- 自然语言：description 中的 "pre-training preflight / 训练前预检 / Git entry / input output conflict" 等触发词参与选择；是否自动加载由宿主版本、配置和权限决定。
- 权限：`SKILL.md` 未声明 `allowed-tools`；Bash 是否可用由宿主权限决定。

### Codex

- 项目级路径：`.agents/skills/ml-experiment-preflight/SKILL.md`；Codex 从工作目录向上扫描到仓库根。
- 显式调用：`$ml-experiment-preflight ...`（IDE 中可用 `/skills`）。
- 自动选择：description 匹配；`agents/openai.yaml` 可禁用隐式调用，但本 Skill 未添加该文件，保持默认。

### AionUi

没有验证 AionUi 原生 Skill 目录发现、自动触发或权限模型。你可以手动读取 `SKILL.md` 并运行 CLI，但这不等于原生 AionUi 兼容。

## 调用与安全边界

Skill 正文要求宿主：

- 只用 CLI 的 JSON 结果，不把规则重写成提示词或模型判断；
- 对 `critical`、`warning`、`unknown` 都给出可执行整改建议，但不执行整改；
- 不把 `unknown` 说成 pass；不隐藏 `blocked`；不把 `incomplete` 说成 clear；
- 不运行训练、不导入项目代码、不读取训练数据内容、不递归扫描；
- 不执行 `git add/commit/checkout/restore/clean` 等写操作；
- 不上传报告或路径；私有项目建议本地运行并只分享脱敏 JSON；
- 在任何写操作、联网、安装依赖或 Git 状态变更前请求用户确认。

## 验证范围

合成示例的 CLI 结果（系统临时目录，非科研项目）：

| 场景 | 输入/输出 | CLI 实际结果 | 退出码 |
| --- | --- | --- | --- |
| normal | 已提交 `train.py`；存在 `data/input.bin`；输出 `runs/model.bin` 不存在 | 六规则全 pass；`overall=clear`，finding/unknown 均 0 | 0 |
| risk | 入口已修改；`data/missing.bin` 缺失；`runs/model.bin` 已存在 | GIT-002 warning `ENTRY_CHANGED`；PATH-001 critical `INPUT_MISSING`；OUT-001 warning `OUTPUT_EXISTS`；OUT-002 unknown；`overall=blocked`，3 findings/1 unknown | 2 |
| conflict | 输入=输出=`data/input.bin` | OUT-001 warning `OUTPUT_EXISTS`；OUT-002 critical `OUTPUT_EQUALS_INPUT_OR_ENTRY`；`overall=blocked`，2 findings/0 unknown | 1 |

两份 `SKILL.md` 字节一致；`tests/test_skill_contract.py` 7 项通过，检查两份副本一致、frontmatter/name/description 规范、CLI/JSON 解释、unknown/blocked 语义、边界词和绝对路径/宿主私有字段缺失。宿主原生发现、自动选择与权限行为随版本/配置变化，不作跨版本保证。

## 未验证事项

- 全新 Agent 的原生自动选择未独立测量；AionUi 原生发现、自动触发、权限模型未验证。
- Linux、Windows Python 3.12 本地和最终公开提交上的 GitHub Actions 运行未在本文件内验证；以 README/SECURITY 的兼容性声明为准。
- Skill 依赖 CLI 已安装或可导入；未测试未安装 CLI 时的用户提示与安装流程。
- 未验证所有宿主版本、策略/企业配置、Windows PowerShell/Bash 差异、真实科研项目的误报/接受度。
