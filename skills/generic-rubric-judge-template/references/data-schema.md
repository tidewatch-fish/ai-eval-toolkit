# 通用评测数据契约

## 核心原则

题目只提供待评测内容，不定义题目专属 criterion。每条样本通过 `dimension_id` 选择统一维度库中的一套 Rubric。

## 样本输入

必填非空字符串：

- `case_id`：样本唯一标识。
- `user_query`：本轮用户问题。
- `response`：待评测回答。
- `dimension_id`：当前评测维度，只能为 `accuracy`、`completeness` 或 `helpfulness`。

使用 `prepare_eval.py --all-dimensions` 时可省略 `dimension_id`；脚本会为每条样本展开三个相互独立的任务。

可选字符串：

- `reference_context`：冻结的参考材料。
- `standard_answer`：标准答案。
- `conversation_context`：与本轮有关的上文。
- `task_instruction`：系统或产品对回答的额外要求。

可选对象：

- `human_judgment`：人工判断结果。
- `metadata`：来源、数据切分、版本等追溯信息。

将领域事实放入 `reference_context`，不要把特定题目的事实写入统一维度 Rubric。

单个 JSON 对象、JSON 对象数组和 JSONL 均可作为脚本输入。

## 评测模型输出

```json
{
  "case_id": "case-001",
  "dimension_id": "accuracy",
  "result": "对",
  "evidence": [
    "回答原文或精确位置"
  ],
  "reason": "对：核心事实均与参考材料一致。"
}
```

约束：

- `dimension_id` 必须与输入一致。
- `result` 只能为 `对`、`错`、`不适用`。
- `evidence` 必须是至少包含一个非空字符串的数组。
- `reason` 必须为非空字符串，格式为“结论：核心原因。详情”。
- 只输出当前指定维度，不生成题目专属规则。

批量结果可在每条判断中附带：

```json
{
  "human_judgment": {
    "result": "错",
    "reason": "人工标注理由"
  }
}
```

`score_result.py` 检测到 `human_judgment.result` 后，会额外计算人机一致率、错误样本召回率和误召率。

## 结果校验与汇总

`score_result.py` 校验字段和取值，补充 `rubric_version`、维度名称及 `is_applicable`，再生成总体、分维度和题目级汇总。脚本不把结果映射成分数。

“不适用”必须保持独立。任何通过率、召回率和误召率统计都不得把“不适用”当成“对”。

## 批量文件

- `prepare_eval.py`：接受单个 JSON、JSON 数组或 JSONL。
- `score_result.py`：接受单个判断、判断数组、`{"judgments": [...]}` 或 JSONL。
- 批量输出包含 `overall`、`by_dimension` 和 `query_level` 汇总。
- `query_level` 按 `case_id` 聚合：任一维度为“错”则题目为“错”；否则任一维度为“对”则为“对”；全部为“不适用”才为“不适用”。
- `--summary-only` 只输出汇总，适合接入报告脚本。
