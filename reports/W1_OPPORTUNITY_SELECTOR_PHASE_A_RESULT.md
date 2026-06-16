# W1_OPPORTUNITY_SELECTOR_PHASE_A_RESULT

## Scope

W1_OPPORTUNITY_SELECTOR_PHASE_A 已按最小阶段 A 落地：只做 read-only candidate unification 与 dashboard view separation，不改模型、不做新校准、不生成单一主结论。

## Implemented

- A1: 新增 `scripts/w1_candidate_builder.py`，从同一 market-implied score matrix 派生 1X2、OU、AH、BTTS、score_pool candidates。
- A2: 新增 `scripts/w1_candidate_offline_eval.py`，在既有 128 场 FULL subset 上生成 `reports/w1_candidate_offline_eval_v1.json` 与 `.md`。
- A3: dashboard 新增 Director 层候选共识块与 Analyst/专家表；候选展示为同源矩阵切片，不产生单一高亮结论。
- A4: prospective snapshot/lock future-write 接线 `candidates_snapshot`；已有 write-once pre_match_view 不重写。
- A5: 新增 `scripts/check_w1_opportunity_phase_a.py`，覆盖候选字段、概率自洽、红线、dashboard 展示、离线报告与反向测试。
- A6: registry 已更新。

## Candidate Contract

每个 candidate 必须包含：

- `basis="market_implied_score_matrix"`
- `independent_edge=false`
- `calibrated=false`
- `raw_probability`
- `expected_result_score`

阶段 A 不包含单一主结论、选择器评分、投注/资金表达或命中承诺。

## Offline Eval

- scope: World Cup 2018 + 2022 FULL subset only
- n_matches: 128
- candidate_groups: 17
- research_only: true
- production_wired: false
- calibrated: false

该离线评估仅用于描述同源候选集在历史 FULL 子集上的基本表现，不用于调参或上线。

## Dashboard

tracked `reports/dashboard/W1_VISUAL_DASHBOARD.html` 保留 file-open 能力，并展示稳定 embedded baseline 中的 candidates。

- Director view: 中性 hero + 四灯 + `候选共识`
- Analyst view: `候选共识 · 专家表`
- 文案明确：同源矩阵、未校准、非独立优势、非推介。
- A3 mockup 5 项修正已补齐：hero 去强预测词；Header chip 只显示比赛生命周期；`盘口跟踪` 替代旧市场变化标签；BTTS 仅在有信息量时显示；动作行改为 `当前观察建议`。

## Prospective Ledger

`snapshot_w1_forward_ledger.py` 将 future snapshot 带上 `candidates_snapshot`；`w1_forward_lock_pre_match_view.py` 在 lock 时复制该字段。

已有 locked pre_match_view 遵守 write-once，不被重写。未来新锁定样本会携带 candidates snapshot。

## Red Lines

- `scripts/w1_score_engine.py`: untouched
- `DEFAULT_RHO=-0.057766`: unchanged
- `config/w1_decision_policy.json`: untouched
- `config/w1_odds_movement_thresholds.json`: untouched
- λ / score matrix calculation logic: unchanged
- FULL pipeline conclusion: unchanged
- draw calibration conclusion: unchanged
- S2 prototype wiring: unchanged
- no API / no fetch / no sidecar

## Checker

```bash
python3 scripts/check_w1_opportunity_phase_a.py
```

Result:

```text
W1 opportunity phase A check PASS (read-only candidates, view separation, red lines intact)
```

## Rollback

No rollback performed.

## Next

阶段 A 完成后，建议先让专家审阅 candidate contract 与 dashboard 认知分层。只有在专家确认需要进入下一阶段时，才讨论 Phase B calibration/prototype；不得从 Phase A 直接接生产 selector。
