# W1 FULL pipeline 异常复核 V1（11 个 market-reproduction 超阈值样本）

> diagnostic_only=`true` · engine_modified=`false` · rho_modified=`false` · refetch=`false`

## 结论
- 超阈值样本：**11/128**（阈值 0.02）。
- 成因分布：**{'DRAW_RATE_TENSION': 11}**。
- 数据 bug：**否**；orientation 结构性排除（精确 date+home_id+away_id 合并）。
- 11/128 超阈值样本全部归因为 DRAW_RATE_TENSION：误差集中于平局，主客复现良好。根因是市场隐含 Dixon-Coles 的固有限制——μ 由 OU 固定、ρ 固定，单一 δ 无法同时匹配市场平局率。非数据 bug、非引擎 bug；记录为已知限制，本阶段不改引擎。

## 逐场
| 比赛 | 实际 | err | 最差 | 市场(H/D/A) | 模型(H/D/A) | draw_gap | μ | fav | 成因 |
|---|---|---:|:--:|---|---|---:|---:|---:|---|
| denmark vs france | 0-0 | 0.0583 | D | [0.15, 0.355, 0.495] | [0.191, 0.297, 0.512] | -0.0583 | 2.061 | 0.495 | DRAW_RATE_TENSION |
| australia vs denmark | 1-0 | 0.0332 | D | [0.148, 0.189, 0.663] | [0.12, 0.222, 0.658] | 0.0332 | 2.579 | 0.663 | DRAW_RATE_TENSION |
| england vs belgium | 0-1 | 0.0316 | D | [0.361, 0.347, 0.292] | [0.376, 0.315, 0.309] | -0.0316 | 2.089 | 0.361 | DRAW_RATE_TENSION |
| france vs australia | 2-1 | 0.028 | D | [0.777, 0.133, 0.09] | [0.777, 0.161, 0.062] | 0.028 | 2.831 | 0.777 | DRAW_RATE_TENSION |
| argentina vs australia | 2-1 | 0.0273 | D | [0.737, 0.158, 0.105] | [0.736, 0.185, 0.079] | 0.0273 | 2.701 | 0.737 | DRAW_RATE_TENSION |
| iceland vs croatia | 1-2 | 0.0247 | D | [0.198, 0.244, 0.558] | [0.18, 0.269, 0.552] | 0.0247 | 2.331 | 0.558 | DRAW_RATE_TENSION |
| australia vs peru | 0-2 | 0.0226 | D | [0.305, 0.271, 0.423] | [0.293, 0.294, 0.414] | 0.0226 | 2.331 | 0.423 | DRAW_RATE_TENSION |
| england vs iran | 6-2 | 0.0222 | D | [0.693, 0.201, 0.106] | [0.692, 0.223, 0.085] | 0.0222 | 2.259 | 0.693 | DRAW_RATE_TENSION |
| saudi_arabia vs mexico | 1-2 | 0.0221 | D | [0.191, 0.225, 0.584] | [0.174, 0.247, 0.578] | 0.0221 | 2.586 | 0.584 | DRAW_RATE_TENSION |
| ghana vs uruguay | 0-2 | 0.0213 | D | [0.234, 0.25, 0.517] | [0.219, 0.271, 0.51] | 0.0213 | 2.459 | 0.517 | DRAW_RATE_TENSION |
| peru vs denmark | 0-1 | 0.0204 | D | [0.261, 0.312, 0.427] | [0.248, 0.333, 0.419] | 0.0204 | 1.848 | 0.427 | DRAW_RATE_TENSION |

## 未来研究候选（仅登记，不在本阶段实现）
- `W1_DRAW_CALIBRATION_RESEARCH`：按场让 ρ 或加平局校准项浮动以吸收平局残差;需动引擎,属红线外,单独立项,先回测证明再上。

## 边界
- 纯诊断;不改引擎/ρ/政策/阈值;平局张力记录为已知限制。
- 不构成投注/资金建议,不承诺命中率。
