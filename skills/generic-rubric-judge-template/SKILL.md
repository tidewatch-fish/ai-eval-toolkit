---
name: generic-rubric-judge-template
description: 使用固定维度 Rubric 评测开放式模型回答，并生成可追溯的结构化判断与批量汇总。适用于 RAG、客服、文档助手、Agent 等场景的准确性、完整性、帮助性单维度评测，也适用于 Gold Set 人工标签对齐、回归测试和 Rubric 迭代；当用户要求评测回答、搭建 LLM-as-a-Judge、分析误判或复用本模板时使用。
---

# 通用 Rubric 评测器模板

使用固定维度规则评测回答。不要为每道题临时生成 criterion。

## 先确认方法是否适用

- 需要跨题目复用统一质量标准、统计各类问题时，使用本 Skill。
- 需要核对某道题独有的答案点时，改用逐题 criterion。
- 需要评测金融问答时，优先使用 `finance-rubric-judge`。

## 执行评测

### 1. 读取规则和数据契约

先读取：

- `references/data-schema.md`：输入、判断结果和批量文件格式；
- `references/rubric.json`：维度触发条件、判断规则和边界。

### 2. 准备任务

将用户提供的内容整理为 `assets/eval-case-template.json` 的结构。把领域事实写入 `reference_context`，不要写入 Rubric。

只评测一个维度时，指定 `dimension_id`：

```bash
python scripts/prepare_eval.py --input assets/sample-case.json
```

完整评测同一回答时，生成三个相互隔离的任务：

```bash
python scripts/prepare_eval.py --input assets/sample-case.json --all-dimensions
```

批量输入可使用 JSON 数组或 JSONL。每条记录仍然只对应一个维度；使用 `--all-dimensions` 时，脚本为每条记录展开三个独立任务。

### 3. 独立判断每个任务

严格按以下顺序执行：

1. 检查当前维度的全部 `trigger_conditions`；任一不满足，返回“不适用”。
2. 只读取当前维度的 `judgment_rule`、`pass_conditions`、`fail_conditions` 和 `boundary_rules`。
3. 仅使用输入中的参考材料、标准答案、对话上下文和任务要求判断，不补充外部事实。
4. 引用待评回答中的直接证据，输出一个结构化判断。

始终隔离维度：

- 信息遗漏属于完整性；
- 已表达内容的事实错误属于准确性；
- 已提供内容是否清晰、可理解、可执行属于帮助性；
- 同一问题不要在多个维度用相同理由重复判错。

输出：

```json
{
  "case_id": "case-001",
  "dimension_id": "accuracy",
  "result": "对",
  "evidence": ["回答原文或精确位置"],
  "reason": "对：回答中的核心事实均与参考材料一致。"
}
```

结果语义：

- `对`：满足当前维度；
- `错`：违反当前维度；
- `不适用`：当前维度不适用或证据不足。“不适用”不是“对”，统计通过率时必须排除。

### 4. 校验并汇总

校验单条判断：

```bash
python scripts/score_result.py --input assets/sample-judgment.json
```

批量输入可使用 JSON 数组或 JSONL。脚本会输出总体和分维度的“对”“错”“不适用”数量、适用率及通过率。若每条判断附带 `human_judgment.result`，还会计算人机一致率、错误样本召回率和误召率。

```bash
python scripts/score_result.py --input experiment/judgments.example.jsonl --summary-only
```

脚本不再把判断映射成分数。“不适用”始终保留为独立状态，汇总统计时单独排除。

## 定制模板

1. 复制 `assets/eval-case-template.json`。
2. 编辑 `references/rubric.json`，只保留跨题目复用的判断规则。
3. 为每个维度准备“对”“错”“不适用”和易混淆边界样本。
4. 发布后保持 `dimension_id` 稳定；修改规则时递增 `rubric_version`。
5. 使用开发集修规则，使用未参与修改的留出集验收。

不要把题目事实写进 Rubric，也不要把单次误判直接改成只适用于一条样本的补丁。

## 配套资源

- `assets/sample-case.json`：可直接运行的电商价保样本；
- `assets/sample-judgment.json`：对应判断示例；
- `experiment/regression-set.example.jsonl`：最小回归集；
- `experiment/judgments.example.jsonl`：可直接运行的批量判断与人工标签示例；
- `references/report-checklist.md`：报告口径和版本追溯清单。
