# W1 World Cup Engine

世界杯专用独立系统。完全隔离 V3/V4/M1。

## 地位

- W1 是世界杯专用系统，不继承旧 V3 作为主系统。
- M1 只作为市场研究资产参考，不介入 W1 评分/推荐。
- 本仓库不与任何旧系统共享数据、代码或配置。

## 当前阶段

仅进行：
- 数据源审计（检查可用世界杯数据的完整性）
- 蓝图设计（系统架构、评分模型框架、验证流程）

禁止：
- 生成推荐
- 写 official
- 写 pending
- 推 QQ
- 修改任何旧系统（V3/V4/M1）

## 目录结构

```
w1_world_cup_engine/
  README.md          ← 本文件
  docs/              蓝图设计、设计文档
  config/            配置文件、schema
  data/
    raw/             原始下载数据
    processed/       清洗后数据
    snapshots/       数据快照/备份
  src/               源代码
  scripts/           工具脚本
  tests/             测试
  reports/
    data_audit/      数据源审计报告
    match_previews/  比赛前瞻（仅研究用途）
    ledger/          操作日志
```

## 纪律

- 不改 V3/V4/M1 任何文件。
- 不移动旧数据到本目录。
- 不写业务推荐逻辑。
- 不做 QQ 推送。
- git init 但不配置 remote，不 push。
