# 首版规则规范（拟定）

状态：规则规范，已在 v0.1.0 实现；保留设计说明。日期：2026-10-27。六条规则仅覆盖三组核心检查；`pass` 只代表规则的限定观察范围内未发现对应条件。所有规则不得读取原始训练数据内容、导入项目代码或递归枚举输入目录。

## 共通判定

每条规则结果可包含多项枚举证据，引用 `root`、`entry`、`input:N`、`output:N`。已知 finding 与其他目标的未知可以同时发生：结果保留 `status=finding`，同时标记 `coverage_complete=false`、给出 `reason_code` 与未知引用；总体检查因覆盖不完整返回退出码 2。若没有已知 finding 但覆盖不完整，`status=unknown`。只有全部相关目标可判断且无 finding 才可 `pass`。证据总量有上限，超过上限须设 `coverage_complete=false`，不得静默截断为通过。具体字段见 [CLI_CONTRACT.md](CLI_CONTRACT.md)。

## Git

| ID | 检查与判定 | finding 严重度/证据码 | pass 证据码 | unknown 原因码 |
| --- | --- | --- | --- | --- |
| `GIT-001` | 根目录是否为可安全检查且有 HEAD 的 Git 仓库；先检查根内 `.git`，不搜索父目录；仅支持根等于仓库顶层、普通本地 `.git` 目录。 | warning：`NO_REPOSITORY` 或 `NO_HEAD`。并非禁止不使用 Git。 | `REPOSITORY_WITH_HEAD` | `GIT_UNAVAILABLE`、`GIT_ROOT_MISMATCH`、`UNSUPPORTED_GIT_LAYOUT`、`GIT_TIMEOUT`、`GIT_ERROR` |
| `GIT-002` | 仅检查已跟踪的显式入口文件的暂存/工作树变化，忽略其他文件、未跟踪目录及子模块内容；入口带 assume-unchanged/skip-worktree 索引标志时不宣称未变化。 | warning：`ENTRY_CHANGED`。不报告文件名或 diff。 | `ENTRY_UNCHANGED` | `ENTRY_UNAVAILABLE`、`ENTRY_NOT_TRACKED`、`GIT_ENTRY_FLAG_UNSUPPORTED`、`GIT_CONTEXT_UNKNOWN`、`GIT_TIMEOUT`、`GIT_ERROR`、`GIT_OUTPUT_LIMIT` |
| `GIT-003` | 指定入口文件是否在 Git 索引中；对字面路径做精确匹配。 | warning：`ENTRY_NOT_TRACKED`。仅表明当前索引未跟踪该入口。 | `ENTRY_TRACKED` | `ENTRY_UNAVAILABLE`、`GIT_CONTEXT_UNKNOWN`、`GIT_TIMEOUT`、`GIT_ERROR` |

当 `GIT-001` 为 `NO_REPOSITORY`/`NO_HEAD` finding 时，`GIT-002/003` 为 `unknown(GIT_CONTEXT_UNKNOWN)`；当入口未跟踪时，`GIT-003` 为 finding、`GIT-002` 为 `unknown(ENTRY_NOT_TRACKED)`；当 `PATH-001` 确认入口逃逸根或无法解析时，均不对入口调用 Git，`GIT-002/003` 为 unknown。其他源/配置文件、未跟踪文件与被忽略文件绝不被 `GIT-002` 的 pass 覆盖。`git status` 的默认索引刷新副作用及 `--no-optional-locks` 依据见 [技术设计](TECHNICAL_DESIGN.md)。

## 显式输入路径

| ID | 检查与判定 | finding 严重度/证据码 | pass 证据码 | unknown 原因码 |
| --- | --- | --- | --- | --- |
| `PATH-001` | 对入口和所有显式输入做目标存在性与 file/dir 类型检查；入口物理目标必须留在根内。只取自身及必要父链元数据，不列目录内容。 | critical：`ENTRY_MISSING`、`INPUT_MISSING`、`TYPE_MISMATCH`、`ENTRY_ESCAPES_ROOT`。 | evidence 可为空 | `PERMISSION_DENIED`、`SYMLINK_UNRESOLVED`、`PATH_IO_ERROR`、`EVIDENCE_LIMIT` |

