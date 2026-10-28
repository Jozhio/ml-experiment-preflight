# ML Experiment Preflight — 产品简述

核对日期：2026-10-27。本文为产品判断；v0.1.0 已实现核心 CLI/规则，但产品价值假设仍待用户验证。

## 结论

**设计判断：v0.1.0 已实现核心静态检查器；直接竞品已存在，产品净价值仍须验证。** 目标用户是准备在本机或受控计算环境启动训练、希望先发现明显配置与可追溯性风险的研究者。首版应提供离线、只读、可审计的命令行检查器；Agent Skill 负责明确调用、读取结构化结果、解释证据和不确定性。成功标准是在不运行训练的前提下发现少数高价值、可复核的问题。

**最清晰的候选差异化：** 在不导入项目模块、不读取原始数据、不写入项目的约束下，用低成本静态证据检查启动契约、Git 与显式路径/输出冲突；检查器独立于 Agent 可运行，Agent 只解释带规则 ID、证据位置及未知边界的结果。该组合价值待验证，不能宣称“训练前 + Agent”独有。

## 需求与定位

- **待验证假设：** 小型研究团队存在“启动训练后才发现代码未提交、路径写错、输出会覆盖、种子配置不完整、运行参数未留痕”的重复成本。尚无访谈或真实项目测量支持其频率与付费/采用意愿。
- **已验证事实：** MLflow/DVC/ReproZip/Gitleaks 分别覆盖追踪、版本、执行捕获和密钥扫描；preflight-ml、trainproof、preflight-data 已提供不同类型的训练前检查，其中 trainproof 还提供稳定规则 ID 与 JSON；已有 Claude Code 实验预检命令。[MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/) · [DVC Experiments](https://doc.dvc.org/user-guide/experiment-management) · [ReproZip](https://www.reprozip.org/) · [Gitleaks](https://github.com/gitleaks/gitleaks) · [preflight-ml](https://pypi.org/project/preflight-ml/) · [trainproof](https://pypi.org/project/trainproof/0.22.0/) · [preflight-data](https://pypi.org/project/preflight-data/0.1.1/) · [Agent 命令](https://github.com/yeaight7/agent-powerups/blob/main/plugins/machine-learning-ops/commands/experiment-preflight.md)（均于 2026-10-27 核对）。详见 [竞品分析](COMPETITOR_ANALYSIS.md)。
- **设计判断：** 本项目仅能尝试在“严格静态、隐私保护、低误报、跨宿主 Skill”这一窄组合上形成体验差别；尚未证实市场空白。

## 产品边界

输入限于用户明确指定的项目根目录、训练入口及少量配置路径。扫描只在该根目录内的候选源码/配置文件进行，且有大小、数量、时间预算；外部数据路径仅做路径属性检查，不读取内容。默认不访问网络、不执行训练/项目代码、不写入被检查项目、不保存源文件或环境变量值。输出在标准输出；如需落盘，由调用者重定向到其批准的位置。

检查结果分为 `pass`、`finding`、`unknown`；`finding` 带 `warning`/`critical` 严重度，`unknown` 表示证据不足、不能算通过。严重度是行动优先级，不是置信度或失败概率。每条结果应含规则 ID、简短原因、脱敏证据位置、可操作建议。Agent 只解释机器结果，并说明静态分析不能证明随机性、完整依赖或运行结果。

## Agent Skills 可行性

**已验证事实：** 开放的 Agent Skills 规范要求 skill 目录内有 `SKILL.md`，YAML frontmatter 中 `name` 与 `description` 为必填；可附带 `scripts/` 等资源。Codex 可依据描述自动选用或经 `$` 显式调用，Claude Code 可自动选用或通过 `/skill-name` 调用；两者均支持项目级 skill，但项目目录惯例不同。[Agent Skills 规范](https://agentskills.io/specification) · [Codex Build skills](https://learn.chatgpt.com/docs/build-skills) · [Claude Code Skills](https://code.claude.com/docs/en/skills)（2026-10-27 核对）。

**设计判断：** v0.1.0 采用标准 `SKILL.md` 和相对路径脚本构成可移植源包；Codex 与 Claude Code 的发现、显式调用及权限行为仍随宿主版本/配置变化，AionUi 原生发现未验证。Skill 本身不提供沙箱或只读保证；安全边界由检查器和宿主权限共同实现。

## 产品验证门槛

用公开、合成的 Windows/Linux 小样例验证：明确风险能稳定检出；正常样例误报可解释；完全离线、只读；无 Git 或缺少可选配置时有清楚的 `unknown`；同一结构化结果能被两个 Agent 正确转述。若这些门槛失败，缩减规则或停止该方向。
