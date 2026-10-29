# ML Experiment Preflight

**版本 0.1.0 — 预发布。**

`ml-experiment-preflight` 是一个只读、离线的训练前预检工具。你显式提供项目根、入口脚本、输入路径和输出路径；它在启动训练前给出确定性的 Git 状态、输入缺失/类型错误，以及输出与输入冲突证据。

它**不**检查训练数据内容、不做数据质量评估、不估算 GPU/VRAM、不求解依赖、不计算可复现性分数，也不运行训练。

## 快速开始

要求：**Python 3.11+**。Git 对 CLI 是可选的；Git 示例需要 Git。

### 1. 克隆或下载

```bash
git clone https://github.com/Jozhio/ml-experiment-preflight.git
cd ml-experiment-preflight
```

如果下载的是 ZIP，请进入解压后的目录（目录名可能以 `-main` 结尾）。请把本文中的占位路径替换为你机器上的真实路径。

### 2. 在虚拟环境中安装 CLI

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\ml-experiment-preflight.exe --help
```

Linux：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
ml-experiment-preflight --help
```

本项目不发布 PyPI 包，请从当前克隆目录安装。启用 build isolation 时，`pip install .` 可能需要联网获取构建依赖 `setuptools>=61` 和 `wheel`；安装后的工具本身离线运行。

### 3. 运行仓库自带的合成示例

仓库自带三个合成项目，只使用占位文件和本地 Git 仓库；`train.py` 永远不会被执行，也不会读取真实科研数据。

Windows PowerShell（在仓库根目录运行）：

```powershell
.\.venv\Scripts\python.exe -B .\examples\verify_examples.py
```

Linux（在仓库根目录运行）：

```bash
.venv/bin/python -B examples/verify_examples.py
```

预期结果：

| 示例 | overall | 退出码 | 关注点 |
| --- | --- | --- | --- |
| `normal` | `clear` | `0` | 六条规则全部 pass，覆盖完整 |
| `risk` | `blocked` | `2` | `ENTRY_CHANGED`、`INPUT_MISSING`、`OUTPUT_EXISTS`；`OUT-002` 为 `unknown`；unknown 不是 pass |
| `conflict` | `blocked` | `1` | `OUTPUT_EQUALS_INPUT_OR_ENTRY` critical；没有 unknown |

`risk` 虽然是 `blocked`，但因存在不完整覆盖而退出 `2`。请先读 JSON，再把退出码作为辅助信号。

校验器优先使用 PATH 上的已安装 `ml-experiment-preflight` 命令；使用上面的显式 venv Python 时，它可能回退到当前克隆目录的源码。两种方式运行的是同一份代码。

### 4. 在自己的项目上运行

请替换占位路径；相对路径以 `--root` 为基准，不使用当前 shell 目录。

Windows PowerShell：

```powershell
.\.venv\Scripts\ml-experiment-preflight.exe check `
  --root C:\path\to\your-project `
  --entry train.py `
  --input-file data\input.bin `
  --output-file runs\model.bin `
  --format json
```

Linux：

```bash
.venv/bin/ml-experiment-preflight check \
  --root "$HOME/projects/your-project" \
  --entry train.py \
  --input-file data/input.bin \
  --output-file runs/model.bin \
  --format json
