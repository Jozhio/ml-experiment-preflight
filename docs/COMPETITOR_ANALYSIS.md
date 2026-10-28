# 竞品与替代方案核对

核对日期：2026-10-27。表中“事实”仅指所链官方说明能直接支持的能力；“判断”是本项目定位推断，不代表竞品不存在其他插件或版本功能。

| 工具 | 已验证事实与来源（均于 2026-10-27 核对） | 已解决的问题 | 对本项目的判断 |
| --- | --- | --- | --- |
| MLflow Tracking | 官方称 API/UI 可记录参数、代码版本、指标、输出文件，支持 autologging；默认可写入本地 `mlruns`。[Tracking](https://mlflow.org/docs/latest/ml/tracking/) · [Autologging](https://mlflow.org/docs/latest/ml/tracking/autolog/) | 运行期间及运行后的实验记录、比较与产物管理。 | 不做第二个 tracking 系统；可提示追溯准备不足，但不能声称 MLflow 不支持代码版本。 |
| DVC | 官方文档覆盖数据/模型版本、流水线与实验；实验可记录参数、指标、图表及 Git 基线，`dvc exp run` 可运行流水线。[Experiments](https://doc.dvc.org/user-guide/experiment-management) · [Pipelines](https://doc.dvc.org/user-guide/pipelines) | 有组织的实验版本、依赖与产物管理。 | 不复制数据版本和流水线执行；预检适合尚未采用 DVC 或只需一次启动前检查的项目。 |
| ReproZip | 官方称可打包研究所需文件、库、环境变量及选项；文档将一次运行定义为 `reprozip trace` 追踪的命令，再由 `pack` 建包。[项目主页](https://www.reprozip.org/) · [术语表](https://docs.reprozip.org/en/latest/glossary.html) | 基于实际执行的环境/文件捕获与重现打包。 | 静态预检无法达到其运行观察深度；不宣称完整依赖捕获。 |
| Gitleaks | 官方仓库称其检测 Git、文件或 stdin 中的密码、API Key、Token，支持 pre-commit 和 GitHub Action。[官方仓库](https://github.com/gitleaks/gitleaks) | 专业密钥扫描。 | 不重造密钥检测规则库；首版最多检查明显输出/提交风险元数据，不扫描文件内容找秘密。 |
| preflight-ml | PyPI 项目页称其在 PyTorch 训练前运行 10 项检查，涉及采样 batch、标签泄漏、梯度、形状与显存估算；其示例需提供 dataloader 脚本。[项目页](https://pypi.org/project/preflight-ml/) | PyTorch 的训练前数据/模型动态检查。 | “训练前预检”不是本项目独有；本项目若继续，边界应限定为不导入训练代码、不采样数据的静态检查。 |
| trainproof 0.22.0 | PyPI 项目页描述 `preflight` 数据检查、`env` 启动环境检查、稳定规则 ID/JSON/退出码；核心声称无运行时依赖，环境检查会在子进程导入模块。[项目页](https://pypi.org/project/trainproof/0.22.0/) | 运行前环境/数据检查及运行中、运行后诊断。 | “零 Python 依赖”“结构化 Agent 输出”“运行前”均不具独占性；保留的差别主要是严格静态、离线、只读与不读原始数据的组合，实际使用价值待验证。 |
| preflight-data 0.1.1 | PyPI 项目页称其做数据质量、schema、切分与统计异常检查，提供 JSON/CI gate 和 schema 版本；示例会读取数据表。[项目页](https://pypi.org/project/preflight-data/0.1.1/) | 数据就绪与切分质量预检。 | 不增加数据质量/泄漏规则，避免读取私人数据和重复竞品功能。 |
| agent-powerups 的 `experiment-preflight` | 仓库中的 Claude Code 命令文档要求读训练脚本、检查 seed/追踪/数据版本并输出 Go/No-Go；文件是指令文档。[原始文件](https://github.com/yeaight7/agent-powerups/blob/main/plugins/machine-learning-ops/commands/experiment-preflight.md) | 已有 Agent 侧实验预检流程说明。 | Agent 解释层本身不构成壁垒；本项目必须交付独立可运行的确定性检查器，且不能让 Agent 自行宣称“Go”。 |

## 差异化检验

**已验证事实：** 上述工具分别覆盖追踪、数据/流水线版本、执行后打包和密钥扫描；更直接的 preflight-ml、trainproof、preflight-data 及 Agent 命令已覆盖训练前检查、结构化结果或 Agent 说明的部分组合。因此“训练前检查 + Agent 解释”本身并非独有。来源见表。

**设计判断：** 可继续验证的窄差异是：针对一般 Python ML 项目，不执行训练/导入项目模块、不读取原始数据，只利用显式输入及有限源码/配置元数据检查 Git、路径与输出冲突，并让 Agent 严格解释机器证据。它是安全约束与低摩擦体验的组合，尚无技术独占优势。六组全做深会失去轻量性。

**待验证假设：** 用户愿意在训练前主动运行一次预检；Agent 解释相比普通 CLI 文案能减少理解成本；严格静态/只读的限制仍能发现足够多的高价值问题，且不会因误报造成放弃使用。上述直接竞品的采用量、维护状态及跨平台实测能力尚未核对；需要下一阶段用公开合成样例和少量自愿提供的非敏感反馈验证，不能从竞品功能表直接推出。

## 不进入的竞争区域

不管理实验数据库、指标与模型；不做 DVC 数据/模型版本或远端同步；不追踪系统调用、容器化或重建环境；不做密钥/恶意软件全量扫描；不承诺检测训练脚本中的全部数据泄露或可复现性缺陷。
