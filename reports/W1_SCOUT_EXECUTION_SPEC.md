# W1_SCOUT 执行规格 — 会学习的 AI 分析师闭环

**日期**: 2026-06-17
**目标**: 把 W1 从"市场镜子"升级为**有真实数据喂养、敢说敢干、且能随战绩成长的 AI 分析师**。
**规则变更**: 老板已解锁外部/API(api-football 已接);本规格起,**允许联网抓取真实因子数据**。
**起步范围**: 世界杯(当前无五大联赛/其他一级赛)。

---

## 0. 诚实边界(先讲死,免得变成骗子工具)

- W1_SCOUT **可以**:用真实数据 + AI 判断给出**敢和市场不一样**的研究结论;记录、审计、并随战绩自我校准、越来越懂自己。
- W1_SCOUT **不承诺**:系统性赢市场。阶段 C 已证明常见因子打不过收盘赔率。**"敢说敢干"指它敢表态、敢逆市场,不指它保证对。**
- 每条结论必须带 **conviction + 该场景历史战绩 + "AI 观点·未验证"标注**;**永不**出现"稳赢/必中/保证/资金/下注"等词。
- 仍不造假数据;赛前判断只用**赛前可得**数据(防泄漏);赛后结果只作审计,不回灌进当场判断。
- "成长"= **基于战绩与教训的经验累积 + 置信校准**(不是重训模型权重);诚实、可追溯。

---

## 1. 架构四层

```
① 数据层(你的 pipeline 抓)   api-football 扩抓真因子 → scout_bundle(每场一份)
② AI 分析师层(敢说敢干)       LLM 读 {scout_bundle + 市场读数 + 战绩记忆} → 结构化大胆判断
③ 锁定 + 审计(复用现有 ledger) 赛前锁定判断 → 赛后对照(准不准 + 逆市场时谁对)
④ 成长引擎(变聪明)            战绩记忆 + 教训库 + 校准回灌 → 喂回 ②,下次更聪明
```

---

## 2. 数据层(你的 pipeline 扩抓 — 我定字段,你机器跑)

现有 pipeline 已拉:`/fixtures`、`/fixtures/lineups`、`/odds`、`/injuries`。**需新增:**

| 新增 endpoint | 取什么(真因子) |
|---|---|
| `/teams/statistics?team=&league=&season=` | 近况:近N场胜平负、场均进/失球、主客分项、form 串 |
| `/fixtures/statistics?fixture=` | 历史场次 xG/射门/控球(**只取该队过往场,滚动**,不取当场) |
| `/standings` | 排名、积分、净胜(已有 watcher,纳入 bundle) |
| `/predictions?fixture=` | api-football 自带预测(作**对照**,不直接采信) |
| `/fixtures/headtohead?h2h=A-B` | 真实 H2H 近交手 |

**产物 `scout_bundle`(每场一份,你 pipeline 写到本地,我消费):**
```
fixture_id, kickoff_utc, home, away, league, season,
market: { p_home,p_draw,p_away, ah_line, ou_line }      # 来自 W1 市场读数
form_home/away: { last5_wdl, gf_avg, ga_avg, ppg, home_or_away_split }
xg_roll_home/away: { xg_for, xg_against, shots, sot }     # 滚动,赛前可得
lineup: { confirmed, formation_home/away, key_absences }
injuries_home/away: [ {player, importance} ]
standings: { rank_home, rank_away, pts_gap }
h2h: { last_n, home_wins, draws, away_wins }
rest_days: { home, away, diff }
api_pred: { ... }                                        # 仅对照
fetched_at_utc, asof_pre_kickoff: true
```
**红线**:bundle 只含赛前可得;**绝不含当场赛后统计**;checker 校验。

---

## 3. AI 分析师层(敢说敢干 — 这是核心)

**输入**:`{ scout_bundle + W1 市场读数 + 系统战绩记忆(见 §5) }`
**输出(结构化,强制字段)**:
```
fixture_id
call: { outcome_lean(主/平/客), scoreline_lean, confidence(0-1) }
market_divergence: {
   stance: AGREE | LEAN_DIFFERENT | FADE_MARKET,     # 必须表态
   where_cn,                                          # 在哪不一样
   why_cn                                             # 为什么(引具体因子)
}
key_factors_cn: [ 2-4 条真实数据依据 ]
conviction: LOW | MEDIUM | HIGH                        # 高=敢逆市场
track_record_context_cn                                # "我在此类局面 X-Y"(来自§5)
honesty_label: "AI 观点·未验证·非投注·可能错"
independent_edge: false
```
**敢说敢干合同**:
- `stance` **必填**;允许 `FADE_MARKET`(逆市场),但 `conviction=HIGH` 才可逆,且必须给出 why。
- 不准只复述市场(纯 AGREE 且无 why = 退回"翻译",checker 拒)。
- confidence 必须被 §5 的校准缩放(过往过度自信→压低)。

