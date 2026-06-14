# W1 World Cup Engine 专家评审报告 V2：Score Matrix 集成后复盘

生成时间：2026-06-14 CST  
项目路径：`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`  
报告定位：供足球数据、盘口、模型策略专家继续评审。本文只描述系统状态、数据链路、策略假设、复盘损失和待验证问题，不构成投注/下注/资金建议，也不承诺命中率。

## 1. 当前项目状态

最新 HEAD：

- `e82c324 Add W1 Australia Turkey post-match result`

remote 状态：

- `remote none`
- 当前未 push。

已完成核心阶段：

- `f42c4e1 Integrate W1 score matrix core`
- `2c343ab Add W1 manual lineup override`
- `b654329 Fix W1 manual lineup fixture alias`
- `e82c324 Add W1 Australia Turkey post-match result`

当前系统已经从早期规则化比分池，推进到以市场隐含参数为核心的 score matrix 输出；同时完成 Australia vs Turkey 的 manual lineup、fixture alias、赛后比分写入和 RPS/log score 复盘链路。

## 2. V1 到 V2 的核心变化

V2 相对上一版的核心变化如下：

- `score_distribution` 从规则池改为 `market_implied_poisson_dixon_coles`。
- 24/24 `match_records` 已经满足 `derived_from_score_matrix=true`。
- `score_pool.weight` 从 `high/medium/low` 这类序数字符串，改为概率数值。
- `game_open_trigger` 和 `collapse_mass` 改为比分矩阵区域概率，不再单独拍权重。
- `post_match_calibration` 改为 RPS/log score 评估。
- fixture_id 硬编码比分逻辑已从核心 score distribution / open trigger / collapse / lesson 逻辑中移除。

这一阶段最重要的意义不是“预测更准”这个结论，而是系统开始把比分判断放进可累计评估的概率框架里。这样后续专家可以围绕参数、样本、误差和校准方法讨论，而不是围绕单场文本解释反复修补规则。

## 3. 专家建议采纳情况

已采纳：

- 概率核心：比分输出改为 score matrix 派生，保留 top scores 和区域概率。
- RPS/log score：赛后不再只看主比分或比分池是否命中，而是记录 outcome 和 exact score 的损失。
- 删除 fixture_id 硬编码：单场样本不再作为代码分支影响比分、打开局或崩盘路径。
- manual/fallback source 明确区分：manual verified、cache、fallback、live API 的来源在数据层明确标注。

未完成：

- `rho` 历史校准：当前 Dixon-Coles rho 仍未通过历史样本拟合。
- 历史 CSV 回测：还没有形成覆盖国际比赛、盘口、大小球和赛果的批量回测集。
- lineup/tactical 数值降权与市场重复计价修正：首发和战术解释已经可展示，但尚未稳定转成 lambda 修正，也没有解决与市场价格可能重复计价的问题。

## 4. Australia 2-0 Turkey 复盘

比赛：

- fixture_id：`1539001`
- alias：`66456942`
- 比赛：Australia vs Turkey
- 结果：Australia 2-0 Turkey

赛前人工主倾向曾偏向 Turkey 不败，实际结果为 Australia 2-0 Turkey。这是方向性失误，不应被“比分池存在某些路径”或“赛后解释”掩盖。

系统记录如下：

- `actual_score_probability=0.0303`
- `rps_1x2=0.9654`
- `exact_score_log_loss=3.4974`

这些指标说明，当前 score matrix 对 Australia 2-0 的概率给得较低，且 1X2 方向损失较大。它应该被纳入累计 calibration 样本，而不能基于单场直接调权重。

本场复盘原则：

- 不基于 Australia 2-0 Turkey 单场结果修改 rho。
- 不基于单场结果修改 score matrix 主逻辑。
- 不基于单场结果修改 odds parser。
- 不基于单场结果修改 lineup_effect 或 tactical_effect 权重。
- 不基于单场结果放宽或绕过 PLAY_GUARD。

## 5. 当前模型暴露的问题

Australia 2-0 Turkey 暴露出以下问题：

- 市场先验可能低估 Australia 路径，尤其是 Australia 胜且零封的路径。
- lineup/tactical 解释层仍未充分进入参数修正，目前更多是解释面板，而不是稳定的数值模型输入。
- 门将、定位球、高点优势未量化。
- Australia 三中卫与 Souttar 高点没有形成足够概率修正。
- Turkey 中场技术优势被高估，或至少没有稳定转化成进球概率。
- `rho` 未校准，当前相关结构仍缺乏历史证据支撑。
- 历史样本不足，无法判断本场是市场尾部正常波动，还是 W1 缺少关键修正项。

