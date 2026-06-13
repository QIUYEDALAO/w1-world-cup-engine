# W1 World Cup Engine 专家评审报告

生成时间：2026-06-14 CST  
项目路径：`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`  
报告定位：供足球数据、盘口、模型策略专家审阅。本文不是营销文案，不构成投注、下注、资金建议，也不承诺命中。

## 1. 项目概览

### 项目目标

W1 World Cup Engine 是一个面向 2026 世界杯赛前分析的本地化工作流系统。目标是在比赛前多阶段整合 fixture、赔率、让球、大小球、首发、伤停、裁判、天气、场地、战术效应和赛后复盘信息，形成可解释的赛前判断面板。

系统当前重点不是追求单点比分，而是把赛前判断拆成：

- 数据是否齐全；
- 是否允许进入正式判断；
- 哪些因素支持当前方向；
- 哪些因素反对当前方向；
- 哪些数据缺口阻断正式判断；
- 比分分布有哪些路径；
- 比赛可能如何被打开；
- 赛后如何反证和校准。

### 使用场景

- 世界杯小组赛赛前数据汇总；
- 点击 dashboard 后实时刷新关键数据；
- 给分析者展示当前比赛的可解释风险；
- 记录赛后比分，校准比分池、盘口假设和比赛打开机制；
- 给专家审查 W1 的策略假设与工程边界。

### 当前边界

- 本地运行，dashboard 由 `w1_local_predict_server.py` 服务提供；
- 不接外部聊天推送；
- 不改旧 V3/V4/M1 系统；
- 不配置远程仓库；
- 不推送；
- 运行时文件与代码提交分离。

### 非目标

W1 不是投注平台，不输出资金建议，不承诺命中率，不把早盘参考包装成正式结论。

## 2. 当前代码与提交状态

### 项目根目录

`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`

### 最新 HEAD

`70531e3 Add W1 post-match auto calibration`

### 最近关键 commits

- `70531e3` post-match auto calibration
- `2761452` score distribution
- `b09faf9` live API on click
- `d30ca27` live lineup refresh
- `e1877d4` lineup effect
- `5eca18e` weather integration

### remote 状态

当前无 remote 输出，未推送。

### runtime 文件边界

当前工作区存在 runtime WARN_ONLY 文件，包括：

- `reports/dashboard/assets/w1_dashboard_data.json`
- `state/w1_predict_progress.json`
- `state/w1_refresh_state.json`
- `state/w1_live_refresh_state.json`
- `state/w1_weather_cache.json`
- 部分 match card runtime 写回
- logs 与旧 snapshot 文件

这些文件反映本地运行状态，不应与代码变更混在一起提交。报告本身只作为文档提交。

## 3. 系统架构

### dashboard 前端

核心文件：`reports/dashboard/W1_VISUAL_DASHBOARD.html`

职责：

- 中文老板版交互入口；
- 今日/下一场焦点选择；
- 对阵预测台；
- 点击“开始预测”后调用本地 `/predict`；
- 轮询 `/progress`；
- 展示数据质量、实时刷新来源、首发效应、战术效应、天气/场地、比分分布、赛后校准。

### local predict server

核心文件：`scripts/w1_local_predict_server.py`

职责：

- 只监听 `127.0.0.1`；
- 提供 `/health`、`/predict`、`/progress`、`/dashboard-data`；
- 按 fixture_id 精确匹配比赛；
- 后端读取接口凭据，不返回到前端；
- 写入 `state/w1_predict_progress.json`；
- 写入本次 `live_refresh` 状态；
- 触发 dashboard data rebuild。

### build dashboard data

核心文件：`scripts/build_w1_dashboard_data.py`

职责：

- 读取本地 match cards、ledger、state、latest snapshot、weather cache、venue mapping；
- 生成 `match_records`；
- 生成 `data_quality`、`environment_context`、`lineup_effect`、`tactical_effect`、`score_distribution`、`post_match_calibration`；
- 写入 `reports/dashboard/assets/w1_dashboard_data.json`；
- 同步更新 dashboard HTML 内嵌数据，支持双击打开。

### watcher

核心文件：`scripts/w1_watcher.sh`

职责：

- 常规刷新；
- 无实质变化不写快照、ledger、git；
- 关注 odds、AH、OU、lineup、referee、injury 等实质变化；
- 不推送，不写旧系统。

### match card

路径：`data/processed/match_cards/group_stage_round1/`

职责：

- 承载每场比赛的 fixture、球队、市场、阵容、上下文、风险、缺口、决策；
- 运行时可被 click-to-predict 写入更新后的首发和 live_refresh；
- 仍需注意运行时写回与版本控制边界。

