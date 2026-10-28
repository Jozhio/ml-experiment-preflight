# 技术设计

状态：设计基线；v0.1.0 已实现本文的 CLI、六规则与报告契约，个别“候选命令”以当前源码为准。日期：2026-10-27。适用边界继承 [MVP_SCOPE.md](MVP_SCOPE.md)。

## 目标与工作流

一个独立 CLI 接受明确指定的项目根、训练入口、输入与输出目标，只读取文件系统元数据和有限 Git 元数据，生成稳定的 JSON 或文本报告。Agent Skill 调用同一个 CLI，并严格依据 JSON 的规则 ID、证据码和未知原因解释风险。运行训练、导入用户 Python 模块、遍历数据集、读取数据内容、创建任何被检查项目文件均不在流程内。

三组检查联用的价值来自同一组显式路径：例如入口未受版本控制、输入仍存在但输出指向输入目录时，报告能同时指出“这次运行的代码基线不明”和“结果可能污染数据目录”。这是并列证据与优先处置顺序，不推断训练代码真的会覆盖文件，更不输出一个无法证明的复现性分数。参见 [规则规范](RULE_SPECIFICATION.md)。

## 组件边界

1. **CLI 参数层**：解析显式参数、数量上限、格式选择；不遍历目录。参数语法错误返回用法错误。
2. **路径归一化层**：以 `--root` 为相对路径基准，给所有输入稳定编号；对现存路径使用 `resolve(strict=True)`，对尚不存在的输出仅在现存父链可解析时使用非严格解析；保留原始路径只在进程内比较，不写入报告。
3. **元数据检查层**：使用 `lstat`/`stat`/路径比较判断类型、存在性及冲突；不得 `open()` 指向训练数据的文件。输入目录仅检查目录自身，不 `iterdir()`/`glob()`。
4. **Git 适配层**：若根目录不是可安全检查的仓库，返回 `unknown` 或仓库缺失 finding；只调用固定 argv、无 shell 的本地 Git 命令。Git 的 stdout/stderr 仅在内存中解析，原样内容不写入报告。
5. **报告层**：输出全部六条固定规则的结果，包括 `unknown`；证据仅用受限枚举、数字和不含真实路径的引用符号。JSON stdout 仅一个对象，stderr 仅脱敏诊断。

首版不需要网络、数据库、插件系统、规则配置语言、YAML 解析器或第三方 Python 运行时依赖。Python 下限暂定 3.11；Git 可缺席，Git 规则此时为 `unknown`，其余规则仍可运行。

## 路径与安全边界

- `--root` 必须是已存在目录。其规范化后的物理路径是本次比较基准；入口必须物理位于根内。相对 `--entry`、`--input-file/dir`、`--output-file/dir` 均相对根解释，绝不相对当前 shell 工作目录。
- 显式输入数据可位于根外，因为科研数据常在独立卷；只检查该目标及必要父链的元数据，不读取内容。输出也可在根外，但会与所有显式输入、入口和根进行重叠比较。
- Windows 比较使用平台路径语义，先标准化盘符/UNC，再按路径组件比较；跨卷对象不能凭字符串前缀判祖先关系。Linux 以实际解析路径和组件比较。不要用 `startswith()` 判断包含关系。大小写仅按当前平台实际语义处理，不声称识别网络共享上的特殊大小写策略。
- 存在的符号链接解析目标后比较。循环、断链、权限拒绝及无法确认的网络路径产生 `unknown`，不得退回纯字符串比较并宣称安全。对未存在输出，只解析已存在父链；若父链不存在、不可读或可能在运行前变化，输出位置判定为 `unknown`。路径状态是检查时点快照，存在 TOCTOU 限制。
- 输出目录等于或包含输入、入口或项目根时为严重冲突；输出位于输入目录内是污染风险警告；输出文件与输入/入口相同为严重冲突。已存在的输出单独警告，允许用户明确选择覆盖/续训，CLI 不自动写入或清理。
- 路径引用仅形如 `root`、`entry`、`input:1`、`output:1`；报告不含绝对路径、文件名、用户名、环境变量值、Git 文件名、命令行原文或源码片段。Agent 的默认解释也不要求打印路径。用户可在本地用原始命令定位编号对应的参数。
- **宿主边界：** CLI 可离线且报告脱敏，但由云端 Agent 发起调用时，用户提示、工具命令或宿主日志仍可能包含原始参数路径；不能把“报告脱敏”宣称为“Agent 从未看到路径”。私有项目默认推荐用户在受控终端本地运行 CLI，再只把脱敏 JSON 提交给已获准的 Agent；直接由 Codex/Claude Code/AionUi 调用须服从用户对该宿主的数据处理授权。工具调用记录的暴露范围仍需各宿主分别评估。

