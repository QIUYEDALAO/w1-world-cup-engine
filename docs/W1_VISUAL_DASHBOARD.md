# W1 可视化 Dashboard 中文预测总控台

**入口:** `reports/dashboard/W1_VISUAL_DASHBOARD.html`  
**数据:** `reports/dashboard/assets/w1_dashboard_data.json`

## 定位

W1_VISUAL_DASHBOARD 是给老板直接查看的中文静态总控台。页面可以直接双击打开，不需要 Web 服务，不调用外部 API。

本版复用公开项目 `worldcup2026-prediction-skill` 的中文 UI 与解释风格，但底层仍完全使用 W1：watcher v2、W1_PLAY_GUARD_V1、match cards、ledger、odds_movement、supporting_factors / counter_factors 与 dashboard_data.json。

## 第一屏信息

- 当前状态：24 场等待关键数据
- 第一场：墨西哥 vs 南非
- 参考倾向：墨西哥不败
- 参考比分：2-0 / 2-1
- 当前动作：等待正式首发，不下最终结论
- 正式判断：6月12日 02:00 / 02:30 CST
- 说明：参考比分只作为外部参考，不绕过 W1 风控

## 页面模块

- 顶部老板视角：当前状态、第一场、参考倾向、参考比分、当前动作、正式判断
- 状态卡：等待数据、观察中、可正式分析、跳过
- 首场比赛卡：比赛、开赛时间、当前结论、参考比分、风险等级、支持理由、反对理由、关键缺口、当前动作、是否通过 W1 风控
- 技术详情：默认折叠，只在展开后显示 raw decision、play_guard_pass、lineup_status、referee_status、odds_movement 等字段
- 世界杯小组总览：A组到L组，每组4队，展示当前赛前积分小表
- 晋级规则：每组前2名直接晋级，成绩最好的8个小组第三晋级，共32队进入淘汰赛
- 晋级路径：每组第1名、第2名、第3名若晋级后的32强席位与潜在对手
- 报告入口

## 边界

页面可以展示参考倾向和参考比分，但它们不是 W1 正式结论。W1_PLAY 仍必须通过 W1_PLAY_GUARD_V1；只要 confirmed_lineup 等关键数据缺失，页面必须保持等待数据。

页面不提供投注、下注、资金或收益建议，也不接入接口密钥教程、聊天群自动化或付费社群。

## 晋级路径说明

页面展示的是 32 强赛程席位，不是赛果预测。每组前2名的对阵席位可以直接列出；小组第三的具体对阵要等 12 个小组第三中哪 8 队晋级后才能确定，因此页面展示候选对手范围。

## 校验

```bash
python3 scripts/check_w1_visual_dashboard.py
```

预期输出：

```text
W1 visual dashboard self-test PASS
```
