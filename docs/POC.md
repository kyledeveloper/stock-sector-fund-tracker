# Phase 0 — 数据源 PoC 报告（2026-10-01）

> 方法：curl/HTTP 探测 + 页面结构验证 + robots/ToS 检查。
> 本机 egress 经代理出口，部分站点（SEC）按 IP 拦截，结论中已注明环境相关项。

## go/no-go 总表

| # | 数据源 | 模块 | 结论 | 备注 |
|---|--------|------|------|------|
| 1 | ETF.com 免费页 | M1 | ⛔ NO-GO（主源证伪） | 免费页仅全市场 Top 10 申购/赎回榜，无 11 只板块 ETF 逐日流 |
| 1b | ETF.com 个股页 fund-flow 接口 | M1 | ⛔ NO-GO | 个股 Fund Flows tab 需登录才渲染数据，无公开 XHR（浏览器实测 2026-10-01） |
| 1c | ETFdb 免费页 | M1 | ⚠️ 仅汇总口径 | 仅 5日/1月/3月…净流入汇总（如 XLK 5日 +313.85M），无逐日序列 |
| 1d | stockanalysis 免费页 | M1 | ⛔ NO-GO | `/etf/xlk/` 静态 HTML 无 fund-flow 数据 |
| 2 | SSGA 官方每日持仓 XLSX | M2 | ✅ GO | 200 + 可解析，T-1 口径已确认 |
| 3 | Yahoo chart API（EOD） | M3 | ✅ GO | 64 根日 K（含当日），无 key；Tiingo 为备选（需免费注册 token） |
| 4 | CBOE 每日 put/call | M5 | ✅ GO | 服务端渲染 HTML，`?dt=` 切日期，无需登录 |
| 5 | SEC EDGAR | M4 | ⚠️ 条件 GO | 本机 egress IP 被 SEC 拦截（403）；代码层合规已就绪，部署 VPS 上需复验 |

## 逐项记录

### 1. ETF.com（M1）— NO-GO（$0 路线已穷尽）
- `https://www.etf.com/robots.txt`：`User-agent: *` 下无 blanket Disallow（`#Disallow: /` 被注释），抓取不违反 robots。
- 但免费每日页面只发布全市场 Top 10 creations + Top 10 redemptions（红队 2026-10-01 已实测多日页面结构）。
- 后果：XLU/XLRE/XLC 等多数日子不上榜 → 静默数据缺口。**禁止**拿 Top-10 当全量用。
- 个股页（如 `/xlk`）的 Fund Flows tab 需登录才渲染数据（浏览器实测 2026-10-01，3 次点击均弹登录框），
  无公开 XHR 可抓 → $0 无认证路线证伪。
- ETFdb 免费页（`etfdb.com/etf/XLK/`）仅提供 5日/1月/3月…净流入**汇总**（如 5日 +313.85M），无逐日序列。
- stockanalysis 免费页（`/etf/xlk/`）静态 HTML 无 fund-flow 数据。

**M1 结论：$0 无认证条件下，不存在 11 只板块 ETF 的逐日资金流数据源 → M1 按原设计 NO-GO。**
备选（需用户决策）：
- A. M1 面板改用 ETFdb **近5日净流入**（每日更新、5日窗口），诚实标注口径；用其日变化做伪动量。
- B. 从份额变化推导日流（需每日 shares outstanding 源，暂未找到 $0 可靠源）。
- C. 付费数据（违背 $0 约束）。
- D. v1 砍掉 M1，用 M2（持仓敞口）+ M3（动量）讲板块轮动故事。
推荐 A（保留产品 headline 数字，口径诚实），但决定权在用户。

### 2. SSGA 持仓（M2）— GO
- `https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xlk.xlsx`
  → 200，`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，22KB。
- openpyxl 解析验证：sheet `holdings`，表头 `(Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency)`，
  文件标注 `As of 30-Sep-2026`（当日 10-01 → **T-1 口径确认**）。
- 官方源，免费，无 ToS 风险。11 只 ticker 套用同一 URL 模式。

### 3. EOD 行情（M3）— GO（Yahoo 主，Tiingo 备）
- `https://query1.finance.yahoo.com/v8/finance/chart/XLK?interval=1d&range=3mo`
  → 200，64 根日 K，最后一根 2026-10-01（当日）。12 个标的 × 90 天回填 ≈ 12 个请求。
- 非官方接口（ToS 灰色地带，广泛使用但可能变更）；**备选 Tiingo** 免费 tier 需注册 token（500 symbols/月，12 个标的够用）。
- Finnhub 免费 tier 的 `/stock/candle` 稳定 403 —— 已排除，不再考虑。

### 4. CBOE put/call（M5）— GO
- 真实地址（旧 `/us/options/market_statistics/daily/` 已迁移）：
  `https://www.cboe.com/markets/us/options/market-statistics/daily?dt=YYYY-MM-DD`
  省略 `dt` 返回最近交易日。curl 验证：200，447KB HTML，内嵌 `"TOTAL PUT/CALL RATIO","value":"0.88"`。
- 无公开 JSON XHR（Next.js 服务端渲染 + RSC），采集方式 = **解析服务端渲染 HTML 表格**，无需登录、无反爬迹象。
- 口径：TOTAL / INDEX / EQUITY / VIX / ETP 五个比率（页面文本抓取已验证数值）。

### 5. EDGAR（M4）— 条件 GO
- `curl -A "us-moneyflow/0.1 (+...)" https://data.sec.gov/submissions/CIK0001067983.json` → UA 发送正确，但返回 403（SEC 按 egress IP 拦截自动化工具；`www.sec.gov` 同样 403）。
- 代码层已合规：`common/http.py` 强制描述性 UA、可配置限流（默认 0.5s 间隔，远低于 SEC 10 req/s 上限）。
- **部署到用户 VPS 后必须复验**（Phase 4 DoD 的一部分）；若 VPS IP 同样被拦，备选：SEC 公司概念 API 同源、或延迟到 Phase 5 用浏览器任务中转。

## 待办（阻塞 Phase 1 开工）
- [x] 浏览器任务返回：CBOE put/call 真实地址 → GO（服务端渲染 HTML + `?dt=`）
- [x] M1 数据源穷尽验证 → NO-GO（$0），备选 A–D 待用户决策
- [ ] 红队审查 Phase 0
- [ ] 用户 VPS 部署后：复验 EDGAR 可达性
