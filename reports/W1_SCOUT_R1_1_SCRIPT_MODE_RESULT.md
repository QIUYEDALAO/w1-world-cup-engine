# W1_SCOUT_R1_1_SCRIPT_MODE_RESULT

日期: 2026-06-18
分支: `w1-scout-reframe-review-c5a4d09`

## 1. 阶段结论

R1.1-S1 已将 `本场解读 · DeepSeek` 从普通自然语言解读收紧为:

- 数据证据链
- 结构化 evidence
- 常规剧本
- 尾部高方差剧本
- 反向风险
- 专家盘口剧本

本阶段只改 Scout 解读合约、prompt、checker 和展示守护,不改 W1 市场底座。

## 2. 新字段说明

`read.evidence_chain_cn`

- 面向页面阅读的人类中文证据链。
- 允许自然语言,但必须引用可见数据来源或明确数据缺失。

`read.evidence`

- 面向 checker 和专家审计的结构化证据数组。
- 每条 evidence 必须包含:
  - `claim`
  - `source`
  - `fields`
  - `availability`
  - `weight`
- `source` 只允许:
  - `form`
  - `xg_roll`
  - `lineups`
  - `injuries`
  - `market`
  - `score_matrix`
  - `rest_days`
  - `standings`
  - `h2h`
  - `environment`
  - `availability`
- `availability` 只允许:
  - `full`
  - `partial`
  - `weak_sample`
  - `missing`
- `weight` 只允许:
  - `high`
  - `medium`
  - `low`

`regular_script_cn`

- 常规比赛展开路径。
- 必须绑定至少 1 条结构化 evidence。

`high_variance_tail_script_cn`

- 尾部高方差路径,例如早球、红牌、转换混乱、定位球、门将失误。
- 必须包含明确触发语义。
- 必须绑定至少 1 条结构化 evidence。

`reverse_risks_cn`

- 与主倾向相反的风险路径。
- 至少 1 条必须包含失效条件,例如久攻不下、低位防守成功、射门质量无法转化、剧本降权或大比分剧本失效。

`market_expert_script_cn`

- 只允许解释盘口语境,例如盘口、让球、大小球、水位、早盘、临场、隐含。
- 不允许写成行动建议。
- 如果盘口数据缺失,必须明确写“盘口数据缺失 / 无法展开盘口剧本 / 不展开盘口剧本”,不能硬编盘口内容。

## 3. 盘口术语边界

允许:

- 解释盘口样本、让球、大小球、水位、早盘、临场、隐含概率。
- 明确说明盘口数据缺失,并降级为“不展开盘口剧本”。

禁止:

- 资金建议
- 下注建议
- 稳赚表达
- 命中承诺
- 把市场差异包装成机会
- 声称独立优势

## 4. Checker 结果

已新增/强化:

- `scripts/check_w1_scout.py`
  - 校验 `read.evidence` 结构化字段。
  - 校验 source / availability / weight 枚举。
  - 校验常规剧本和尾部高方差剧本绑定 evidence。
  - 校验尾部高方差触发条件。
  - 校验反向风险失效条件。
  - 校验盘口剧本支持“盘口数据缺失”降级。
  - 增加反向测试。

- `scripts/check_w1_visual_dashboard.py`
  - 校验 embedded Scout JSON 中的结构化 evidence 形态。
  - 校验 dashboard Scout 卡保留证据链、剧本、风险、盘口剧本区域。

## 5. Dry-run / Live 验证

已执行:

- `python3 scripts/w1_scout_analyst.py --dry-run`
- `python3 scripts/w1_scout_review.py --dry-run`
- `python3 scripts/w1_result_sync.py --dry-run`
- `bash scripts/run_w1_scout_cycle.sh --dry-run`

本地还用 DeepSeek 对 fixture `1539004` 生成过一条新结构 read,仅写入 gitignored `state/w1_scout_calls.json` 用于 checker 验证,不会提交。

## 6. Runtime / Raw State

未提交:

- `state/w1_scout_calls.json`
- `state/w1_scout_bundles.json`
- `data/scout/`
- `data/results/world_cup_2026_results.json`
- raw prompt
- raw API dump
- secret / env

本阶段新增报告自身为 tracked review artifact,不包含 secret 或 raw API dump。

## 7. 红线确认

- 未改 `scripts/w1_score_engine.py`
- 未改 `DEFAULT_RHO`
- 未改 λ
- 未改概率
- 未改 Primary Read 逻辑
- 未 push `origin main`
- 未提交 runtime/raw state
- 未使用投注化展示文案

