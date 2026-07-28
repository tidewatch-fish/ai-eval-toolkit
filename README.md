# AI Evaluation Toolkit

面向 LLM 与 AI Agent 的自动化评测工具箱。

当前版本提供两份可独立安装的 Rubric Judge Skill，以及一组能够同时验证两份 Skill 的 Gold Set。它把评测拆成三个固定维度：准确性、完整性和帮助性；每次任务只判断一个维度，输出“对”“错”或“不适用”。

## 选择 Skill

| Skill | 适用场景 |
| --- | --- |
| `generic-rubric-judge-template` | RAG、客服、文档助手、Agent 等开放式生成任务 |
| `finance-rubric-judge` | 银行、财富管理、借贷、支付等金融问答，额外覆盖利率、费用、期限、资格和无依据承诺 |

两个目录都是自包含 Skill。即使脚本存在少量重复，也不要抽到公共目录，否则单独复制一个 Skill 后将无法运行。

## 安装

克隆仓库：

```bash
git clone https://github.com/tidewatch-fish/ai-eval-toolkit.git
cd ai-eval-toolkit
```

将需要的 Skill 目录复制到 Codex Skills 目录。

macOS / Linux：

```bash
mkdir -p ~/.codex/skills
cp -R skills/generic-rubric-judge-template ~/.codex/skills/
cp -R skills/finance-rubric-judge ~/.codex/skills/
```

Windows PowerShell：

```powershell
$skillRoot = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Copy-Item "skills\generic-rubric-judge-template" $skillRoot -Recurse -Force
Copy-Item "skills\finance-rubric-judge" $skillRoot -Recurse -Force
```

安装后可以直接说：

```text
使用 $generic-rubric-judge-template，分别从准确性、完整性和帮助性评测下面这条回答。
```

或：

```text
使用 $finance-rubric-judge，评测下面这条金融回答，并指出证据和规则边界。
```

如果当前 AI 工具不支持自动发现 Skill，让模型先读取对应目录中的 `SKILL.md`，再提交评测样本。

## 快速验证

本仓库不依赖第三方 Python 包，使用 Python 3.10 或更高版本即可运行。

```bash
python examples/verify_two_skills.py
```

验证脚本会使用同一份金融问答 Gold Set，依次检查：

1. 通用版和金融版能否读取 JSONL；
2. 单条回答能否展开为三个独立维度任务；
3. 人工标签是否会从 Judge 任务中隔离；
4. 批量结果能否计算通过率、适用率、错误样本召回率和误召率；
5. 多个维度能否按 `case_id` 聚合为题目级结论。
6. 人工标为“错”而 Judge 返回“不适用”时，能否正确计为漏判。

成功时输出：

```json
{
  "success": true
}
```

样例的预期结果：

| 口径 | 对 | 错 | 不适用 |
| --- | ---: | ---: | ---: |
| 维度级，7 条 | 3 | 3 | 1 |
| 题目级，3 条 | 1 | 1 | 1 |

示例 Judge 结果与人工标签完全一致，因此该固定样例的人机一致率和错误样本召回率均为 100%，误召率为 0%。验证脚本还额外构造了一组漏判场景，确认 Judge 返回“不适用”时不会从人工错误样本的召回率分母中消失。这只验证数据与统计闭环，不代表任意 Judge 模型都能达到相同表现。

## 工作方式

```text
评测样本
  → prepare_eval.py 校验并生成单维度任务
  → Judge 模型按对应 Rubric 判断
  → score_result.py 校验结果并汇总指标
```

脚本不会调用模型 API。模型、Prompt、调用并发和结果存储方式由使用者自行选择。

`score_result.py` 不把判断映射成分数。“不适用”始终保持独立，统计通过率时单独排除；但人工标为“错”而 Judge 返回“不适用”时，仍按漏判计算错误样本召回率。

具体业务事实应放入样本的 `reference_context`，不要写进固定 Rubric。需要核对某道题独有答案点时，应使用逐题 criterion，而不是继续扩张全局维度规则。

## 仓库结构

```text
ai-eval-toolkit/
├── skills/
│   ├── generic-rubric-judge-template/
│   └── finance-rubric-judge/
├── examples/
│   ├── shared-finance-cases.jsonl
│   ├── shared-finance-judgments.jsonl
│   └── verify_two_skills.py
└── .github/workflows/validate.yml
```

每个 Skill 包含：

- `SKILL.md`：评测流程和边界；
- `references/`：Rubric、数据契约和报告检查表；
- `scripts/`：任务准备和确定性评分脚本；
- `assets/`：单条输入输出模板与样例；
- `experiment/`：回归集和批量判断样例；
- `agents/openai.yaml`：Codex 展示元数据。

## 贡献

提交规则修改时，请同时提供触发修改的误判样本，并运行：

```bash
python examples/verify_two_skills.py
```

不要提交真实客户信息、生产规则、访问凭据或无法公开的业务数据。

## 免责声明

金融目录中的机构、产品和规则均为虚构评测材料，仅用于演示自动化评测方法，不构成金融建议。

## License

[Apache License 2.0](LICENSE)
