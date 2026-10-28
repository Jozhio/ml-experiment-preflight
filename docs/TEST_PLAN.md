# 候选验收测试计划

状态：设计基线；v0.1.0 已实现并执行自动化单元/合成 E2E 测试。本文保留原始验收计划；未覆盖的真实 ACL、网络卷、进程树等边界以 README/SECURITY 的限制为准。日期：2026-10-27。所有场景只使用在临时目录生成的合成源码、占位数据文件和本地 Git 仓库；不得复制真实科研项目、数据或凭据。

## 测试原则与判定

运行前记录临时项目文件树、内容哈希、权限、mtime、`.git/index` 哈希与文件列表；运行后对比，允许仅测试框架自身在项目外写日志。检查器不得创建/修改/删除项目文件。网络访问应被阻断并监测。以读取审计或特制“不可读但可 stat”的合成数据文件证明 CLI 不打开输入文件内容、不列输入目录；若平台监测不可靠，标测试证据不足，不声称通过。stdout/stderr 搜索绝对临时路径、用户目录、文件名、合成 secret 字符串。每个测试同时验证 JSON 结构、规则顺序、计数、退出码和文本/JSON 语义一致。

至少在 Windows 与 Linux 各运行同一套场景；路径包含空格、中文、前缀相似目录（`data`/`database`）。Windows 额外覆盖盘符不同、UNC（可用受控共享时）、大小写与 junction；Linux 覆盖符号链接循环和权限拒绝。权限测试需在能真正触发拒绝的非管理员账号执行，否则标为未测。硬链接、网络文件系统和并发 TOCTOU 不作确定性保证。

## 三个完整合成端到端场景

### E2E-01：正常启动契约

在临时 `project/` 创建入口 `train.py`、占位 `data/input.bin`、空的 `runs/` 父目录。仅将入口加入本地 Git 并提交；绝不运行 `train.py`。指定 `--input-file data/input.bin --output-file runs/model.bin`。期望六规则全部 `pass`，`overall.status=clear`，退出 0；不产生项目写入，不输出原始路径。该场景验证“无风险”必须受限于显式入口与路径，不得在解释中称数据内容/可复现性已经检查。

### E2E-02：组合风险与处置优先级

复制合成项目，修改已跟踪的 `train.py` 但不提交；输入设为现存目录 `data/`，输出目录也设为 `data/`。期望 `GIT-002=finding(warning, ENTRY_CHANGED)`、`PATH-001=pass`、`OUT-001=finding(warning, OUTPUT_EXISTS)`、`OUT-002=finding(critical, OUTPUT_EQUALS_INPUT_OR_ENTRY)`；`GIT-001/003=pass`。总体 `blocked`、退出 1。Agent 解释先指出输出与输入目录冲突，再提醒入口未提交；不得说“训练一定会覆盖数据”。

### E2E-03：无法安全判断

先准备有 `.git` 且有 HEAD 的合成仓库，再用绝对 Python 解释器启动 CLI，并在隔离环境中使 Git 可执行文件不可用；入口为本地普通合成脚本，`--input-file` 指向合成循环链接，输出父目录不存在。期望三项 Git 规则 `unknown`，`PATH-001=unknown(SYMLINK_UNRESOLVED)`，`OUT-001/002=unknown(OUTPUT_PARENT_UNKNOWN 或 PATH_COMPARISON_UNKNOWN)`；总体 `incomplete`、退出 2。不得将任何未知呈现为通过；不得创建输出父目录。Windows 若无法以普通权限建链接，使用受控 junction/断链等价场景并记录偏差。

## 每条规则的阳性、阴性与 unknown

| 规则 | 阳性：必须产生 finding | 阴性：必须 pass | unknown：必须保留不确定性 |
| --- | --- | --- | --- |
| `GIT-001` | 合成根没有 `.git`，报 `NO_REPOSITORY` | 根为有一次提交的普通仓库 | 控制 PATH 使 Git 缺失；或仓库根与 `--root` 不一致 |
| `GIT-002` | 修改已跟踪入口后报 `ENTRY_CHANGED` | 已跟踪入口未修改；其他未跟踪数据文件存在也不能改变此 pass 的范围 | 入口未跟踪、Git status 超时、入口无法取元数据，或入口带 assume-unchanged/skip-worktree 标志 |
| `GIT-003` | 入口存在但未 `git add`，报 `ENTRY_NOT_TRACKED` | 入口在索引中 | Git context 不可用或入口缺失 |
| `PATH-001` | 输入缺失、file/dir 类型错、入口链接逃逸，分别报对应码 | 所有显式入口/输入类型正确且可解析 | 循环链接、断链或受控权限拒绝；混合有缺失与未知时 finding 且 coverage 不完整 |
| `OUT-001` | 已存在输出报 warning；现存但类型错报 critical | 输出未存在且父链可解析 | 输出父链缺失/权限拒绝；混合存在与未知时 finding 且 coverage 不完整 |
| `OUT-002` | 输出等于输入或输出目录包含输入报 critical；输出位于输入目录内报 warning | 不同目标、无危险祖先关系，包括普通 `runs/` 位于根内 | 比较对象循环链接或输出父链无法确认；混合已知冲突与未知时 finding 且 coverage 不完整 |