根外**显式数据输入**本身不产生 finding。入口词法路径越出根是 CLI 参数错误；Windows 本地同卷 8.3 父目录别名仅在严格解析父目录后可确认入口在根内时例外，UNC/异卷不走此回退，无法确认时不得返回 pass。词法上在根内、经符号链接实际逃逸则是 `ENTRY_ESCAPES_ROOT`，不会再打开目标内容。缺失输入可能是稍后挂载，报告只说明“检查时不存在”，不声称训练必然失败。`PATH-001` 的阳性/阴性/unknown 例见 [测试计划](TEST_PLAN.md)。

## 显式输出路径

| ID | 检查与判定 | finding 严重度/证据码 | pass 证据码 | unknown 原因码 |
| --- | --- | --- | --- | --- |
| `OUT-001` | 对每个输出检查目标已存在、目标类型与声明的 file/dir 是否一致、尚不存在时父链能否确认。 | warning：`OUTPUT_EXISTS`；critical：`OUTPUT_TYPE_MISMATCH`。 | evidence 可为空 | `OUTPUT_PARENT_UNKNOWN`、`SYMLINK_UNRESOLVED`、`PERMISSION_DENIED`、`PATH_IO_ERROR` |
| `OUT-002` | 解析后的输出与入口、根、所有显式输入作同一目标及组件级祖先/后代比较。 | critical：`OUTPUT_EQUALS_INPUT_OR_ENTRY`、`OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT`；warning：`OUTPUT_INSIDE_INPUT_DIR`。 | evidence 可为空 | `PATH_COMPARISON_UNKNOWN`、`SYMLINK_UNRESOLVED`、`OUTPUT_PARENT_UNKNOWN`、`EVIDENCE_LIMIT` |

`OUT-001` 已存在只是警告：用户可能续训或复用目录。`OUT-002` 发现多个关系时按 critical 优先设置规则 severity，但保留所有受上限约束的证据码。输出在项目根内通常是正常的，`OUTPUT_INSIDE_ROOT` **不单独构成 finding**；只有与入口、输入或根本身形成危险关系才提示。这一限制避免把 `runs/` 等正常路径误报。输出文件位于输入目录内是警告，因为具体训练程序是否将其纳入数据读取不可由静态检查证明。输出目录包含根是 critical，避免指向项目整体作为产物目录。

## 每项规则的最小可验收三态用例

| 规则 | 阳性 finding | 阴性 pass | unknown |
| --- | --- | --- | --- |
| GIT-001 | 根非仓库或仓库无 HEAD | 普通仓库且有 HEAD | Git 不在 PATH 或根对应外部 gitdir |
| GIT-002 | 修改已跟踪入口 | 已跟踪入口无变化 | 入口未跟踪或 `status` 超时/不可运行 |
| GIT-003 | 入口存在但未加入索引 | 入口被索引跟踪 | 入口缺失或 Git 上下文不可用 |
| PATH-001 | 显式输入缺失/类型错误或入口链接逃逸 | 入口与输入存在且类型正确 | 循环链接/权限拒绝导致目标无法判定 |
| OUT-001 | 输出目标已存在或类型不符 | 输出不存在且父目录已存在 | 父链不可解析或权限拒绝 |
| OUT-002 | 输出等于输入、输出目录包含输入或落入输入目录 | 输出与根/输入/入口均无危险重叠 | 任一必需比较目标不可解析 |

这些用例仅是设计验收条件，不是已运行测试。组合、平台与隐私测试见 [TEST_PLAN.md](TEST_PLAN.md)。