---

## 4. 锁定 + 审计(复用已建好的 forward-ledger)

- **赛前锁定**:把每条 call 写进 prospective lock(`lock_as_of_utc <= kickoff`,不可变),复用 `w1_forward_lock_*` 模式。
- **赛后审计**:复用 `w1_forward_post_match_audit` 思路,新增两项打分:
  1. **绝对准度**:outcome/scoreline 命中、Brier/logloss。
  2. **逆市场价值**:当 `stance=FADE_MARKET` 时,**它对还是市场对**(对比同场市场读数)——这是判断"AI 到底有没有用"的真相计。
- 拒绝 hindsight;赛果只作审计,不进当场判断。

---

## 5. 成长引擎(变聪明 — 新核心)

三个持久文件(gitignored,随时间长大):

1. **`state/scout_track_record.json`** — 按场景切片的战绩:
   `{ overall: {n,hit,brier}, by_conviction:{HIGH:{n,hit}...}, by_stance:{FADE_MARKET:{n,fade_win}...}, by_situation:{"逆主队热门":{n,hit}, "高原小球":{...}} }`
2. **`state/scout_lessons.md`** — 从输赢蒸馏的可读教训(每次审计后更新):
   例:"逆主队热门 6-9,过度自信→ FADE 只在 conviction 真高时";"高原(>1500m)小球 7-3,可适度加重"。
3. **校准表** — 实测 confidence vs 命中率,生成缩放系数。

**回灌**:②每次开口前,**先读这三样**(track record + lessons + 校准)写进 prompt → 它带着"自己的经验和教训"判断。这就是成长闭环:**跑得越多,记忆越厚,越知道自己几斤几两**。

---

## 6. Checker + 红线(更新版)

新增 `check_w1_scout.py` 硬断言 + 反向测试:
- scout_bundle 无当场赛后统计(防泄漏,结构性证明:首次出场无滚动)。
- 每条 call 字段齐 + `stance` 必填 + 纯 AGREE 无 why 被拒 + `honesty_label` 在 + `independent_edge=false` + 无"稳赢/必中/保证/资金/下注"词。
- 锁定不可变;审计拒 hindsight;`FADE_MARKET` 必须 `conviction=HIGH`。
- 成长文件只追加/更新,不篡改历史锁定。

**红线(变更后)**:✅ 现在**允许**联网抓取(你 pipeline);❌ 仍不改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵 的市场底座(SCOUT 是上层,不动底座);❌ 不造假;❌ 不输出投注/资金/命中承诺;❌ 赛后不泄漏进赛前。

---

## 7. 分工 + 谁跑 AI

- **你的 pipeline(你机器,有 key+网络)**:扩抓 → 写 `scout_bundle`。
- **我(Claude)= AI 分析师**:读 bundle + 战绩记忆 → 产出 call。MVP 阶段我直接生成;长期可挂**每日定时任务**自动跑锁定+审计+成长。
- 底座 W1 不变,SCOUT 叠在上面。

---

## 8. 落地第一步(MVP,世界杯)

1. **你**:pipeline 扩抓下一轮世界杯各场的 `scout_bundle`(form/xG/lineup/injuries/h2h/standings),写到 `data/scout/`。
2. **我**:建 `scout_bundle` schema + `check_w1_scout.py` + 成长文件骨架 + 锁定/审计接线;对已有数据先跑一遍(冷启动,无战绩),产出第一批**敢说敢干**的 call。
3. **赛后**:审计 → 播种 `track_record` + `lessons`。第二轮起,AI 带着记忆判断 → 开始变聪明。

> 冷启动诚实提醒:**第一批 call 没有历史战绩垫底,就是"裸判断"**;价值随审计轮次累积。这跟 prospective 纪律一致——不能无中生有,只能跑出来。

---

## 9. 待你确认即动手

- 我先落地**第 2 步里我能做的部分**(schema + checker + 成长骨架 + 锁定/审计接线 + 用现有本地数据跑第一版 call),不依赖你先扩抓也能起步(只是因子会偏薄)。
- 你那边**扩抓 scout_bundle** 后,因子变厚,call 立刻更有料。
- 要不要我现在就动手建骨架?还是你先看规格有没有要改的方向(尤其"敢说敢干"的尺度、conviction 逆市场的门槛)。
