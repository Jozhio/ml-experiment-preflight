# CLI 与 JSON 契约（拟定 v1）

状态：v1 契约，已在 v0.1.0 实现；保留设计说明。日期：2026-10-27。

## 命令与输入

拟定调用：

```text
python -m ml_experiment_preflight check --root ROOT --entry ENTRY \
  (--input-file PATH | --input-dir PATH)... \
  (--output-file PATH | --output-dir PATH)... \
  [--format json|text]
```

`--root` 与 `--entry` 各一次；至少一个显式输入、一个显式输出，分别最多 32 个。四类路径选项可重复、可混用，按出现顺序分别编号；不支持通配符、`@file`、自动发现或从环境变量读取路径。`--format` 默认 `text`；Skill 必须显式请求 `json`。相对路径均以 `--root` 为基准。调用方传入路径只是本次本地检查授权，不授权读取内容或递归扫描。`--entry` 代表准备启动的脚本文件，不是执行命令；没有训练参数解析能力。

根目录不存在/非目录、入口的**词法路径**在根外、参数缺失、类型标志冲突、同类目标的词法归一化路径重复、输入或输出数量超限，返回用法错误 2。Windows 的本地同卷 8.3 短路径**父目录**别名是狭义例外：仅当父目录可严格解析并证明入口位于根内时继续检查；无 8.3 父目录特征、UNC 或不同卷绝不尝试此回退。最终入口仍由 `PATH-001` 检查，无法证明时返回用法错误或 unknown，绝不当作 pass。词法重复拒绝只避免同一目标被重复声明，不保证发现不同别名指向同一物理对象。入口词法上在根内、但符号链接目标逃逸，交给 `PATH-001` 报告。入口本身缺失或类型不符也由 `PATH-001` 报告，使报告仍能包含其余证据。输入、输出可在根外；不读取其内容。首版没有 `--write`、`--fix`、`--upload`、`--show-absolute-paths`、`--scan-all` 选项。

## 状态、严重度与总体结论

每个规则恰有一个结果，固定按 [RULE_SPECIFICATION.md](RULE_SPECIFICATION.md) 的六个 ID 排序：`status=pass|finding|unknown`。`pass` 表示该规则在限定观察范围内未发现预定义问题，不表示实验安全；`finding` 表示观测到具体风险条件；`unknown` 表示该规则无法判断。`severity=none|warning|critical`，仅 finding 可为 warning/critical，pass/unknown 必为 none。对于涉及多个目标的规则，若部分目标无法判断但其他目标已有 finding，保留 finding 并设 `coverage_complete=false`、`reason_code` 和 `unknown_refs`；若无 finding 则 status 为 unknown。只有完整覆盖才可 pass。

`overall.status` 的优先级为：存在 critical finding → `blocked`；否则有任何覆盖不完整 → `incomplete`；否则有 warning finding → `review`；否则 `clear`。`blocked` 仍可能同时含覆盖不完整，Agent 必须逐项展示，不能把总体结论当作“全部已检查”。严重度是行动优先级而非失败概率；不提供置信百分数。所有 finding 都是预检建议，CLI 不阻止用户自行运行训练。

退出码：`0` 为 `clear`；`1` 为已知 finding 且全部规则覆盖完整；`2` 为任意覆盖不完整、参数错误或无法构建报告。若同时有 critical finding 和 unknown/部分覆盖，JSON 的 `overall.status=blocked`，退出码仍为 2 以强调检查不完整。解析成功后即使有规则 unknown，也必须输出完整 JSON；参数解析失败不输出 JSON，仅向 stderr 输出固定的 `USAGE_ERROR` 码和脱敏帮助；解析成功但无法构建报告时不输出 JSON，仅向 stderr 输出固定的 `REPORT_ERROR` 码。文本输出同样遵守脱敏。自动化调用须先判断 stdout 是否为有效 JSON，再依据 `overall` 和全部非 pass 结果处理；不得只凭退出码下结论。

## JSON Schema v1（设计契约）

