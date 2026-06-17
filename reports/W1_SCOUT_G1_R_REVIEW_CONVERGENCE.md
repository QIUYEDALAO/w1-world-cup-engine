# W1_SCOUT G1-R 审阅收敛包

**日期**: 2026-06-18  
**阶段**: G1-R review / convergence only  
**边界**: 暂停 G1 全量开发；本报告只审阅 Scout memory 路径、`.gitignore`、policy、analyst、ledger、checker、dashboard first-screen checker 合约。未改 dashboard，未迁移文件，未新增蒸馏器。

---

## 1. 当前合约总览

| 模块 | 当前路径 / 合约 | 审阅结论 |
|---|---|---|
| Scout runtime 因子 | `data/scout/*.json` | 已被 `.gitignore` 排除；fetcher 写入此目录；checker 会扫描本地文件，禁止 post-match 字段和非法 availability。 |
| Scout memory / growth | `state/scout_track_record.json`, `state/scout_lessons.md` | policy 与 analyst 均指向该路径；两者在 `state/` 下，属于本地运行态，不入仓。 |
| Scout calls | `state/w1_scout_calls.json` | analyst 只写 gitignored state；checker 验证每条 call 的必需字段、honesty、independent_edge、禁词、FADE 门槛。 |
| Scout lock / audit | `state/scout_lock.jsonl`, `state/scout_audit.jsonl` | ledger 赛前 lock 拒绝已开赛 fixture；audit 只读本地 `data/results/round1_results.json`，回填 track record。 |
| Policy | `config/w1_scout_policy.json` | 明确 MEDIUM boldness、默认 AGREE、LEAN/FADE 门槛、防泄漏字段、禁词、growth path 和 lock/audit path。 |
| Analyst | `scripts/w1_scout_analyst.py` | 默认 DeepSeek `deepseek-v4-pro`；输出必须经 `check_w1_scout.validate_call`；强制写入 `honesty_label` 与 `independent_edge=false`。 |
| Fetcher | `scripts/w1_scout_fetch_api_football.py` | 只写 `data/scout/`；赛前滚动数据取 kickoff 前已完赛场；有 SSL/timeout 重试和 post-match 字段清洗。 |
| Scout checker | `scripts/check_w1_scout.py` | 同时守 policy artifacts、fetcher 静态契约、analyst 静态契约、bundle/call runtime 契约和反向测试。 |
| Dashboard embed | `scripts/w1_scout_embed.py` | 将 `state/w1_scout_calls.json` 注入 tracked HTML 的 `<script id="w1-scout-calls">`，展示用 `deepseek:deepseek-pro` 避免旧 V4 红线误伤。 |
| Dashboard first-screen checker | `scripts/check_w1_visual_dashboard.py` | 要求 Director View、研究结论、五维就绪度、候选共识、Scout 分析师面板、预测控件顺序。当前是 token/顺序守护为主。 |
| Autopilot | `scripts/run_w1_scout_cycle.sh` | 执行 fetch -> bundle -> delta -> analyst -> checker -> embed -> lock -> audit；cron 可定时跑。 |

---

## 2. 已收敛的边界

1. **运行态不入仓**  
   `.gitignore` 已覆盖 `state/`、`data/scout/`、`data/forward_ledger/`、dashboard runtime JSON。Scout calls、locks、audit、track record、lessons 和抓取因子均为本地运行态。

2. **DeepSeek 是研究分析师，不改 W1 底座**  
   Scout/DeepSeek 只在上层读 bundle、写 call、展示面板；不改 `w1_score_engine.py`、`DEFAULT_RHO`、decision policy、odds thresholds、λ/比分矩阵。

3. **checker 是唯一安全闸门**  
   analyst 可重试、归一枚举、复用旧有效 call，但最终写入的 call 仍必须符合 `check_w1_scout.validate_call`。禁词、honesty label、independent_edge、FADE=HIGH 均由 checker 守。

4. **防泄漏方向正确**  
   fetcher 取 `form/xg_roll` 时筛 `dt < kickoff`；checker 扫 `actual_score/fulltime/post_match/ft_score` 等 forbidden 字段；ledger audit 与赛果读取只在赛后审计路径。

5. **dashboard 可见性已最小接入**  
   Scout 面板在候选共识后、预测控件前渲染；这是 display-only，不改概率、不覆盖市场读数。

---

## 3. 主要收敛风险