```

检查器只读取元数据和有限的本地 Git 元数据；它不会运行 `train.py`、导入项目代码、读取输入内容、写入项目文件或修改 Git 状态。

## 结果含义

六条规则各自返回三种状态：

- `pass`：该规则在其限定观察范围内没有发现预定义问题；这不是通用安全声明。
- `finding`：观察到具体风险。`warning` 需要复核；`critical` 是高优先级冲突或目标缺失。
- `unknown`：证据不足。**绝不能把 unknown 说成 pass、clean 或 verified。**

`overall` 的优先级：存在 critical finding → `blocked`；否则覆盖不完整 → `incomplete`；否则有 warning → `review`；否则 `clear`。

| 退出码 | 含义 |
| --- | --- |
| `0` | `clear`：六规则全部 pass 且覆盖完整 |
| `1` | 有已知 finding 且覆盖完整（`review` 或 `blocked`） |
| `2` | 覆盖不完整、用法错误或报告构建失败 |

退出码 `2` 仍可能带有有效 JSON 报告。请先解析 stdout；如果 stdout 不是 JSON，按工具失败（`USAGE_ERROR` 或 `REPORT_ERROR`）处理，不要当作项目结论。

## 六条规则

报告固定包含以下顺序的六条结果。

| 规则 | 检查内容 | finding | `unknown` 示例 |
| --- | --- | --- | --- |
| `GIT-001` | 根是否为普通本地 `.git` 仓库、HEAD 是否可解析、仓库顶层是否等于 `--root`。 | warning `NO_REPOSITORY`、`NO_HEAD` | `GIT_UNAVAILABLE`、`GIT_ROOT_MISMATCH`、`UNSUPPORTED_GIT_LAYOUT`、`GIT_TIMEOUT`、`GIT_ERROR` |
| `GIT-002` | 仅检查显式入口（且已跟踪）的暂存区/工作区变化。 | warning `ENTRY_CHANGED` | `ENTRY_UNAVAILABLE`、`ENTRY_NOT_TRACKED`、`GIT_ENTRY_FLAG_UNSUPPORTED`、`GIT_CONTEXT_UNKNOWN`、`GIT_TIMEOUT`、`GIT_ERROR`、`GIT_OUTPUT_LIMIT` |
| `GIT-003` | 显式入口是否在 Git 索引中。 | warning `ENTRY_NOT_TRACKED` | `ENTRY_UNAVAILABLE`、`GIT_CONTEXT_UNKNOWN`、`GIT_TIMEOUT`、`GIT_ERROR` |
| `PATH-001` | 入口和显式输入是否存在、file/dir 类型是否正确；入口物理目标是否留在根内。 | critical `ENTRY_MISSING`、`INPUT_MISSING`、`TYPE_MISMATCH`、`ENTRY_ESCAPES_ROOT` | `PERMISSION_DENIED`、`SYMLINK_UNRESOLVED`、`PATH_IO_ERROR`、`EVIDENCE_LIMIT` |
| `OUT-001` | 每个输出是否存在、类型是否匹配、父链是否可确认。 | warning `OUTPUT_EXISTS`；critical `OUTPUT_TYPE_MISMATCH` | `OUTPUT_PARENT_UNKNOWN`、`SYMLINK_UNRESOLVED`、`PERMISSION_DENIED`、`PATH_IO_ERROR` |
| `OUT-002` | 输出是否等于输入/入口、包含输入/入口/根，或位于输入目录内；已存在目标用 `Path.samefile` 识别同一文件。 | critical `OUTPUT_EQUALS_INPUT_OR_ENTRY`、`OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT`；warning `OUTPUT_INSIDE_INPUT_DIR` | `PATH_COMPARISON_UNKNOWN`、`SYMLINK_UNRESOLVED`、`OUTPUT_PARENT_UNKNOWN`、`EVIDENCE_LIMIT` |

Git 是可选的；Git 不可用时 Git 规则为 `unknown`，路径/输出规则仍运行。无法判断时绝不能写成 `pass`。

## 路径与只读行为

| 参数 | 含义 | 相对基准 | 要求 |
| --- | --- | --- | --- |
| `--root` | 项目目录，作为路径基准和 Git 根 | 当前目录 | 必须存在且为目录 |
| `--entry` | 训练入口脚本 | `--root` | 必须存在且为文件；物理目标必须留在 `--root` 内；不会被执行 |
| `--input-file` / `--input-dir` | 显式输入 | `--root` | 可以在根外；只读元数据；不读取文件内容，不枚举目录 |
| `--output-file` / `--output-dir` | 显式输出 | `--root` | 可以在根外；父目录可解析时目标可以不存在；检查器不会创建它 |

至少提供一个输入和一个输出，每组最多 32 个。不支持通配符、环境变量展开、`@file` 或自动目录发现。路径必须显式提供；检查器不扫描项目、不猜测缺失路径。

本文路径约定：`ml-experiment-preflight` 是克隆目录；`train.py`、`data/input.bin`、`runs/model.bin` 是相对 `--root` 的路径；`C:\path\to\your-project` 和 `$HOME/projects/your-project` 是需要你替换的占位路径。`.claude/...`、`.agents/...`、`examples/...` 和 `docs/...` 是仓库内路径。

检查是只读快照：不运行训练、不导入项目模块、不读取数据内容、不创建文件、不修改 Git 状态。文本输出供人阅读；Agent 应使用 `--format json`。没有 `--write`、`--fix`、`--upload` 或 `--scan-all`。

JSON 结构示例（六条结果始终存在；完整 schema 见 [docs/CLI_CONTRACT.md](docs/CLI_CONTRACT.md)）：

```json
{
  "schema_version": "1.0",
  "tool_version": "0.1.0",
  "scope": {
    "root_ref": "root",
    "entry_ref": "entry",
    "input_count": 1,
    "output_count": 1,
    "git_status_scope": "entry_only",
    "untracked_files_scanned": false
  },
  "overall": {"status": "clear", "finding_count": 0, "unknown_count": 0},
  "results": [
    {"rule_id": "GIT-001", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": [{"code": "REPOSITORY_WITH_HEAD", "refs": ["root"]}]},
    {"rule_id": "GIT-002", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": [{"code": "ENTRY_UNCHANGED", "refs": ["entry"]}]},
    {"rule_id": "GIT-003", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": [{"code": "ENTRY_TRACKED", "refs": ["entry"]}]},
    {"rule_id": "PATH-001", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": []},
    {"rule_id": "OUT-001", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": []},
    {"rule_id": "OUT-002", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": []}
  ]
}
```

## Agent Skill 安装与使用

CLI 是检查器；Agent Skill 是可选的说明，用于让 Claude Code 或 Codex 调用同一个 CLI、解释 JSON，并避免不安全操作。请先安装 CLI；Skill 不负责安装，也不是沙箱。

### 项目级 Skill 路径

| 宿主 | 项目中的路径 | 调用方式 |
| --- | --- | --- |
| Claude Code | `.claude/skills/ml-experiment-preflight/SKILL.md` | `/ml-experiment-preflight ...` 或自然语言请求 |
| Codex | `.agents/skills/ml-experiment-preflight/SKILL.md` | `$ml-experiment-preflight ...` 或 Codex IDE 中的 `/skills` |

这些路径遵循官方约定：[Claude Code Skills](https://code.claude.com/docs/en/skills)、[Codex Build skills](https://learn.chatgpt.com/docs/build-skills) 和 [Agent Skills 规范](https://agentskills.io/specification)。宿主原生发现、自动选择和权限行为随宿主版本/配置变化；本项目不声称跨宿主行为一致。AionUi 原生 Skill 发现未验证；你可以手动读取 `SKILL.md` 并运行 CLI，但这不等于原生 AionUi 兼容。

仓库中两份副本逐字节一致（SHA-256 `a7cf67ff94fac04186530e1318b115c4d77504d8d87d52951baa42befa1f3a1c`）。如果同时安装到两个宿主，请保持两份副本一致。

### 把 Skill 复制到自己的项目

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

使用 Codex 时，把 `src` 和目标路径中的 `.claude` 改为 `.agents`。请把 `C:\path\to\your-project` / `$HOME/projects/your-project` 替换为你的项目目录。

Skill 要求显式提供 `--root`、`--entry`、输入和输出；只运行只读 CLI、解释 JSON，不运行训练、不导入项目代码、不读取数据内容、不写 Git 状态，也不会擅自执行整改。详见 [Claude Code Skill](.claude/skills/ml-experiment-preflight/SKILL.md) 和 [docs/SKILL_INTEGRATION.md](docs/SKILL_INTEGRATION.md)。

## 合成示例

[`examples/`](examples/) 提供 `normal`、`risk`、`conflict` 三个合成项目。每个 runner 会把 fixture 复制到临时目录、创建本地 Git 仓库、运行 CLI，然后删除临时目录。不读取真实数据，`train.py` 永远不会被执行。

在仓库根目录运行：

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -B .\examples\verify_examples.py
```

Linux：

```bash
.venv/bin/python -B examples/verify_examples.py
```

单独运行：

```powershell
powershell -NoProfile -File .\examples\normal\run.ps1
powershell -NoProfile -File .\examples\risk\run.ps1
powershell -NoProfile -File .\examples\conflict\run.ps1
```

```bash
bash examples/normal/run.sh
bash examples/risk/run.sh
bash examples/conflict/run.sh
```

`risk` 和 `conflict` 脚本故意以 `2` 和 `1` 退出；这是预期结果，不是脚本错误。详见 [examples/README.md](examples/README.md)。

## 卸载

Windows PowerShell（在仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y ml-experiment-preflight
Remove-Item -Recurse -Force .venv
```

Linux（在仓库根目录）：

```bash
. .venv/bin/activate
python -m pip uninstall -y ml-experiment-preflight
deactivate
rm -rf .venv
```

如果 console script 不可用但包已安装/可导入，可使用 `python -m ml_experiment_preflight check ...`，参数相同。

## 隐私与限制

- **只读**：读取文件系统元数据和有限的本地 Git 元数据；不运行训练或用户代码、不导入项目模块、不读取数据内容、不创建文件、不修改 Git 状态。
- **仅显式路径**：不扫描项目、不枚举输入目录、不猜测缺失路径。
- **离线意图**：不上传、不遥测、不调用网络 API。明显的 UNC 路径会拒绝或标为 `unknown`；用户指定的映射盘/网络卷上的元数据读取仍可能触发操作系统网络 I/O。
- **脱敏报告**：JSON 只含规则/证据码和符号引用；不含绝对路径、文件名、环境变量值或 Git 文件名。原始命令和宿主/工具日志仍可能含路径；私有项目请本地运行，只分享脱敏 JSON。
- **Git 可选**：Git 缺失或布局不支持时为 `unknown`，不是 `pass`。Git 只从受检查根和当前目录之外的绝对 PATH 目录解析；调用方控制的 PATH 仍是信任假设。
- **静态快照**：TOCTOU、并发修改、符号链接、权限、网络路径和跨卷身份仍有限制。UNC 根/入口会拒绝；UNC 输入/输出为 `unknown`；映射盘尚不能穷尽识别。Windows 只保证终止直接子进程，不保证完整进程树。
- **不是数据或可复现性审计**：无数据质量、标签、schema、GPU/CUDA、依赖求解、性能或完整可复现性证明。
- **Skill 权限**：Skill 不声明 `allowed-tools`；Bash/工具调用仍受宿主权限模型约束。不要把 Skill 文本当作沙箱。

安全策略和私密漏洞报告见 [SECURITY.md](SECURITY.md)。

## 兼容性

只列出实际运行过的环境；标为“未运行”的项不构成支持声明。

| 环境 | 状态 |
| --- | --- |
| Windows 10.0.19045；Python 3.11.0；Git 2.54.0.windows.1 | 最终候选本地实测：127 项 unittest，0 failures，5 skips，exit 0；三个合成示例均验证通过。 |
| Linux / Windows Python 3.12（本地） | 本地未运行。 |
| 公开 GitHub Actions | [初始公开候选运行](https://github.com/Jozhio/ml-experiment-preflight/actions/runs/40710712840) 的四个 Job（Ubuntu 24.04 / Windows；Python 3.11/3.12）全部通过。每个新提交（包括文档提交）都必须通过自己的 CI 运行后才能合并。 |
| Claude Code / Codex 项目级 Skill | 提供两条发现路径和字节一致的两份副本。未在公开源码树中独立复核宿主原生发现；行为随宿主版本变化。 |
| AionUi | 不宣称原生 Skill 发现。 |

本地 Windows 测试有 5 项跳过：4 项 POSIX 专项 + 1 项 Windows 符号链接权限测试。

## 许可证与贡献

MIT，见 [LICENSE](LICENSE)。运行时没有第三方依赖；`setuptools>=61` 与 `wheel` 是构建期依赖。Python 和 Git 是外部工具，不是随包分发组件。

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)
- [CLI 契约](docs/CLI_CONTRACT.md)
- [规则规范](docs/RULE_SPECIFICATION.md)
- [合成示例](examples/README.md)
- [竞品分析](docs/COMPETITOR_ANALYSIS.md)

不要在 issue、测试、示例或报告中包含 API Key、凭据、私人科研数据、绝对用户路径或专有项目材料。检查器和示例只面向合成样例。
