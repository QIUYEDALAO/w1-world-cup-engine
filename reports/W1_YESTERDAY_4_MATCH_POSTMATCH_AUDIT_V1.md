# W1 Yesterday 4 Match Postmatch Audit V1

- 审计日期 CST：2026-06-15
- 目标比赛日 CST：2026-06-14
- 数据源：`reports/dashboard/assets/w1_dashboard_data.json`
- 范围：只读审计报告；不改模型、不改 dashboard UI、不提交。
- 说明：方向命中只做展示，不作为调整依据；样本量很小，不能据此调整模型。

## 1. 自动识别的昨天 4 场

| fixture_id | match | kickoff | status | actual_score | result_state |
|---|---|---|---|---|---|
| 1489373 | 卡塔尔 vs 瑞士 | 2026-06-14 03:00 CST | finished | 卡塔尔 1-1 瑞士 | READY |
| 1489371 | 巴西 vs 摩洛哥 | 2026-06-14 06:00 CST | not_started | 缺失 | MISSING_RESULT |
| 1489372 | 海地 vs 苏格兰 | 2026-06-14 09:00 CST | not_started | 缺失 | MISSING_RESULT |
| 1539001 | 澳大利亚 vs 土耳其 | 2026-06-14 12:00 CST | finished | 澳大利亚 2-0 土耳其 | READY |

## 2. 逐场审计

### 卡塔尔 vs 瑞士 (1489373)
- 开球：2026-06-14 03:00 CST；状态：finished
- 实际比分：卡塔尔 1-1 瑞士
- 参考倾向：谨慎观察
- 主比分：0-2；备选比分：1-1
- 主/备结果桶：A / D
- 1X2：H=0.0641, D=0.1631, A=0.7729
- O/U 2.5：Over=0.5398, Under=0.4602
- Top3：0-2(0.1561), 0-1(0.1310), 0-3(0.1203)
- open_game_mass：0.3168
- 市场/比分风险说明：市场期望净胜球 δ=-1.78, 但热门取胜仅 77%、平局 16%; AH 是期望不是保证。 深让不等于大胜；平手盘也可能打开；大小球不直接决定比分。
- 审计判断：主比分命中=否；备选命中=是；方向展示=否；actual in Top8=是
- O/U 2.5 集合：读数=OVER，实际=UNDER，命中=否
- 1X2 最高项：读数=A，实际=D，命中=否
- 打开/尾部路径：是
- 风控上下文：SOFT_THIN, 盘口过旧
- RPS/log：actual_prob=0.0755, rank=5, rps=0.6013, log_loss=2.5834
- hit_type：pool_hit；miss_tags：MATRIX_OPEN_GAME_MASS, FAVORITE_WIN_NOT_COVER_SEPARATION
- lesson：赛后校准：比分池命中，说明多路径比分分布比单一比分更稳。 深让不等于大胜；平手盘也可能打开；大小球不直接决定比分。

### 巴西 vs 摩洛哥 (1489371)
- 开球：2026-06-14 06:00 CST；状态：not_started
- 实际比分：MISSING_RESULT
- 参考倾向：巴西不败
- 主比分：1-0；备选比分：1-1
- 主/备结果桶：H / D
- 1X2：H=0.5748, D=0.2588, A=0.1664
- O/U 2.5：Over=0.4274, Under=0.5726
- Top3：1-0(0.1429), 2-0(0.1218), 1-1(0.1201)
- open_game_mass：0.2189
- 市场/比分风险说明：市场期望净胜球 δ=0.87, 但热门取胜仅 57%、平局 26%; AH 是期望不是保证。 深让不等于大胜；平手盘也可能打开；大小球不直接决定比分。
- 审计判断：主比分命中=缺赛果；备选命中=缺赛果；方向展示=缺赛果；actual in Top8=缺赛果
- O/U 2.5 集合：读数=UNDER，实际=缺赛果，命中=缺赛果
- 1X2 最高项：读数=H，实际=缺赛果，命中=缺赛果
- 打开/尾部路径：是
- 风控上下文：首发未确认, SOFT_THIN, 盘口过旧
- RPS/log：actual_prob=缺失, rank=缺失, rps=缺失, log_loss=缺失
- hit_type：待复盘；miss_tags：无
- lesson：等待赛后校准；RPS/log score 将在实际比分写入后计算。