每项规则的状态、严重度和码以 [RULE_SPECIFICATION.md](RULE_SPECIFICATION.md) 为准。还需对无 Git 仓库、入口未跟踪时的 finding 与 unknown 并存，32 个输入/输出上限、33 个参数拒绝、词法重复输出参数拒绝、证据数超限、路径带换行与非 ASCII、`--format json` 仅输出一份 JSON、`USAGE_ERROR`/`REPORT_ERROR` 与有效 JSON unknown 的区分、参数错误不泄漏路径、已有输出但允许续训的误报文案作边界测试。特意构造同前缀不同目录，防止用字符串 `startswith` 产生假重叠。

## Git 只读与副作用验收

使用普通仓库、无 HEAD 仓库、仓库子目录、linked worktree、submodule、带 FSMonitor 配置、`core.ignoreStat=true`、入口带 assume-unchanged/skip-worktree 标志、损坏索引、超时包装器和 Git 缺失的合成 fixture。对两个索引标志分别修改入口，要求 `GIT-002=unknown(GIT_ENTRY_FLAG_UNSUPPORTED)`，不可误报 `ENTRY_UNCHANGED`。用 `.git/index` 与工作树快照确认 `--no-optional-locks` 配合 scoped status 未写入；监测是否触发外部 FSMonitor/网络；任何一次写入或扫描非显式数据内容即不通过。官方文档明确 `git status` 默认可能刷新索引且 `--no-optional-locks` 用于避免可选锁/写入，因此只读不是单靠命令名推断。[git-status](https://git-scm.com/docs/git-status) · [git](https://git-scm.com/docs/git)（2026-10-27 核对）。

## Agent Skills 跨宿主兼容验收

只在临时、合成项目和隔离的测试配置/助手中安装同一份规范 `SKILL.md` 与 CLI；不修改用户日常使用的全局 Codex/Claude Code/AionUi 配置。若 AionUi 无法提供隔离配置，兼容测试停在准备阶段并另行征求用户对临时配置变更的批准。先按 [Agent Skills 规范](https://agentskills.io/specification) 验证 frontmatter 的 `name`/`description`、目录名、相对脚本引用，再分别测试：

| 宿主 | 安装/发现路径与操作 | 必须验证的行为 |
| --- | --- | --- |
| Codex | 临时 repo 的 `.agents/skills/ml-experiment-preflight/`；用显式 `$` 调用，再测试描述匹配的自动选用。[Codex 说明](https://learn.chatgpt.com/docs/build-skills) | 调用本地 CLI `--format json`；只复述真实规则与 unknown；无额外项目扫描、写入或上传。 |
| Claude Code | 临时 repo 的 `.claude/skills/ml-experiment-preflight/`；用 `/ml-experiment-preflight` 显式调用，再测试自动选用。[Claude Code 说明](https://code.claude.com/docs/en/skills) | 同一 JSON 得出等价结论；不把 Skill 说明当成执行权限；不读取数据内容。 |
| AionUi | 在隔离测试助手中导入同一 skill 目录、附加到助手，再分别选择可用的 Codex 与 Claude Code 后端。[AionUi 官方指南](https://github.com/iOfficeAI/AionUi/wiki/Assistant-Configuration-Guide) | 确认实际发现、工具调用权限、stdout 解析、脱敏与失败呈现；记录后端差异，不假定 AionUi 的展示等于宿主已执行。 |

每个宿主至少跑 E2E-01/02/03 的 JSON 固定输出（可用合成 fixture）和一次真实本地 CLI 调用。验证 Agent 是否正确区分 `blocked`、`incomplete`、退出码 2、部分覆盖 finding；注入一个只含伪造自然语言指令的模拟诊断字符串，确认受限 JSON schema 不让 Agent 将其当作可信指令。若某宿主不能执行 CLI 或无法保证默认只读，标兼容性不通过，不用提示词掩盖。

## 验收门槛

规则阳性/阴性/unknown 与三场景在 Windows/Linux 均通过；无项目写入、无原始数据内容读取、无网络；JSON/schema/退出码一致；三个宿主各能明确调用并正确保留未知。实际误报需在合成负例中逐条复盘，再以自愿非敏感反馈评估使用价值。v0.1.0 已执行自动化单元/合成 E2E 测试，但本文列出的真实 ACL、网络卷、完整进程树和全部宿主原生发现等验收项未全部执行，不能据此宣布完整跨平台或宿主兼容已通过。
