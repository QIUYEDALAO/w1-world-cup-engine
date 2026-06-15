# W1_OUTPUT_LAYER_SAFE_VIEW_V1

阶段：`W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1`（S0 子轨）
定位：**纯展示层**。只改 dashboard 的数据派生与渲染表达，**不改 λ / ρ / μ / δ / Dixon-Coles 矩阵 / market reproduction 任何模型量**。

## 1. 为什么要做

单格众数比分(argmax)在泊松型分布里恒偏小，会系统性低估净胜与总进球。例：西班牙 vs 佛得角，模型 μ=3.47、净胜≥2 概率 67.8%、总进球≥4 概率 45.6%，但头条"主比分"给 2-0(仅 13.6%)，与"略偏大比分"自相矛盾。S0 不改模型，只把头条从"一个比分结论"改成"结果 + 区间 + 分布形态"。

同时修一个已暴露给用户的错标：场景质量面板"防线崩盘（热门输）46%"其实是 `blowout_prob`(净胜≥3)，真正的热门输只有 3.7%。

## 2. 改了什么

### 2.1 数据层（`build_w1_dashboard_data.py`，新增 `build_safe_view`）
每场新增 `safe_view` 字段(由**同一比分矩阵**派生，附加字段，不动模型)：

- `outcome`：主/平/客(= model_hda)。
- `total_goals_range`：`band_0_1` / `band_2_3` / `band_4_plus` / `most_likely_band` / `expected_total(μ)`。
- `goal_difference_range`：平局、热门净胜 1/2/3+、热门取胜合计、`most_likely_margin_cn`。
- `tail_mass`：`total_over_3_5`、`blowout_margin_3_plus`(净胜≥3)、`favorite_loss`(真实热门输)。
- `distribution_shape_summary_cn`：一句话形态摘要。
- `primary_score` + `primary_score_prob`：标明主比分只是最高单格。
- `disclaimer_cn`。

`safe_view` 同时进入 public 输出，供前端读取。

### 2.2 展示层（`W1_VISUAL_DASHBOARD.html` 的渲染 JS）
- `pCore`：主比分标题降权为"主比分 · 最高单格概率"；备选标"· 至多一个"；新增"比分形态读数"行(总进球区间 + 净胜区间 + 形态摘要 + "主比分不代表整场形态"提示)。
- `pScenarios`：场景质量行修正为四条——防平、打开局(总≥4)、**大胜(净胜≥3)=blowout**、**热门被翻盘(热门输)=favorite_loss**。删除把 blowout 错标成"热门输"的旧写法。

## 3. 边界（红线）

- 不改 `w1_score_engine.py`、`DEFAULT_RHO`、`w1_decision_policy.json`、`w1_odds_movement_thresholds.json`。
- `safe_view` 是矩阵派生的附加读数；λ/ρ/μ/δ/model_hda/top_scores/market_fit_error 逐场指纹必须与改造前一致(已验证 diff=NONE)。
- 保留输出政策：主比分唯一、备选最多一个；风险路径/尾部路径/Top scores 不得称为推荐；专家区默认折叠。
- 不出现投注/资金/命中率承诺表达；保留"非最终结论、不构成收益承诺或操作指令"。

## 4. 自检

```bash
python3 scripts/check_w1_output_safe_view.py
```

校验：safe_view 字段完整、区间/尾部字段齐全、热门输与净胜≥3 已分离、主≤1/备≤1、专家区默认折叠、无促性表达、模型指纹未变(由 check_w1_score_matrix 等既有 checker 共同保证)。