JSON stdout 为 UTF-8 单个对象；不混入进度条或日志。`schema_version` 只在兼容变更时保留主版本，破坏性变更升主版本。下方 Schema 限定公开字段，具体证据码见规则规范；`additionalProperties: false` 防止意外泄露。所有字符串字段均禁止填入原始路径、文件名、命令行、环境值和 Git 原始输出。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ML Experiment Preflight report v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "tool_version", "scope", "overall", "results"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "tool_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "scope": {
      "type": "object", "additionalProperties": false,
      "required": ["root_ref", "entry_ref", "input_count", "output_count", "git_status_scope", "untracked_files_scanned"],
      "properties": {
        "root_ref": {"const": "root"},
        "entry_ref": {"const": "entry"},
        "input_count": {"type": "integer", "minimum": 1, "maximum": 32},
        "output_count": {"type": "integer", "minimum": 1, "maximum": 32},
        "git_status_scope": {"const": "entry_only"},
        "untracked_files_scanned": {"const": false}
      }
    },
    "overall": {
      "type": "object", "additionalProperties": false,
      "required": ["status", "finding_count", "unknown_count"],
      "properties": {
        "status": {"enum": ["clear", "review", "blocked", "incomplete"]},
        "finding_count": {"type": "integer", "minimum": 0},
        "unknown_count": {"type": "integer", "minimum": 0}
      }
    },
    "results": {
      "type": "array", "minItems": 6, "maxItems": 6,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["rule_id", "status", "severity", "coverage_complete", "reason_code", "unknown_refs", "evidence"],
        "properties": {
          "rule_id": {"enum": ["GIT-001", "GIT-002", "GIT-003", "PATH-001", "OUT-001", "OUT-002"]},
          "status": {"enum": ["pass", "finding", "unknown"]},
          "severity": {"enum": ["none", "warning", "critical"]},
          "coverage_complete": {"type": "boolean"},
          "reason_code": {"type": ["string", "null"], "pattern": "^[A-Z][A-Z0-9_]*$"},
          "unknown_refs": {"type": "array", "maxItems": 64, "items": {"type": "string", "pattern": "^(root|entry|input:[1-9][0-9]*|output:[1-9][0-9]*)$"}},
          "evidence": {
            "type": "array", "maxItems": 64,
            "items": {
              "type": "object", "additionalProperties": false,
              "required": ["code", "refs"],
              "properties": {
                "code": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]*$"},
                "refs": {"type": "array", "maxItems": 2, "items": {"type": "string", "pattern": "^(root|entry|input:[1-9][0-9]*|output:[1-9][0-9]*)$"}}
              }
            }
          }
        }
      }
    }
  }
}
```

Schema 外的逻辑约束也属于契约：六个 ID 各出现一次且固定顺序；`pass/unknown` 的 severity 为 none，finding 的 severity 非 none；pass 必须 `coverage_complete=true` 且无 reason_code/unknown_refs；覆盖不完整必须有 reason_code 与 unknown_refs（Git 这类无具体路径目标的规则可用 `root`）；unknown 的 evidence 为空；finding 可同时覆盖不完整；finding_count 是 finding 结果数，unknown_count 是覆盖不完整结果数，两者可重叠；`overall.status` 按上述优先级计算。已用 Python 标准库测试这些约束；运行时不必引入 JSON Schema 验证库。

## 脱敏与异常

路径引用的编号只对应调用参数位置，JSON 不包含映射表或 basename。Git SHA 不进入默认报告；Git 文件名和原始 stderr 不透传。错误以固定枚举码表达（如 `PERMISSION_DENIED`、`GIT_TIMEOUT`、`SYMLINK_UNRESOLVED`、`OUTPUT_PARENT_UNKNOWN`）；仅文本模式可显示不含路径的通用解释。异常栈、环境变量值、凭据和绝对路径不得输出。输出过大/超时视为 unknown，不能截断成 pass。Agent 解释需引用 `rule_id`、`code`、`refs` 并保留 unknown。

脱敏只约束 CLI **报告**，不约束用户原始命令、shell 历史或 Agent 宿主工具日志。含敏感路径的项目应优先在本地运行 CLI，再按已批准的数据处理边界提交脱敏 JSON；不得以本契约声称云端 Agent 调用全过程没有路径暴露。