### schema/config

关键文件：

- `config/w1_match_card_schema.json`
- `config/w1_decision_policy.json`
- `config/w1_ledger_schema.json`

职责：

- 约束 match card；
- 定义 W1_PLAY_GUARD_V1；
- 定义 ledger 字段；
- 支撑 checker 验收。

### checker

关键 checker：

- `scripts/check_w1_click_to_predict.py`
- `scripts/check_w1_dashboard_data_binding.py`
- `scripts/check_w1_visual_dashboard.py`
- `scripts/check_w1_weather_integration.py`
- `scripts/check_w1_production_lite.py`
- `scripts/check_w1_post_match_calibration.py`

checker 当前是主要质量门槛，但还不是完整测试体系。

## 4. 数据链路

点击 dashboard “开始预测”后的 10 步：

1. 初始化比赛；
2. 实时请求赔率；
3. 实时请求首发；
4. 实时请求裁判/fixture detail；
5. 实时请求伤停/停赛；
6. 实时请求天气；
7. 写入 runtime/match card；
8. 重算 `data_quality` / `lineup_effect` / `tactical_effect` / `score_distribution` / `play_guard`；
9. 重建 `dashboard_data`；
10. 展示进度和结果。

当前实现的重要点：

- fixture_id 优先，禁止在 fixture_id 存在时用队名模糊匹配覆盖；
- 每个模块记录 `source/status/fetched_at/message_cn`；
- 实时失败时允许 cache 或 verified_fallback，但必须明示来源；
- dashboard 显示“本次实时刷新”，不只显示“查询完成”。

## 5. 数据源与字段

### API-Football

用于：

- fixture；
- odds；
- lineups；
- injuries；
- referee / fixture detail。

当前实现风险：

- odds、injuries、referee 的实时成功率仍需更多真实点击样本验证；
- 不同 endpoint 的返回为空时，当前降级为 cache/missing；
- 未建立完整 retry、TTL、source confidence 体系。

### Open-Meteo

用于：

- 赛时天气；
- 温度；
- 湿度；
- 风速；
- 降雨概率/降雨量。

特点：

- 免费；
- 不需要接口凭据；
- 已接入 click-to-predict 流程；
- 当前天气只作为环境风险，不作为 W1_PLAY 硬阻断。

### 静态 venue mapping

路径：`data/static/world_cup_2026_venues.json`

用于：

- 场馆名；
- 城市；
- 国家；
- 经纬度；
- 海拔；
- 屋顶状态；
- 时区。

### 本地 match cards

用于：

- 保存基础 fixture；
- 保存市场与上下文；
- 保存首发、阵型、风险、缺口；
- 承载 runtime 写回。

### live_refresh 字段

结构含义：

- `source`：`live_api` / `cache` / `fallback` / `verified_fallback` / `missing`
- `status`：`success` / `empty` / `error` / `skipped`
- `fetched_at`：本次请求时间；
- `message_cn`：中文说明。

区别：

- `live_api`：本次点击实际请求后端接口成功；
- `cache`：实时失败或未配置时使用本地已有数据；
- `verified_fallback`：人工核验样本作为兜底；
- `missing`：本次没有可用数据；
- fallback/cache 不能显示成实时成功。

## 6. 已实现核心模块

### W1_PRODUCTION_LITE

最小正式赛前分析入口。定义 match card、decision policy、ledger schema、sample card、checker 和硬风控边界。

### PLAY_GUARD_V1

量化 W1_PLAY 准入：

- confirmed lineup 必须存在；
- odds/AH/OU 必须齐全；
- blocking data gaps 必须为 0；
- risk flags 数量受限；
- market signal 与 supporting/counter factors 必须达到门槛；
- W1_PLAY 必须 ledger_required。

当前状态：PLAY_GUARD 是硬风控，不应被早盘参考、天气、比分池或外部参考比分绕过。

### Dashboard data binding

dashboard 主面板统一读取 `match_records` 富数据，不再使用 group fixture 基础索引作为展示来源。

### Click-to-Predict

本地按钮触发后端流程，显示查询进度并刷新 dashboard 数据。

### Live API on click refresh

每次点击都尝试实时请求赔率、首发、裁判、伤停和天气；cache/fallback 明确标注。

### Weather integration

通过 Open-Meteo 接入天气，生成 environment_context。

### Environment context

包括：

- 球场；
- 城市；
- 天气；
- 温度；
- 湿度；
- 风速；
- 降雨；
- 海拔；
- 屋顶；
- 环境风险；
- 中文解读。

