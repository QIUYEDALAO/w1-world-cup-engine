# W1 可视化 Dashboard V2 中文老板版

**入口:** `reports/dashboard/W1_VISUAL_DASHBOARD.html`  
**数据:** `reports/dashboard/assets/w1_dashboard_data.json`

## 定位

W1_VISUAL_DASHBOARD_V2 是给老板直接查看的中文静态总控台。页面可以直接双击打开，不需要 Web 服务，不调用外部 API。

## 第一屏信息

- 当前结论：全部等待首发/裁判等关键数据
- 第一场：墨西哥 vs 南非
- 正式判断时间：2026-06-12 02:00 / 02:30 CST
- 现在动作：等待，不下结论

## 页面模块

- 顶部状态卡：等待数据、观察中、可正式分析、跳过
- 运行信息：刷新器版本、风控规则、下次刷新
- 世界杯小组总览：A组到L组，每组4队
- 晋级规则：每组前2名直接晋级，成绩最好的8个小组第三晋级，共32队进入淘汰赛
- 首场比赛卡：比赛时间、当前状态、首发、裁判、赔率、风控是否通过、下一次刷新
- 小组积分榜模板
- 小组第三排名模板
- 报告入口

## 校验

```bash
python3 scripts/check_w1_visual_dashboard.py
```

预期输出：

```text
W1 visual dashboard self-test PASS
```
