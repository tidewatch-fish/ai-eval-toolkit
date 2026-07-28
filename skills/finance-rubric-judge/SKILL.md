---
name: finance-rubric-judge
description: 使用金融领域固定维度 Rubric 评测模型回答，并生成可追溯的结构化判断与批量汇总。适用于银行、财富管理、借贷、支付等高风险问答的准确性、完整性、帮助性单维度评测，也适用于 Gold Set 人工标签对齐、回归测试和无依据承诺识别；当用户要求评测金融回答、搭建金融 LLM-as-a-Judge、分析误判或校准规则时使用。
---

# 金融 Rubric 评测器

使用固定金融质量规则评测回答。不要为每道题临时生成 criterion，也不要在评测过程中提供新的金融建议。

## 执行评测

### 1. 读取规则和数据契约

先读取：

- `references/finance-rubric.json`：维度触发条件、通过条件、不通过条件和边界规则。
- `references/data-schema.md`：输入输出字段与数据约束。

### 2. 准备任务

将用户提供的内容整理为 `assets/eval-case-template.json` 的结构。只评测一个维度时，指定 `dimension_id`：

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
3. 仅使用输入中的参考材料、标准答案、对话上下文和任务要求判断。
4. 引用待评回答中的直接证据，输出一个结构化判断。

始终隔离维度：

- 已表达内容的正误属于准确性；
- 信息遗漏属于完整性；
- 已提供内容是否清晰、可理解、可执行属于帮助性；
- 同一问题不要在多个维度用相同理由重复判错。

输出：

```json
{
  "case_id": "fin-001",
  "dimension_id": "accuracy",
  "result": "错",
  "evidence": ["回答中的原文或精确定位"],
  "reason": "错：核心结论与参考材料相反。"
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

## 金融领域边界

- 只依据给定参考材料、标准答案和上下文判断。
- 准确性缺少可靠核验材料时返回“不适用”，不要用外部常识补判。
- 不要假设所有金融回答都需要免责声明；只有参考材料或任务要求明确需要时，才按对应维度判断。
- 准确性维度中，无依据的收益、审批、赔付、时效或无风险保证直接判不通过。
- 不要因为“金融风险高”而扩大用户问题的必要信息范围。

## 校准规则

1. 使用 `experiment/regression-set.example.jsonl` 建立最小回归集。
2. 用开发集定位误判并修改 `references/finance-rubric.json`。
3. 递增 `rubric_version`，再用未参与修改的留出集验收。
4. 按 `references/report-checklist.md` 记录版本、召回率和误召率。

不要把某个产品的利率、费用、期限或资格写进通用 Rubric；把这些事实放在样本的 `reference_context` 中。

## 配套资源

- `assets/sample-case.json`：可直接运行的定期存款样本；
- `assets/sample-judgment.json`：对应判断示例；
- `experiment/regression-set.example.jsonl`：金融边界最小回归集；
- `experiment/judgments.example.jsonl`：可直接运行的批量判断与人工标签示例；
- `references/report-checklist.md`：报告口径和版本追溯清单。