| 优先级 | 风险 | 具体表现 | 建议处理 |
|---|---|---|---|
| P1 | autopilot 失败后可能推进旧 call | `run_w1_scout_cycle.sh` 中 analyst 失败只 echo，随后仍跑 `check_w1_scout.py`；如果旧 `state/w1_scout_calls.json` 仍合法，可能更新 fingerprint、embed 旧 call、继续 lock/audit。 | 最小改动：analyst 非零时不要更新 `.scout_bundles.sha`，不要 embed，不要 lock；保留 audit 可选。 |
| P1 | ledger 只按 fixture 锁一次 | 当前 `scout_lock.jsonl` 以 fixture_id 去重；如果 T-48h、T-2h、T-30m 多次重判，同一 fixture 后续有效 call 不会追加锁定。 | 先定口径：若要审计每次重判，lock key 应改为 `fixture_id + call_hash/asof/band`；若只审计首次赛前锁定，文档要明确。 |
| P1 | “抓齐 24 场”与赛前纪律冲突 | 当前日期下 21 场已开赛/过去，不能再作为 pre-match 因子回填。 | 文档口径应改为“从现在起对未来 fixture 持续抓齐”；已开赛场只允许赛后 audit，不允许伪赛前补因子。 |
| P2 | dashboard Scout checker 仍偏 token 级 | `check_w1_visual_dashboard.py` 要求 `function pScoutAnalyst`、`AI 分析师` 和渲染顺序，但不解析 `<script id="w1-scout-calls">` 的结构。 | 最小改动：新增 HTML embedded scout JSON parse 检查：records >= 1、call 字段完整、honesty_label 可见、generated_by 不含旧 V4 token。 |
| P2 | embed 展示名与 state 模型名不一致 | state 中 `generated_by=deepseek:deepseek-v4-pro`；HTML 展示副本改为 `deepseek:deepseek-pro` 以避开旧 V4 红线。 | 保持可接受，但文档/checker 应明确这是展示层 sanitize，不代表 state 模型名丢失。 |
| P2 | Scout memory 只有结构检查，缺少 lessons 内容检查 | checker 只验证 track record 结构，未验证 `scout_lessons.md` 是否存在非空、有更新时间或禁止投注词。 | 最小改动：checker 增加 lessons 非空、无禁词、可读检查。 |
| P3 | analyst 复用旧有效 call 缺少显式 stale 标识 | 模型失败时可复用旧有效 call，安全但可解释性不足。 | 最小改动：在 state payload 顶层增加 `reused_previous_count` 或 `warnings`；dashboard 不必立刻展示。 |
| P3 | cron 粒度还不是时间档语义 | 当前 cron 是每 2 小时跑；脚本内 delta 是 bundle hash，不是 T-48/T-24/T-12/T-6/T-2/T-1/T-30m 语义门。 | 后续 G1 正式开发再做；G1-R 不实现。 |

---

## 4. 最小改动清单

**不建议现在做大迁移。** G1-R 后的最小技术收敛建议如下：

1. **收紧 autopilot 失败语义**  
   文件：`scripts/run_w1_scout_cycle.sh`  
   改法：analyst 失败时本轮不写 `.scout_bundles.sha`、不 embed、不 lock；只允许 audit 继续跑或直接退出。  
   原因：防止旧 call 在新 bundle 下被误视为本轮已重判。

2. **明确 ledger 锁定粒度**  
   文件：`scripts/w1_scout_ledger.py`, `config/w1_scout_policy.json`, 对应报告  
   选择 A：继续“一 fixture 只锁第一次赛前 call”，文档改清楚。  
   选择 B：改为多版本锁定，key = `fixture_id + call_hash + lock_band/asof`。  
   推荐：先选 A 收敛，等 G1 正式阶段再做 B。

3. **增强 dashboard Scout 嵌入 checker**  
   文件：`scripts/check_w1_visual_dashboard.py`  
   改法：解析 `<script id="w1-scout-calls">`，检查 JSON 可解析、calls 为数组、每条有 `fixture_id/call/market_divergence/honesty_label/independent_edge=false`，并禁止展示副本出现旧 V4 token。  
   原因：把现在的 token 守护提升到结构守护，但不改 dashboard。

4. **增强 Scout memory checker**  
   文件：`scripts/check_w1_scout.py`  
   改法：检查 `state/scout_lessons.md` 非空、无 policy 禁词；检查 track record 有 `overall/by_conviction/by_stance/updated_at`。  
   原因：growth memory 是 G1 后续“会校准”的核心输入，应被 checker 明确守住。

5. **文档统一“24 场抓齐”的时间口径**  
   文件：`reports/W1_SCOUT_COMPLETION_CHECKLIST.md`, `reports/W1_SCOUT_AUTOPILOT_TASKS.md`, `reports/W1_SCOUT_TECH_HANDOFF.md` / `TECHNICIAN_HANDOFF` 二选一  
   改法：统一为“未来 fixture 在赛前抓齐；已开赛/完赛不回填伪赛前因子”。  
   原因：避免技术员为了覆盖率破坏 pre-match discipline。

---

## 5. 不建议纳入 G1-R 的事项

- 不迁移 `state/scout_*` 到新目录。
- 不新增 distiller / 蒸馏器。
- 不把 `state/` 或 `data/scout/` 纳入 git。
- 不改 dashboard 布局或文案。
- 不改 W1 score engine、DEFAULT_RHO、decision policy、odds thresholds。
- 不把 DeepSeek output 接入概率、λ、推荐比分算法。

---

## 6. G1-R 结论

当前 Scout/DeepSeek/F/FiveDim/dashboard checker 多套机制已经能一起跑，但还需要先做**收敛而不是扩建**。最小下一步不是 G1 全量开发，而是：

1. 固化 autopilot 失败不推进旧 call；
2. 明确 ledger 是首次锁定还是多版本锁定；
3. 将 Scout dashboard checker 从 token 检查提升为 embedded JSON 结构检查；
4. 把 Scout memory 的 lessons/track record 纳入 checker；
5. 统一“24 场抓齐”的赛前时间口径。

完成这些后，再进入 G1 正式开发会更稳，不会在 dashboard、Scout、FiveDim、Primary Read、ledger 之间继续长出并行但口径不一致的机制。
