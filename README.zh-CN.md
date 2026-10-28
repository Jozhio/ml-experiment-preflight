# ML Experiment Preflight

**版本 0.1.0 — 预发布。**

`ml-experiment-preflight` 是一个离线、只读的训练前预检工具。它只接受用户**显式指定**的项目根、训练入口、输入路径和输出路径，用确定性证据报告 Git 状态、显式输入路径以及输出/输入冲突。

它的范围刻意很窄：不检查训练数据内容、不做数据质量评估、不估算 GPU/VRAM、不求解依赖、不计算可复现性分数，也不运行训练。

## 产品价值

在启动长时间或昂贵的训练前，静态检查可以发现少数代价较高的启动配置错误：

- 入口脚本有未提交修改或未被 Git 跟踪；
- 仓库没有可用 HEAD；
- 显式输入不存在或 file/dir 类型不符；
- 输出已存在、类型不符，或与输入/入口/根发生冲突。

它提供的是快速、可复核的检查时点快照，不保证训练一定成功。检查器独立于 Agent，可直接在终端运行；Agent Skill 只负责解释结构化结果。

本项目不宣称独特市场定位。相近工具包括 MLflow、DVC、ReproZip、Gitleaks，以及 `preflight-ml`、`trainproof`、`preflight-data` 等训练前检查工具。参见 [docs/COMPETITOR_ANALYSIS.md](docs/COMPETITOR_ANALYSIS.md)。

## 六条规则

报告固定按以下顺序给出六条结果。`pass` 只表示该规则在其限定观察范围内没有发现预定义问题，不是通用安全声明。

| 规则 | 检查内容 | finding | `unknown` 示例 |
| --- | --- | --- | --- |
| `GIT-001` | 根是否为普通本地 `.git` 仓库、HEAD 是否可解析、仓库顶层是否等于 `--root`。 | warning `NO_REPOSITORY`、`NO_HEAD` | `GIT_UNAVAILABLE`、`GIT_ROOT_MISMATCH`、`UNSUPPORTED_GIT_LAYOUT`、`GIT_TIMEOUT`、`GIT_ERROR` |
| `GIT-002` | 仅检查显式入口（且已跟踪）的暂存区/工作区变化。 | warning `ENTRY_CHANGED` | `ENTRY_UNAVAILABLE`、`ENTRY_NOT_TRACKED`、`GIT_ENTRY_FLAG_UNSUPPORTED`、`GIT_CONTEXT_UNKNOWN`、`GIT_TIMEOUT`、`GIT_ERROR`、`GIT_OUTPUT_LIMIT` |
| `GIT-003` | 显式入口是否在 Git 索引中。 | warning `ENTRY_NOT_TRACKED` | `ENTRY_UNAVAILABLE`、`GIT_CONTEXT_UNKNOWN`、`GIT_TIMEOUT`、`GIT_ERROR` |
| `PATH-001` | 入口和显式输入是否存在、file/dir 类型是否正确；入口物理目标是否留在根内。 | critical `ENTRY_MISSING`、`INPUT_MISSING`、`TYPE_MISMATCH`、`ENTRY_ESCAPES_ROOT` | `PERMISSION_DENIED`、`SYMLINK_UNRESOLVED`、`PATH_IO_ERROR`、`EVIDENCE_LIMIT` |
| `OUT-001` | 每个输出是否存在、类型是否匹配、父链是否可确认。 | warning `OUTPUT_EXISTS`；critical `OUTPUT_TYPE_MISMATCH` | `OUTPUT_PARENT_UNKNOWN`、`SYMLINK_UNRESOLVED`、`PERMISSION_DENIED`、`PATH_IO_ERROR` |
| `OUT-002` | 输出是否等于输入/入口、包含输入/入口/根，或位于输入目录内；已存在目标用 `Path.samefile` 识别同一文件。 | critical `OUTPUT_EQUALS_INPUT_OR_ENTRY`、`OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT`；warning `OUTPUT_INSIDE_INPUT_DIR` | `PATH_COMPARISON_UNKNOWN`、`SYMLINK_UNRESOLVED`、`OUTPUT_PARENT_UNKNOWN`、`EVIDENCE_LIMIT` |

