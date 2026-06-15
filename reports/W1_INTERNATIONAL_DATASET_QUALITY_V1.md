# W1 国际赛种子集数据质量报告 V1

> S1B-Seed · pipeline_mode = `1X2_ONLY` · w1_full_pipeline_validated = `false`

## 1. 覆盖
- 总场次：1081（{'WorldCup2026Qualifiers': 889, 'WorldCup2022': 64, 'WorldCup2018': 64, 'WorldCup2014': 64}）
- 1X2 赔率可用：1074
- OU 可用：0 · AH 可用：0（**缺失 → 仅 1X2-only**）
- xG（预选）：339/889（部分覆盖，非必需字段）
- 比赛统计：909 · 犯规：875

## 2. 脏 Finished 标签（仅定位，建模用 90 分钟比分 + ET/点球推导）
- WorldCup2022: Uruguay vs South Korea 0-0 标为 `Penalties`（实际无加时/点球）
- WorldCup2022: Switzerland vs Cameroon 1-0 标为 `Penalties`（实际无加时/点球）
- WorldCup2022: Morocco vs Croatia 0-0 标为 `Penalties`（实际无加时/点球）
- WorldCup2022: Argentina vs Saudi Arabia 1-2 标为 `Penalties`（实际无加时/点球）
- WorldCup2022: Senegal vs Netherlands 0-2 标为 `Extra time`（实际无加时/点球）

## 3. 东道主缺预选历史（WARN，gate 正式 S2）
- Canada（canada）：预选 0 场 / 总 3 场 · 最近 2022-12-01
- Mexico（mexico）：预选 0 场 / 总 11 场 · 最近 2022-11-30
- Usa（usa）：预选 0 场 / 总 8 场 · 最近 2022-12-03

## 4. 样本稀疏（total < 5 的球队：37 支；强度模型需时间衰减 + shrinkage）

| team_id | 总 | 预选 | 正赛 | 最近 |
|---|---:|---:|---:|---|
| argentina | 36 | 18 | 18 | 2025-09-10 |
| brazil | 35 | 18 | 17 | 2025-09-10 |
| uruguay | 30 | 18 | 12 | 2025-09-10 |
| colombia | 27 | 18 | 9 | 2025-09-10 |
| japan | 26 | 15 | 11 | 2025-06-10 |
| australia | 26 | 16 | 10 | 2025-06-10 |
| south_korea | 26 | 16 | 10 | 2025-06-10 |
| croatia | 25 | 8 | 17 | 2025-11-17 |
| france | 25 | 6 | 19 | 2025-11-16 |
| iran | 25 | 16 | 9 | 2025-06-10 |
| saudi_arabia | 24 | 18 | 6 | 2025-10-14 |
| ecuador | 24 | 18 | 6 | 2025-09-10 |
| belgium | 23 | 8 | 15 | 2025-11-18 |
| england | 23 | 8 | 15 | 2025-11-16 |
| chile | 22 | 18 | 4 | 2025-09-10 |

低样本球队（total<5）：anguilla, antigua_and_barbuda, aruba, bahamas, barbados, belize, bhutan, british_virgin_islands, brunei, cambodia, canada, cayman_islands, cook_islands, cuba, dominica, dominican_republic, fiji, grenada, guam, guyana, laos, macau, maldives, mongolia, montserrat, papua_new_guinea, puerto_rico, saint_kitts_and_nevis, saint_lucia, saint_vincent_and_the_grenadines, samoa, solomon_islands, sri_lanka, tahiti, timor_leste, tonga, vanuatu

## 边界
- 仅赛前分析与赛后研究；不构成投注/资金建议，不承诺命中率。
