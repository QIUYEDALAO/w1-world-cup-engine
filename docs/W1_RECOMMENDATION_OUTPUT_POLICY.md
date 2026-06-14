# W1 Recommendation Output Policy

版本：W1_RECOMMENDATION_OUTPUT_POLICY_V1

本规则只约束 dashboard 和报告的展示层，不改变 score matrix、DEFAULT_RHO、PLAY_GUARD 或任何模型核心计算。

## 1. 输出边界

- `primary_score` 必须唯一，只能来自已有比分矩阵的主路径。
- `secondary_score` 最多 1 个，可以为空；如果与 `primary_score` 相同，展示层必须置空。
- 机器校验口径：primary_score 必须唯一；secondary_score 最多 1 个。
- 对外主展示不得超过 2 个比分。
- `risk_paths`、`tail_paths`、`open_game_paths` 只能作为风险路径或压力测试展示，不得称为推荐。
- 完整 `score_pool`、`top_scores` 和矩阵参数只保留在专家展开区或详情层。

## 2. 字段约定

`recommendation_view` 从已有 `score_distribution` 派生，字段如下：

- `primary_score`
- `secondary_score`
- `primary_basis="most_likely_result_conditional_mode"`
- `secondary_basis="second_result_conditional_mode"`
- `risk_path_summary`
- `risk_paths`
- `tail_paths`
- `open_game_paths`
- `expert_score_pool_available`
- `display_score_limit=2`

`recommendation_view` 不写回模型核心，不覆盖 `score_distribution`，不参与 rho、lambda、odds parser 或 PLAY_GUARD 计算。

## 3. 风险路径展示

风险路径用于说明比赛如何偏离主路径，例如早球、转换混乱、红牌/点球、尾部崩盘或打开局。它们必须单独放在“风险路径摘要”或“专家展开区”，不能与主比分、备选比分混写成同一类输出。

## 4. 合规说明

W1 只做赛前/赛后数据分析研究。页面输出不是投注平台内容，非投注/下注/资金建议，不承诺命中率，不输出资金管理建议。