### 海地 vs 苏格兰 (1489372)
- 开球：2026-06-14 09:00 CST；状态：not_started
- 实际比分：MISSING_RESULT
- 参考倾向：谨慎观察
- 主比分：0-1；备选比分：1-1
- 主/备结果桶：A / D
- 1X2：H=0.1465, D=0.2392, A=0.6143
- O/U 2.5：Over=0.4641, Under=0.5359
- Top3：0-1(0.1357), 0-2(0.1263), 1-1(0.1124)
- open_game_mass：0.2490
- 市场/比分风险说明：市场期望净胜球 δ=-1.03, 但热门取胜仅 61%、平局 24%; AH 是期望不是保证。 深让不等于大胜；平手盘也可能打开；大小球不直接决定比分。
- 审计判断：主比分命中=缺赛果；备选命中=缺赛果；方向展示=缺赛果；actual in Top8=缺赛果
- O/U 2.5 集合：读数=UNDER，实际=缺赛果，命中=缺赛果
- 1X2 最高项：读数=A，实际=缺赛果，命中=缺赛果
- 打开/尾部路径：是
- 风控上下文：首发未确认, SOFT_THIN, 盘口过旧
- RPS/log：actual_prob=缺失, rank=缺失, rps=缺失, log_loss=缺失
- hit_type：待复盘；miss_tags：无
- lesson：等待赛后校准；RPS/log score 将在实际比分写入后计算。

### 澳大利亚 vs 土耳其 (1539001)
- 开球：2026-06-14 12:00 CST；状态：finished
- 实际比分：澳大利亚 2-0 土耳其
- 参考倾向：谨慎观察
- 主比分：0-1；备选比分：1-1
- 主/备结果桶：A / D
- 1X2：H=0.1878, D=0.2669, A=0.5452
- O/U 2.5：Over=0.4272, Under=0.5728
- Top3：0-1(0.1374), 1-1(0.1247), 0-2(0.1133)
- open_game_mass：0.2189
- 市场/比分风险说明：市场期望净胜球 δ=-0.75, 但热门取胜仅 55%、平局 27%; AH 是期望不是保证。 深让不等于大胜；平手盘也可能打开；大小球不直接决定比分。
- 审计判断：主比分命中=否；备选命中=否；方向展示=否；actual in Top8=否
- O/U 2.5 集合：读数=UNDER，实际=UNDER，命中=是
- 1X2 最高项：读数=A，实际=H，命中=否
- 打开/尾部路径：是
- 风控上下文：SOFT_THIN, 盘口过旧
- RPS/log：actual_prob=0.0307, rank=11, rps=0.9566, log_loss=3.4848
- hit_type：miss；miss_tags：FAVORITE_WIN_NOT_COVER_SEPARATION
- lesson：赛后校准：实际比分未进入比分池，需要检查市场先验、打开局质量和尾部概率。 深让不等于大胜；平手盘也可能打开；大小球不直接决定比分。

## 3. 汇总

- 已识别昨天比赛：4 场
- 已有实际比分：2 场
- 缺赛果：2 场：巴西 vs 摩洛哥, 海地 vs 苏格兰
- 主比分命中：0/2
- 备选比分命中：1/2
- 主或备命中率：0.5000
- 方向展示率：0.0000（仅展示）
- Top8 覆盖：0.5000
- O/U 2.5 集合命中率：0.5000
- 1X2 最高项命中率：0.0000
- mean actual_score_probability：0.0531
- mean RPS 1X2：0.7790
- mean exact score log loss：3.0341

## 4. 审计结论

- 4 场中当前只有 2 场有实际比分，样本太小。
- Qatar vs Switzerland：备选比分命中，实际比分在 Top8 内；但 1X2 最高项和 O/U 2.5 集合方向未中。
- Australia vs Turkey：主/备比分、1X2 最高项均未中，actual score 未进入 Top8，是需要继续累计观察的方向性失误样本。
- Brazil vs Morocco、Haiti vs Scotland：当前 W1 数据缺赛果，标记 MISSING_RESULT，不能纳入 RPS/log 汇总。
- 本报告只作为赛后审计，不据此调整 rho、score matrix、盘口阈值或推荐口径。

