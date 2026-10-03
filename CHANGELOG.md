# CHANGELOG

## 第三方代码审阅修复（2026-10-02）

6 项审阅结论中 4.5 项经逐条核实成立，已修复（RED 回归测试先行）：

### 修复
- **H1 — 13F 修正案生效**：同季度 13F-HR/A 曾因 `report_date` 相同被永久跳过。现比较 `filing_date`：修正案更新时先抓取、成功后再 `delete_quarter` + upsert 整季度替换（被删除的仓位不再残留；抓取失败不删旧数据）。
- **M1 — Form 4 小数股数**：`transactionShares` 曾用 `int()`，小数（DRIP/拆股）导致整份 filing 被丢弃。现解析为 `float`（`InsiderTransaction.shares` / `InsiderBuyView.shares` 同步改为 float；SQLite 列 affinity 兼容，无需 migration）；非数字仍 fail-loud。
- **M2 — Yahoo 单根 adjclose 为 null**：曾静默回退到 raw close，混用复权/未复权价格。现该情形直接 `ValueError`（与 blocker-1 的 fail-loud 一致）；adj 整体缺失（全 raw 序列）与双 null（非交易日补位行丢弃）行为不变。
- **前端金额 `$0K`**：`Form4Panel` 的 `fmtMoney` 对 <$1000 显示 `$0K`/`$1K`。现 <$1000 显示原值美元。
- **H2 — Form 4 全失败仍标 fresh**：EFTS 搜索成功但所有 filing 抓取失败时，曾无条件 `mark("m4")`。现 `errors` 非空且 `fetched == 0` 时只 `touch()`（stale）；部分成功与静默日（scanned == 0）仍正常 mark。`run-all` 输出的 `m4 ok` 后追加错误计数，不再掩盖 per-filing 错误。
- **M3 — 13F 同 CUSIP+putCall 多行**：`parse_13f_infotable` 现按 `(cusip, put_call)` 聚合（value/shares 求和），不再 last-write-wins 丢金额。

### 不成立
- "CBOE 缺交易日会被前后两天连线"：`PutCallPanel` 已设 `connectNulls: false`，描述的 bug 不存在。

## Phase 4 — M5 期权情绪 + hardening + 部署（2026-10-02）

### 新增
- **M5 CBOE put/call ratio**：每日抓取 CBOE 公开市场统计页（服务端渲染 HTML 解析），存 90 天滚动历史（`cboe_putcall` 表：trade_date / total / equity / index）。
  - 纯函数 `parse_cboe_daily(html, trade_date)`：golden fixture 契约测试；周末/节假日无数据页返回 None（跳过不写）；缺行、`--`、小数点错位一律 fail-loud，绝不写脏数据。
  - CLI：`m5`（T+1：交易日抓上一交易日）、`backfill-m5`（90 天串行回填，间隔 ≥2s，upsert 幂等）。
  - API：`GET /api/v1/sentiment/putcall?days=90`（days clamp 1..365）+ freshness 元数据。
  - 前端 Put/Call 面板：ECharts 双线（total/equity）+ 0.7 参考线，中英双语，CBOE 延迟展示诚实文案。
- **部署**：`docs/DEPLOY.md`（systemd timer 每日 15:05 PDT 跑 `run-all`、SQLite WAL、备份、迁移步骤、冒烟清单）。

### Hardening
- M5 接入 freshness watchdog（T+2 stale 灰化，与其他模块一致）。
- 全量测试 / ruff / React build / 架构检查通过；独立红队签字 GO。

### 合规备注
- CBOE robots.txt 不禁 daily 页；抓取策略：每日单请求、诚实 UA、间隔 ≥2s、不分发原始 HTML、面板只展示聚合比率。

## Phase 3 — M4 机构与内幕（2026-10-02）
- 12 家机构 13F-HR 观察名单：季度拉取 + QoQ diff（new/increased/decreased/exited），首季黄色提示。
- 全市场 Form 4 每日扫描：非衍生品交易解析、10b5-1/修正案/联合申报标注。
- 红队修复：交易主键改 `(accession_number, ordinal)`、毒 filing 隔离、4/A 标注、联合申报全 owner 解析、cover-only 13F 回退、EFTS 分页 fail-loud。
- 110 tests passed；红队 verdict GO。

## Phase 2 — M3 板块动量（2026-10-01）
- Yahoo EOD（Tiingo 为 fallback）：11 行业 ETF vs SPY 的 20/60 日超额收益 + 简化 RRG。
- 修复 partial adjclose 混用、重复 timestamp 等静默数据损坏；红队 GO。

## 双语基建（2026-10-01）
- 全产品中英双语：`web/src/i18n/dict.ts` + `LangContext.tsx`，TS type-lock，后端语言中立。

## Phase 1 — M2 持仓敞口快照（2026-10-01）
- SSGA 官方 holdings → 跨板块股票持仓敞口快照。"持仓快照、非资金流；权重日变化主要来自价格波动。"
- 红队 GO。