需要特别注意：这些问题不能靠单场“事后合理化”解决。下一阶段应把这些因素设计成可回测字段和小幅参数修正候选，再用历史样本判断是否有增益。

## 6. 当前系统仍然正确的地方

尽管 Australia 2-0 Turkey 是方向性失误，当前系统仍有几处做法是正确的：

- 没有因为 2-0 单场改权重。
- 使用 `actual_score_probability`、RPS、log score 记录损失。
- 保留 deprecated hit type 仅展示，不作为核心评估。
- manual lineup override 修复了数据链路，使 confirmed lineup 能进入 dashboard。
- alias 修复解决了 `1539001` / `66456942` 的 ID 不一致问题。
- score matrix 输出保留概率池，而不是回退到单比分模板。
- live/manual/cache/fallback 的来源区分没有被抹平。

这意味着系统已经具备“犯错后留下可量化证据”的基础，而不是只留下文本解释。

## 7. 下一步专家评审问题

请专家重点回答以下问题：

- 是否需要把首发、战术、定位球优势转成 lambda 修正？
- Australia 2-0 这种结果应归为市场尾部，还是说明 lineup/tactical 信息未被市场充分吸收？
- `rho` 校准需要哪些历史数据字段？
- score matrix 是否需要加入 overdispersion / bivariate correlation？
- 如何避免根据单场爆冷过拟合？
- `manual_verified` lineup 应该如何赋予 source confidence？
- lineup/tactical 修正应作用于 `lambda_home/lambda_away`，还是只调整区域概率如 open game、collapse、clean sheet？
- 若市场已吸收大部分首发信息，W1 的战术层应如何避免重复计价？

## 8. 下一阶段建议

P0 `W1_RECOMMENDATION_OUTPUT_POLICY_V1`：主比分唯一、备选最多一个。  
目标是把 dashboard 的概率池和老板页表达拆开：专家层保留完整概率矩阵，老板层只展示一个主比分和最多一个备选，不制造“全覆盖式解释”。

P1 `W1_RHO_CALIBRATION_DATA_PREP_V1`：准备历史 CSV。  
需要包含 fixture、球队、开赛时间、1X2、AH、OU、实际比分、赛事类型、是否中立场、首发可用性、裁判可用性等字段。

P2 `W1_LINEUP_TO_LAMBDA_ADJUSTMENT_RESEARCH`：研究首发/定位球/高点对 lambda 的小幅修正。  
重点不是扩大主观权重，而是验证是否存在稳定、可复用、低幅度的修正项。

P3 `W1_REMOTE_BACKUP_V1`：绑定独立 GitHub 仓库。  
当前 remote none 属于 WARN_ONLY，但长期看不利于版本备份和专家协作。

P4 `W1_RUNTIME_CLEANUP_POLICY`：明确 logs/state/match cards 是否提交。  
当前运行后会产生 dirty runtime 文件，需要冻结哪些是审计证据、哪些只作为本地缓存。

## 9. 合规说明

- 本系统仅做赛前/赛后分析研究。
- 不构成投注/下注/资金建议。
- 不承诺命中率。
- 不输出资金管理建议。
- API 凭据只应在后端环境变量或本地安全配置中使用，不进入前端和报告。
- 专家评审应聚焦数据链路、概率模型、校准方法和风险控制，不应将本文解释为任何交易或资金操作依据。

## 10. 附录

### 当前 checker 清单和 PASS 状态

本报告生成前要求运行并通过：

- `python3 scripts/check_w1_post_match_result_update.py`：PASS
- `python3 scripts/check_w1_manual_lineup_override.py`：PASS
- `python3 scripts/check_w1_score_matrix.py`：PASS
- `python3 scripts/check_w1_dashboard_data_binding.py`：PASS
- `python3 scripts/check_w1_visual_dashboard.py`：PASS
- `python3 scripts/check_w1_production_lite.py`：PASS

### 关键文件清单

- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `reports/dashboard/assets/w1_dashboard_data.json`
- `scripts/build_w1_dashboard_data.py`
- `scripts/w1_score_engine.py`
- `scripts/w1_score_matrix_batch.py`
- `scripts/check_w1_score_matrix.py`
- `scripts/check_w1_post_match_result_update.py`
- `scripts/w1_local_predict_server.py`
- `data/results/round1_results.json`
- `data/fixture_aliases.json`
- `data/manual_lineups/1539001.json`
- `data/manual_lineups/66456942.json`
- `config/w1_match_card_schema.json`
- `config/w1_decision_policy.json`

### WARN_ONLY

- `remote none`
- runtime dirty files
- `rho` not calibrated
- historical CSV backtest not complete
- lineup/tactical lambda adjustment not implemented
- runtime/cache/log ownership policy not frozen

### BLOCKER

none