Git 是可选的；Git 不可用时 Git 规则为 `unknown`，路径/输出规则仍运行。无法判断时绝不能写成 `pass`。

## 安装

要求 **Python 3.11+**。CLI 运行时无第三方依赖；Git 可选（Git 规则和 Git 示例需要）。当前没有 PyPI 发布，请从源码安装。

### Windows PowerShell（干净环境）

```powershell
cd F:\path\to\ml-experiment-preflight
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
$env:PATH = (Resolve-Path .\.venv\Scripts).Path + ";" + $env:PATH
ml-experiment-preflight --help
```

启用 build isolation 时，`pip install .` 可能需要联网获取声明的构建依赖 `setuptools>=61` 和 `wheel`；安装后的工具本身离线运行。

### Linux Bash（干净环境）

```bash
cd /path/to/ml-experiment-preflight
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
ml-experiment-preflight --help
```

### 卸载

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y ml-experiment-preflight
Remove-Item -Recurse -Force .venv
```

Linux Bash：

```bash
. .venv/bin/activate
python -m pip uninstall -y ml-experiment-preflight
deactivate
rm -rf .venv
```

更完整的干净环境验证步骤见 [安装验证](#安装验证)。

## CLI 使用

必须显式提供 `--root`、`--entry`、至少一个输入和至少一个输出；输入/输出各最多 32 个。相对路径以 `--root` 为基准，不使用当前 shell 目录作为项目根。

### Windows PowerShell

```powershell
ml-experiment-preflight check --root C:\work\demo --entry train.py --input-file data\input.bin --output-file runs\model.bin --format json
```

### Linux Bash

```bash
ml-experiment-preflight check --root /work/demo --entry train.py --input-file data/input.bin --output-file runs/model.bin --format json
```

目录目标使用 `--input-dir`/`--output-dir`。`--format` 默认 `text`，Agent 必须显式使用 `--format json`。不支持 `--write`、`--fix`、`--upload`、`--scan-all` 或自动目录发现。

如果 console script 不可用但包已安装/可导入，可使用：

```text
python -m ml_experiment_preflight check --root ROOT --entry ENTRY --input-file INPUT --output-file OUTPUT --format json
```

## JSON 报告

有效检查的 stdout 是一个 UTF-8 JSON 对象。报告不含绝对路径、文件名、用户名、环境变量值或 Git 文件名；目标只用 `root`、`entry`、`input:N`、`output:N` 引用。

正常结果的结构示例（具体字段与证据码以 CLI 实际 JSON 为准）：

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

`overall.status` 优先级：有 critical finding → `blocked`；否则有任何覆盖不完整 → `incomplete`；否则有 warning finding → `review`；否则 `clear`。`unknown` 不是 pass，`blocked` 不能被隐藏。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | `clear`：六规则全部 pass 且覆盖完整 |
| `1` | 有已知 finding 且覆盖完整（`review` 或 `blocked`） |
| `2` | 任意覆盖不完整、参数错误或报告构建失败 |

退出码 `2` 仍可能带有效 JSON；必须先解析 stdout，不能只凭退出码下结论。stdout 不是 JSON 时，报告工具错误（`USAGE_ERROR`/`REPORT_ERROR`），不要推断项目状态。

## Agent Skill 安装与调用

仓库同时提供两种项目级发现路径：

```text
.claude/skills/ml-experiment-preflight/SKILL.md   # Claude Code
.agents/skills/ml-experiment-preflight/SKILL.md   # Codex
```

两份内容逐字节一致，SHA-256 为 `a7cf67ff94fac04186530e1318b115c4d77504d8d87d52951baa42befa1f3a1c`，目标 Skill 版本为 `0.1.0`。必须先安装 CLI；Skill 只调用 CLI。

### 复制到自己的项目

Windows PowerShell：

```powershell
$dest = "C:\work\my-project\.claude\skills\ml-experiment-preflight"
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -Recurse -Force .\.claude\skills\ml-experiment-preflight\* $dest
```

Linux Bash：

```bash
dest=/work/my-project/.claude/skills/ml-experiment-preflight
mkdir -p "$dest"
cp -R .claude/skills/ml-experiment-preflight/. "$dest/"
```

Codex 复制到 `.agents/skills/ml-experiment-preflight/`。不要只修改一份；两份必须保持一致。

### 调用

- **Claude Code**：消息开头使用 `/ml-experiment-preflight ...`，或用带预检触发词的自然语言请求；项目级 Skill 从 `.claude/skills` 发现。
- **Codex**：使用 `$ml-experiment-preflight`（Codex IDE 中可用 `/skills`）；Codex 从当前目录向上到仓库根扫描 `.agents/skills`。
- **AionUi**：没有验证原生 AionUi Skill 发现；成员 Agent 可以手动读取 `SKILL.md` 并运行 CLI，但这不等于原生 AionUi 兼容。

Skill 要求 Agent 先确认显式路径，只运行只读 CLI，解释 JSON，不运行训练、不导入项目代码、不读取数据内容、不写 Git 状态，也不擅自执行整改。详见 [SKILL.md](.claude/skills/ml-experiment-preflight/SKILL.md) 和 [docs/SKILL_INTEGRATION.md](docs/SKILL_INTEGRATION.md)。

## 示例

[`examples/`](examples/) 提供三个完全合成、可复现的临时项目；只使用占位文件和本地 Git 仓库，不使用真实科研数据。`train.py` 永远不会被执行。

| 示例 | 预期结果 | 退出码 |
| --- | --- | --- |
| `normal` | 六规则全 pass；`overall=clear` | `0` |
| `risk` | `ENTRY_CHANGED`、`INPUT_MISSING`、`OUTPUT_EXISTS`；`OUT-002` unknown；`overall=blocked` | `2` |
| `conflict` | `OUTPUT_EQUALS_INPUT_OR_ENTRY` critical；`overall=blocked` | `1` |

运行全部示例并校验预期结果。

Windows PowerShell：

```powershell
cd F:\path\to\ml-experiment-preflight
python .\examples\verify_examples.py
```

Linux Bash：

```bash
cd /path/to/ml-experiment-preflight
python3 examples/verify_examples.py
```

单独运行（每个脚本创建并清理临时项目）：

Windows PowerShell：

```powershell
powershell -NoProfile -File .\examples\normal\run.ps1
powershell -NoProfile -File .\examples\risk\run.ps1
powershell -NoProfile -File .\examples\conflict\run.ps1
```

Linux Bash：

```bash
bash examples/normal/run.sh
bash examples/risk/run.sh
bash examples/conflict/run.sh
```

`risk` 和 `conflict` 脚本故意以 `2` 和 `1` 退出；这是预期结果，不是脚本错误。详见 [examples/README.md](examples/README.md)。

## 隐私与局限

- **只读**：CLI 读取文件系统元数据和有限的本地 Git 元数据；不运行训练或用户代码、不导入项目模块、不读取数据内容、不创建文件、不修改 Git 状态。
- **Git 可执行文件信任**：Git 只从受检查根和当前目录之外的绝对 PATH 目录解析，绝不使用隐式 cwd 查找；调用方控制的 PATH 仍是信任假设（见 SECURITY.md）。
- **仅显式路径**：不遍历整个项目，不猜测缺失路径；不读取输入/输出内容，不枚举输入目录。
- **离线意图**：CLI 不调用上传、遥测或网络 API。明显的 UNC 路径会拒绝或标为 unknown；用户指定的映射盘/网络卷上的元数据读取仍可能触发操作系统网络 I/O。需要严格离线时应避免这类卷。
- **脱敏报告**：JSON 只含规则/证据码和符号引用，不含绝对路径、文件名、环境变量值或 Git 文件名。但原始命令行和 Agent 宿主日志仍可能含路径；私有项目建议本地运行，只分享脱敏 JSON。
- **Git 可选**：Git 缺失或布局不支持时为 `unknown`，不是 `pass`。
- **静态快照**：TOCTOU、并发修改、符号链接、权限、网络路径和跨卷身份仍有限制；UNC 根/入口会拒绝，UNC 输入/输出为 unknown；映射盘尚不能穷尽识别。Windows 只保证终止直接子进程，不保证完整进程树。
- **不是数据或可复现性审计**：无数据质量、标签、schema、GPU/CUDA、依赖求解、性能或完整可复现性证明。
- **Skill 权限**：Skill 不声明 `allowed-tools`；Bash/工具调用仍受宿主权限模型约束。不要把 Skill 文本当作沙箱。

## 兼容性

只标注实际运行过的环境。空白/未运行项不构成支持声明。

| 环境 | 状态 |
| --- | --- |
| Windows 10.0.19045；Python 3.11.0；Git 2.54.0.windows.1 | 最终候选本地实测：127 项 unittest，0 failures，5 skips，exit 0；三个合成示例均验证通过。 |
| Linux / Windows Python 3.12（本地） | 本地未运行。 |
| GitHub Actions（Ubuntu 24.04 和 Windows；Python 3.11/3.12） | 已提供工作流。公开仓库必须在最终公开提交上重新运行四矩阵 CI 后才能发布；预发布结果不构成公开兼容性声明。 |
| Claude Code / Codex 项目级 Skill | 提供两条发现路径，两份 SKILL.md 字节一致。宿主原生发现、版本、权限和行为会变化；未在公开源码树中独立复核。 |
| AionUi | 不宣称原生 Skill 发现；成员 Agent 可手动读取 SKILL.md 并运行 CLI。 |

本地 Windows 测试有 5 项跳过（4 项 POSIX 专项 + 1 项 Windows 符号链接权限）。公开源码树包含使用和验证项目所需的源码、测试、Skill、示例与文档。

## 安装验证

陌生用户可在干净环境按以下步骤验证：

1. 按上面的 PowerShell 或 Bash 命令在全新虚拟环境安装。
2. 运行 `ml-experiment-preflight --help`，确认列出 `check`。
3. 运行正常示例校验器：

   Windows PowerShell（沿用安装步骤中已加入 PATH 的 venv Scripts）：

   ```powershell
   .\.venv\Scripts\python.exe .\examples\verify_examples.py
   ```

   Linux Bash（已激活 venv）：

   ```bash
   python examples/verify_examples.py
   ```

4. 确认输出包含 `normal: overall=clear`、`risk: overall=blocked`、`conflict: overall=blocked`，并确认校验器提示使用的是 installed `ml-experiment-preflight`。
5. 直接运行 normal runner，确认 JSON 的 `overall.status=clear` 且退出码为 `0`。
6. 按卸载步骤确认该环境中不再存在 `ml-experiment-preflight`。

如果 console script 被宿主权限阻止或不存在，使用已安装包的模块回退方式。不要为示例安装未声明的依赖；示例只用 Python 标准库和 Git。

## 许可证

MIT，见 [LICENSE](LICENSE)。项目不包含第三方源码副本。`setuptools>=61` 与 `wheel` 是构建期依赖；Python 和 Git 是外部工具，不是随包分发组件。外部文档链接只是引用，不包含其内容。

## 贡献与安全

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)

不要在 issue、测试、示例或报告中包含 API Key、凭据、私人科研数据、绝对用户路径或专有项目材料。检查器和示例只面向合成样例。