## Git 只读设计

调用 Git 前先对 `<root>/.git` 做 `lstat`：缺失时报告无仓库且**不向父目录搜索**；普通目录才进入后续检查；符号链接、gitdir 文件或无法读取时返回 `unknown(UNSUPPORTED_GIT_LAYOUT)`。候选命令为 `git --no-optional-locks --no-lazy-fetch --literal-pathspecs -C <root> -c core.fsmonitor=false -c core.ignoreStat=false ...`，固定调用 `rev-parse`、仅针对显式入口的 `status --porcelain=v1 -z --untracked-files=no --ignore-submodules=all --no-renames -- <entry>`，以及 `ls-files --cached -z -- <entry>`（确认跟踪）和 `ls-files -v -z -- <entry>`（读取索引标志）。解析 `ls-files -v` 的入口索引标志；若有 assume-unchanged 或 skip-worktree，`GIT-002` 返回 unknown，不得把空的 `status` 当作入口未变化。限制 status 的 pathspec，避免它为了判断其他已跟踪文件是否变化而读取原始数据内容；入口源码可能被 Git 读取用于变化判断。执行前清除继承的 `GIT_DIR`、`GIT_WORK_TREE`、`GIT_INDEX_FILE` 等会重定向仓库的环境变量，并隔离系统/全局 Git 配置，关闭终端提示、设置超时/输出上限。若安装的 Git 不支持这些安全选项，返回 unknown，不降级为可能写入或联网的调用。具体 argv、索引标志解析与环境隔离方案已在 v0.1.0 合成仓库测试中锁定。Git 可执行文件只从绝对 PATH 目录选择，并排除 `--root` 与当前工作目录内的候选；调用方控制的 PATH 仍是信任假设。[Git update-index](https://git-scm.com/docs/git-update-index) 与 [git-ls-files](https://git-scm.com/docs/git-ls-files) 说明了这些标志的语义（2026-10-27 核对）。

`status` 仅看显式入口，**不扫描未跟踪目录或其他已跟踪文件**；因此“干净”只表示入口没有检测到工作树/暂存变化，不能表示项目完全无未提交文件。仓库根不等于 `--root`、worktree/submodule 或外部 gitdir 的布局暂返回 `unknown`，避免跨根读取。不可解析的 HEAD、Git 未安装、超时、权限错误均不能当作 clean。

Git 官方说明 `status` 默认可能写索引缓存，`--no-optional-locks` 可避免此类可选锁/写入；关闭 FSMonitor 是为了避免用户配置触发外部程序。它们不是对所有平台和 Git 配置的形式证明，必须用文件树与 `.git/index` 快照、无网络/无外部命令监测验证。[Git 主命令](https://git-scm.com/docs/git) · [git-status](https://git-scm.com/docs/git-status) · [git-ls-files](https://git-scm.com/docs/git-ls-files)（2026-10-27 核对）。

## 异常与资源限制

参数错误（根不存在、缺少输入或输出、数量超限）是 CLI 用法错误；一次检查中发生的权限拒绝、损坏链接、Git 超时或解析失败只使受影响规则 `unknown`，其余规则继续。不得回显含原始路径的异常消息。每次最多 32 个显式输入和 32 个输出；每个 Git 调用超时 5 秒、捕获输出上限 1 MiB，超限即 `unknown`。数值为初始设计值，待合成压力样例校准。报告不写磁盘、不做自动修复；调用者自行决定是否保存标准输出。

## 依据与限制

Python `pathlib` 的 `resolve()` 会解析链接并消去 `..`，但非严格模式对不存在尾部只作部分解析，不能证明未来目标不会改变。[Python pathlib](https://docs.python.org/3.11/library/pathlib.html)（2026-10-27 核对）。Skill 的 `SKILL.md` 只定义调用与解释流程，不提供沙箱保证；跨宿主行为见 [测试计划](TEST_PLAN.md)。v0.1.0 已在 Windows 合成目录验证核心流程；真实 ACL、网络卷、完整进程树和跨宿主差异仍未完全验证。
