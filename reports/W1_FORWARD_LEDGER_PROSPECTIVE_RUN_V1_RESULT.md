# W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1_RESULT

日期：2026-06-16

## 1. 阶段结论

`W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1` 已按方案 A（最小 prospective 闭环 V1）落地。

本阶段目标不是改模型，而是建立真正 prospective 的赛前-赛后闭环样本：

- 赛前从现有 `data/forward_ledger/w1_forward_ledger.jsonl` 锁定 immutable `pre_match_view`。
- 赛中不改 `pre_match_view`。
- 赛后只追加 `post_match_audit`。
- 汇总生成 prospective calibration report。
- runtime stores 保持在 `data/forward_ledger/`，不入仓。

## 2. 严格边界

已执行：

- 只基于现有 `data/forward_ledger/w1_forward_ledger.jsonl`。
- V1 只锁定 `market_implied_1x2`。
- `pre_match_view` write-once：已有 fixture 跳过，不重写。
- `post_match_audit` 只读取本地 `data/results/round1_results.json`。
- calibration report 允许样本为 0，并明确这是 prospective discipline，不是模型失败。
- `data/forward_ledger/` 下 runtime JSONL / JSON 不提交。

未执行：

- 未扩 OU snapshot。
- 未扩 exact score snapshot。
- 未接 dashboard / predict / build。
- 未抓取、未接 API、未外推。
- 未把模型-市场分歧写成机会。

## 3. 新增文件

| 文件 | 用途 |
|---|---|
| `config/w1_prospective_audit_schema.json` | prospective audit schema / hard rules |
| `scripts/w1_forward_lock_pre_match_view.py` | 从 pre-match forward ledger 锁定 write-once `pre_match_view` |
| `scripts/w1_forward_post_match_audit.py` | 从本地赛果追加 `post_match_audit` |
| `scripts/w1_forward_prospective_report.py` | 汇总 prospective calibration report |
| `scripts/check_w1_forward_prospective_run.py` | checker：immutability / no hindsight / local result / gitignored runtime / red lines |
| `reports/W1_EXPERT_PROJECT_REPORT.md` | registry 更新 |

## 4. Runtime Store 状态

本机运行结果：

```text
W1 pre_match_view lock: locked 0 new (skipped existing=12, no usable pre-match 1X2=0); view store total rows=12
W1 post_match_audit: appended 0 (skipped: no local result=12, already audited=0, refused non-pre-match=0); audit store total rows=0
W1 prospective report: views_locked=12 audited=0 mean_rps_1x2=None -> data/forward_ledger/w1_prospective_calibration_v1.json
```

解释：

- 当前已有 12 条 `pre_match_view` 被锁定。
- 当前 `post_match_audit` 样本数为 0，因为这些 locked fixtures 尚无本地 `round1_results.json` 赛果可审计。
- 这是正确的 prospective discipline：没有本地赛果就不做 hindsight audit，不代表模型失败。

`data/forward_ledger/` 已被 `.gitignore` 覆盖，live stores 不入仓。

## 5. Checker 结果

```text
W1 forward prospective run check PASS (views=12 immutable/pre-kickoff; audits reference & match views; stores gitignored; production untouched)
W1 forward-ledger check PASS (rows=12, no post-match leakage, as_of present)
```

核心断言：

- `pre_match_view` 每个 fixture write-once，不允许重复。
- `lock_as_of_utc <= kickoff_utc`，禁止 hindsight。
- `pre_match_view` 不含 `actual_score` / `result` / `post_match_calibration` / `rps` 等赛后字段。
- `post_match_audit.locked_prediction == pre_match_view.locked_prediction`。
- `post_match_audit.result.source == local_round1_results`。
- new scripts 不含外部 fetch pattern。
- `data/forward_ledger/` runtime stores gitignored 且不 tracked。

## 6. 红线确认

未修改：

- `scripts/w1_score_engine.py`
- `DEFAULT_RHO`
- `config/w1_decision_policy.json`
- `config/w1_odds_movement_thresholds.json`
- FULL pipeline 结论
- draw calibration 结论
- S2 prototype 接线状态

未引入：

- 投注建议
- 资金建议
- 命中率承诺
- 模型-市场分歧机会化表达
- 外部抓取 / API 接入
- OU / exact score prospective snapshot
- dashboard / predict / build 接线

## 7. 是否发现真实数据错误

否。

当前只是建立 prospective 闭环机制；`post_match_audit` 样本为 0 是因为本地赛果尚未覆盖已锁定 fixtures，不是数据错误。

## 8. 是否回滚

否。

本阶段只新增 prospective audit layer，并由 checker 约束为 research/audit runtime，不改变生产模型或运行入口。

## 9. 下一阶段建议

1. 继续按赛程运行 `snapshot_w1_forward_ledger.py` 积累赛前快照。
2. 每场赛后只在本地 `round1_results.json` 已有事实赛果后运行 audit。
3. 等 `post_match_audit.n` 有实质样本后再读 prospective calibration report。
4. 若未来要评估 OU / exact score，必须另开 V2 扩展 pre-match snapshot schema，不能用 hindsight 补字段。