### Lineup effect

首发出来后评估：

- 阵型；
- 核心缺席；
- 轮换风险；
- 进攻、防守、中场、转换速度、定位球、压迫强度；
- 是否需要重算参考倾向。

### Tactical effect

根据阵型和球员位置生成战术标签：

- 4-3-3：边路速度、高位压迫、转换进攻；
- 4-2-3-1：中路组织、前腰串联、攻守平衡；
- 3/5 后卫体系：防守优先、翼卫推进、反击；
- 并输出对位影响和是否重算参考倾向。

### Score distribution

用比分池替代单比分：

- 主比分；
- 防平比分；
- 优势扩大；
- 打开局；
- 强队打穿；
- 防线崩盘。

当前是规则池，不是经历史样本统计校准后的概率模型。

### Game open trigger

识别比赛是否可能被打开：

- early goal risk；
- transition chaos risk；
- defensive collapse risk；
- red card / penalty risk；
- triggered 后必须重估。

### Market vs score risk

明确盘口与比分不是直接映射：

- 深让不等于大胜；
- 平手盘也可能打开；
- 大小球不直接决定比分；
- favorite win 与 cover 不能混用。

### Post-match calibration

对已完赛比赛自动写入实际比分，计算：

- `main_hit`
- `pool_hit`
- `miss`
- `待复盘`

并生成 miss_reason_tags 与 lesson_cn。当前样本：

- Qatar vs Switzerland：1-1；
- USA vs Paraguay：4-1。

## 7. 决策逻辑说明

### 为什么首发重要

首发决定阵型、核心球员是否在场、轮换比例和战术执行方式。没有 confirmed lineup 时，系统不能判断真实阵型、主力强度、攻防平衡和关键球员缺席，因此 W1_PLAY 被硬阻断。

### 为什么裁判重要

裁判影响比赛节奏、中断频率、牌风险、点球/VAR 可能性。偏严裁判可能提升红牌、点球和比赛打开风险。当前裁判仍主要作为辅助风险，没有进入 PLAY_GUARD 硬阻断。

### 为什么天气/场地重要

高温、高湿、大风、降雨、海拔和屋顶状态会影响体能、传控质量、射门质量和转换速度。当前天气/场地作为 context/risk，不直接触发 W1_PLAY。

### 为什么盘口不能直接等于比分

AH 表达的是市场让步和资金/信息均衡，不等于真实胜差。深让可能来自名气、市场偏好或不对称风险，但比赛仍可能因为节奏、首发、红牌或临场表现走向小胜甚至平局。

### 为什么需要比分池

单比分容易过拟合和误导。比分池可以同时表达主路径、防平路径、打开局路径和极端路径，并在赛后校准时判断命中的是主路径还是备用路径。

### 为什么深让不等于大胜

Qatar vs Switzerland 样本说明，深让方向可能无法转化为实际胜差。favorite win 与 cover 是两类不同事件，不能混用。

### 为什么平手盘也可能打开

USA vs Paraguay 样本说明，平手盘不代表低波动。一旦早球、转换混乱或防线连续失位出现，比分可能快速放大。

### 为什么 OU 不直接锁死比分

OU 是总进球市场先验，不是比分上限。OU 2/2.5 只能降低大比分初始权重，不能排除 3-1、4-1 等打开局路径。

## 8. 复盘样本

### Qatar vs Switzerland

赛前特征：

- 瑞士深让；
- 市场容易把强弱关系误读为大胜路径；
- 实际结果：1-1。

复盘结论：

- favorite win / cover 不能混用；
- 深让不等于大胜；
- 1-1 应进入反证样本；
- favorite_win_but_not_cover_risk 需要保留。

### USA vs Paraguay

赛前特征：

- 平手盘；
- OU 2/2.5；
- 实际结果：4-1。

复盘结论：

- 平手盘也可能打开；
- OU 低位不能直接限制大比分；
- open-game trigger 需要提高权重；
- 3-1、4-1 路径不能被过早压低到不可见。

### Brazil vs Morocco

赛前样例：

- 当前仍是未赛样例；
- 不能只输出单比分；
- 1-0 / 2-0 / 2-1 / 3-1 / 4-1 应作为路径集合；
- 每条路径应有触发条件，例如早球、边路速度、反击、翼卫压上、防线崩盘。

## 9. 当前系统优点

