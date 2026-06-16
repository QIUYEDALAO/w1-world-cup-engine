# W1 Candidate Offline Eval V1

本报告只描述阶段 A 的同源候选集在既有 FULL 子集上的离线表现。它不是校准层，不接生产，不改变推荐比分算法。

- scope: World Cup 2018 + 2022 FULL subset only
- n_matches: 128
- basis: `market_implied_score_matrix`
- calibrated: `false`
- independent_edge: `false` for every candidate item

## Aggregate Candidate Groups

| market | selection | line | n | mean_raw_probability | mean_expected_result_score | mean_realized_result_score |
|---|---|---:|---:|---:|---:|---:|
| 1X2 | away_win |  | 128 | 0.327135 | 0.327135 | 0.351562 |
| 1X2 | draw |  | 128 | 0.254677 | 0.254677 | 0.226562 |
| 1X2 | home_win |  | 128 | 0.418189 | 0.418189 | 0.421875 |
| AH | away_cover | -0.0 | 128 | 0.327135 | -0.091054 | -0.070312 |
| AH | away_cover | -0.5 | 128 | 0.327135 | -0.34573 | 0.15625 |
| AH | away_cover | 0.5 | 128 | 0.581811 | 0.163623 | -0.296875 |
| AH | home_cover | -0.5 | 128 | 0.418189 | -0.163623 | -0.15625 |
| AH | home_cover | 0.0 | 128 | 0.418189 | 0.091054 | 0.070312 |
| AH | home_cover | 0.5 | 128 | 0.672865 | 0.34573 | 0.296875 |
| BTTS | no |  | 128 | 0.584233 | 0.584233 | 0.515625 |
| BTTS | yes |  | 128 | 0.415767 | 0.415767 | 0.484375 |
| OU | over | 1.5 | 128 | 0.69057 | 0.38114 | 0.46875 |
| OU | over | 2.5 | 128 | 0.427186 | -0.145629 | -0.0625 |
| OU | over | 3.5 | 128 | 0.223476 | -0.553048 | -0.5625 |
| OU | under | 1.5 | 128 | 0.30943 | -0.38114 | -0.46875 |
| OU | under | 2.5 | 128 | 0.572814 | 0.145629 | 0.0625 |
| OU | under | 3.5 | 128 | 0.776524 | 0.553048 | 0.5625 |

## Boundary

- Phase A only: candidate unification and view separation.
- No new calibration, no selector promotion, no score-engine edit.
- All candidate probabilities trace to the same market-implied score matrix.
