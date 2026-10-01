# Phase 0 — 数据源 PoC 报告（2026-10-01）

> 方法：curl/HTTP 探测 + 页面结构验证 + robots/ToS 检查。
> 本机 egress 经代理出口，部分站点（SEC）按 IP 拦截，结论中已注明环境相关项。

## go/no-go 总表

| # | 数据源 | 模块 | 结论 | 备注 |
|---|--------|------|------|------|
| 1 | ETF.com 免费页 | M1 | ⛔ NO-GO（主源证伪） | 免费页仅全市场 Top 10 申购/赎回榜，无 11 只板块 ETF 逐日流 |
| 1b | ETF.com 个股页 fund-flow 接口 | M1 | ⏳ 待定 | 已派浏览器任务抓 XHR 接口；若找到则 GO |
| 2 | SSGA 官方每日持仓 XLSX | M2 | ✅ GO | 200 + 可解析，T-1 口径已确认 |
| 3 | Yahoo chart API（EOD） | M3 | ✅ GO | 64 根日 K（含当日），无 key；Tiingo 为备选（需免费注册 token） |
| 4 | CBOE 每日 put/call | M5 | ⏳ 待定 | 页面有数据但 curl 抓不到（JS 渲染）；已派浏览器任务抓 XHR 接口 |
| 5 | SEC EDGAR | M4 | ⚠️ 条件 GO | 本机 egress IP 被 SEC 拦截（403）；代码层合规已就绪，部署 VPS 上需复验 |

## 逐项记录

### 1. ETF.com（M1）— NO-GO
- `https://www.etf.com/robots.txt`：`User-agent: *` 下无 blanket Disallow（`#Disallow: /` 被注释），抓取不违反 robots。
- 但免费每日页面只发布全市场 Top 10 creations + Top 10 redemptions（红队 2026-10-01 已实测多日页面结构）。
- 后果：XLU/XLRE/XLC 等多数日子不上榜 → 静默数据缺口。**禁止**拿 Top-10 当全量用。
- 待定：个股页（如 `/xlk`）的 fund-flow 历史走哪个 XHR 接口。浏览器任务进行中。

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

### 4. CBOE put/call（M5）— 待定
- 页面 `https://www.cboe.com/us/options/market_statistics/daily/` 有 TOTAL(0.88)/INDEX(1.03)/EQUITY(0.53) 等比率（文本抓取验证）。
- curl 直接取页面拿不到表格（Next.js 客户端渲染）；旧 CSV 路径（`/publish/scheduledtask/...`）已 404，CDN 猜测路径 403。
- 浏览器任务抓 XHR 接口中。拿到接口则 GO，否则降级为"页面文本解析"（需浏览器渲染，不适合 cron）或 M5 推迟。

### 5. EDGAR（M4）— 条件 GO
- `curl -A "us-moneyflow/0.1 (+...)" https://data.sec.gov/submissions/CIK0001067983.json` → UA 发送正确，但返回 403（SEC 按 egress IP 拦截自动化工具；`www.sec.gov` 同样 403）。
- 代码层已合规：`common/http.py` 强制描述性 UA、可配置限流（默认 0.5s 间隔，远低于 SEC 10 req/s 上限）。
- **部署到用户 VPS 后必须复验**（Phase 4 DoD 的一部分）；若 VPS IP 同样被拦，备选：SEC 公司概念 API 同源、或延迟到 Phase 5 用浏览器任务中转。

## 待办（阻塞 Phase 1 开工）
- [ ] 浏览器任务返回：ETF.com 个股 fund-flow XHR 接口 → 决定 M1 最终源
- [ ] 浏览器任务返回：CBOE put/call XHR 接口 → 决定 M5 采集方式
- [ ] 用户 VPS 部署后：复验 EDGAR 可达性