- 数据源分层清楚，fixture、market、lineup、weather、venue、card、ledger 各有边界；
- live API 与 fallback 明确区分，避免伪装实时成功；
- dashboard 可解释性较强，能展示数据质量、风险、缺口和路径；
- checker 覆盖了主要工作流；
- 明确禁止投注承诺和资金建议；
- runtime 与代码边界较清晰；
- fixture_id 优先降低了点错比赛后查错数据的风险；
- post-match calibration 已开始把赛果反馈进比分路径。

## 10. 当前主要缺陷

- 真实模型权重仍偏规则化；
- 样本量不足；
- 缺少历史回测；
- score_distribution 目前是规则池，不是统计校准概率；
- 裁判历史尺度未量化；
- 球员能力和位置影响缺少外部评分源；
- 赔率快照/盘口变化没有充分时间序列建模；
- fallback 仍可能影响“实时感知”；
- 没有 CI/CD；
- 无 remote 备份；
- `src/` 与 `tests/` 目录为空；
- dashboard HTML 内嵌数据较大，长期可维护性一般；
- runtime match card 写回与版本控制边界仍需制度化；
- 当前 checker 不能替代单元测试、回归测试和端到端测试。

## 11. 专家重点评审问题

- 比分池权重如何校准？
- AH/OU 如何转成胜差/总进球先验？
- 首发战术标签是否足够？
- 裁判是否应该进入风控？
- open trigger 的阈值如何定？
- post-match calibration 如何避免过拟合？
- fallback 数据如何降权？
- 是否需要 Poisson / xG / Elo / market implied probability 组合？
- 球员评分源如何接入，如何处理国家队样本稀疏？
- 盘口时间序列应该按多少窗口切片？
- 早盘参考与正式判断是否需要不同模型权重？
- scoreboard 与 ledger 的赛后回写如何防止人工覆盖误差？

## 12. 下一阶段优化建议

### P0 GitHub 独立远程备份

建立独立远程仓库，保护当前工作成果。推送前必须确认不包含 runtime、日志、状态文件和任何凭据。

### P1 历史样本回测与 calibration

建立历史世界杯/国际比赛样本，评估方向、比分池、open trigger、AH/OU 先验与实际结果的偏差。

### P2 AH/OU 转 score prior

把 AH、OU、1X2 implied probability 转成比分先验，不再仅用规则池。

### P3 球员评分/阵型识别增强

接入球员能力、位置、俱乐部出场、国家队角色等评分源，增强首发效应判断。

### P4 裁判历史尺度量化

建立裁判黄牌、红牌、点球、VAR、中断频率样本，纳入 game_open_trigger。

### P5 API retry/cache TTL/source confidence

为每个数据源加入 TTL、重试策略、source confidence 和降权规则。

### P6 CI + tests

建立单元测试、端到端测试和静态检查，避免仅依赖脚本 checker。

### P7 专家审阅后的规则冻结

专家评审后冻结一版规则，避免赛中临时频繁修改导致不可复盘。

## 13. 风险控制与合规

- 不输出投注、下注、资金建议；
- 不承诺命中；
- 不把早盘参考写成最终结论；
- 接口凭据仅由后端环境变量读取；
- 前端不展示任何凭据；
- push 前需要确认；
- fallback/cache 必须明示；
- W1_PLAY 必须通过 PLAY_GUARD，不得被参考比分或外部样本绕过。

## 14. 附录

### 关键文件清单

- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `reports/dashboard/assets/w1_dashboard_data.json`
- `scripts/w1_local_predict_server.py`
- `scripts/build_w1_dashboard_data.py`
- `scripts/w1_weather_client.py`
- `scripts/w1_watcher.sh`
- `config/w1_match_card_schema.json`
- `config/w1_decision_policy.json`
- `config/w1_ledger_schema.json`
- `data/processed/match_cards/group_stage_round1/`
- `data/static/world_cup_2026_venues.json`
- `state/w1_predict_progress.json`
- `state/w1_live_refresh_state.json`
- `state/w1_weather_cache.json`

### checker 清单

- `python3 scripts/check_w1_post_match_calibration.py`
- `python3 scripts/check_w1_click_to_predict.py`
- `python3 scripts/check_w1_dashboard_data_binding.py`
- `python3 scripts/check_w1_visual_dashboard.py`
- `python3 scripts/check_w1_weather_integration.py`
- `python3 scripts/check_w1_production_lite.py`

### 当前 runtime WARN_ONLY

- `reports/dashboard/assets/w1_dashboard_data.json` 会随 build 和点击预测变化；
- `state/` 下 progress、refresh、weather、live refresh 会随本地服务变化；
- logs 不应提交；
- snapshot 新文件需要单独审计后再决定是否纳入版本控制；
- runtime match card 写回需要与 schema/sample 区分。

### known BLOCKER

none
