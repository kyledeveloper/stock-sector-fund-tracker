# REDTEAM — Phase 0 独立审查（2026-10-01）

审查人：红队子代理（批判视角）→ 蓝队已修复 → 本文件为最终记录。

## 总 verdict：CONDITIONAL → 修复后 GO（附 M1 待用户决策）

三处 blocker 已在 Phase 0 内修复并回归测试通过；major 已排入 Phase 1–4 计划；
M1 数据源经 A/B/C/D/E/F 评估后，**用户决策 D（2026-10-01）：v1 砍掉 M1**；
M2 重定义为持仓敞口快照，阶段重排为 4 个。

---

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | `store/migrate.py` 把多语句 SQL 传给单语句 executor，`ProgrammingError`；零测试 | 引号/注释感知的 `_split_statements` 逐条执行 | `tests/unit/test_migration.py`：真实迁移 apply 两次（2 个文件、8 张表），第二次返回 0 |
| B2 | 架构测试对相对导入 `pass` 忽略，`from ..store import x` 可走私 | `_resolve_relative_import` 解析为绝对包名再查 ALLOWED 表 | `test_relative_imports_are_resolved` 回归测试 |
| B3 | 前端 Panel 消费 freshness，后端无接口吐 freshness | 新增 `GET /api/v1/freshness`（Phase 0 stub：5 模块全 stale） | `test_api_freshness.py` 锁死前后端形状 |

修复中附带发现：`001_init.sql` 漏了 `sector_momentum` 表 → 按"一变更一文件"约定补 `002_sector_momentum.sql`。

## 🟠 Major（Phase 1 计划内排期）

- **M5** CBOE robots/ToS 未验证 → Phase 4 开工前补查 `cboe.com/robots.txt` + 条款并记录；
  Phase 4 加 HTML fixture parser 契约测试。
- **M2** ~~ETFdb 5日汇总只采过一次快照~~ → n/a（M1 已砍，ETFdb 路线作废）。
- **M3** 真实 payload 零存档 → Phase 1 第一个 parser 契约测试起，SSGA XLSX / CBOE HTML / Yahoo JSON 存 `tests/fixtures/` 做 golden fixture。
- **M4** 周末/节假日行为 → PLAN 已加入"非交易日跳过写入"规则；Phase 1 实现 `trading_day` helper。
- **M5** Yahoo 当日未收盘 bar → PLAN 已记：EOD adapter 必须丢弃未完成 bar（Phase 2）。
- **M6** EDGAR → 已关闭：第二出口实测 **HTTP 200**，证实 403 是本机 egress IP 问题。
  VPS 部署后复验一次即可（Phase 3 DoD）。
- **M7** PLAN 与 ALLOWED 表矛盾 → 已收紧为 PLAN 口径：`compute` 仅依赖 `models`（`ingest` 保留 `common` 给共享 HTTP 客户端，测试与 PLAN 已对齐）。

## 🟡 Minor（状态）

- m1 `_package_of` 恒等三元 → 已清理；m2 scope 补 `vix`/`etp`（前后端同步）；
  m3 `checked_at: str` → `datetime`（API 序列化为 ISO 字符串，前端保持 string 镜像）；
  m4 systemd 硬编码 `/home/hatch` → 改为 `%h` 用户级 unit 模板；
  m5 `npm run build` → 已验证通过（tsc + vite，32 modules）；
  m6 11 只 SSGA URL → 全部 200；
  m7 vcrpy/freezegun 零使用 → Phase 1 parser 契约测试起必须用起来，否则从依赖移除；
  m8 `types.ts` 手写镜像 → 第一个真实接口（Phase 1）起加 CI 对拍或转 OpenAPI 生成。

## M1 数据源最终评估

| 选项 | 结论 |
|------|------|
| ETF.com 免费 Top-10 | ❌ 证伪：只有全市场榜，无 11 只逐日流 |
| ETF.com 个股页 | ❌ 证伪：Fund Flows tab 登录墙，无公开 XHR |
| ETFdb 免费页 | ⚠️ 仅 5日/1月…汇总，无逐日序列 → 备选 A |
| stockanalysis | ❌ 免费页无 fund-flow 数据 |
| Nasdaq 免费 API（E spike） | ❌ `api/quote/XLK/info` 无 flow/shares 字段 |
| SSGA 同目录 shares outstanding（F spike） | ❌ 目录无 listing |
| B（份额推导） | 源不存在，不可 commit |
| C（付费） | 违反 $0 约束，死选项 |

**用户决策（2026-10-01）：D。v1 砍掉 M1。** M2 重定义为持仓敞口快照（原"持仓×板块流"
公式失效），阶段重排为 Phase 1–4。`sector_flow` 表由 `003_drop_m1.sql` 移除。

---

# REDTEAM — Phase 1（M2 持仓敞口面板）独立审查（2026-10-01）

审查人：独立红队子代理（只读，未改任何文件）→ 蓝队修复 → 本节为最终记录。

## 总 verdict：CONDITIONAL → blocker 修复后 GO

2 个 blocker 均为**静默数据损坏路径**（无日志无告警），已按 fail-loud 原则修复并回归；
5 个 major 同批修复；minor 部分修复、部分排期。

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | 11 只 ETF 的 as_of 不一致时被 `Counter.most_common` 多数投票掩盖；滞后文件旧持仓混入快照，`holding` 与 `stock_exposure` 两表口径不一致，全程无告警（`services/m2.py:15-16`） | 删除 `_mode_as_of`；新增 `_validate_batch`：batch 内 as_of 不完全一致 → `ValueError` 列出各 ETF 日期，写入前 fail-loud（面板按现有机制置灰） | `test_run_m2_rejects_mixed_as_of_dates`：混入 9/29 滞后文件 → raise，且两表零写入 |
| B2 | "权重加总≈100%" 不变量只在 golden fixture 测试里，pipeline 运行时无门；SSGA 若把权重列从百分比改成小数（Σ≈0.01），Pydantic 照样通过（`le=1`），静默入库（`services/m2.py` 无运行时校验） | `_validate_batch` 加运行时门：每只 ETF Σweight ∈ [0.95, 1.05]，否则 raise（fail-loud → 置灰） | `test_run_m2_rejects_weight_sum_drift`：模拟 percent→fraction 漂移 → raise，零写入 |

## 🟠 Major（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| M1 | `_fetch_all` 单文件 404 拖垮全部 11 只；all-or-nothing 策略无测试锁定（将来改成"能写几只写几只"会悄悄制造 B1 同类问题） | 策略不变（fail-loud-all 正确），加测试 pin 住 | `test_fetch_failure_writes_nothing`：mock `_fetch_all` 抛错 → 异常向上传播，两表零写入 |
| M2 | 前端 freshness fail-open：`/freshness` 500 而 `/exposure` 仍有旧数据时，面板全透明度展示旧数字、只写 "no data yet"，无置灰无 STALE（`Panel.tsx:17`） | `Panel` 新增 `hasData` prop：`freshness === null && hasData` → 按 stale 处理（置灰 + "freshness unknown · STALE"）；无数据空态保持原样 | `npm run build` 通过（tsc）；`ExposurePanel` 传入 `hasData={rows?.length > 0}` |
| M3 | ECharts tooltip formatter 把原始 ticker 拼进 HTML 字符串 → 反射型 XSS 面（`ExposurePanel.tsx:44-47`） | 新增 5 行 `escapeHtml`，ticker 与 contributing_etfs 拼接前转义 | 同上构建通过；SSGA 为可信源，实际可利用性低 |
| M4 | `"Free, official, no ToS risk"` 无证据法律断言仍在模块 docstring（`ssga.py:13`） | 改为 "fetched at low frequency with descriptive UA; SSGA ToS not independently reviewed" | 文本修改 |
| M5 | 同一文件内重复 ticker 会被 `weights[ticker] += ...` double-count（`compute/exposure.py:19-23`） | parser 内对单文件 ticker 去重-or-raise（fail-loud 优先）；跨 ETF 重复合法（GOOGL 在 XLC+XLY）不受影响 | `test_duplicate_ticker_row_within_file_raises`：fixture 追加 NVDA 重复行 → raise；golden fixture 本身 75 ticker 全唯一，parser 契约测试仍绿 |

## 🟡 Minor（状态）

- **m1** `is_stale` 对未来日期返回"新鲜" → 已修：`as_of > today → stale`（`test_future_as_of_is_stale`）。
- **m2** "As of" 单一日期格式 → 已修：`AS_OF_FMTS = ("%d-%b-%Y", "%Y-%m-%d", "%d %b %Y")` 逐个尝试再 fail-loud（`test_as_of_accepts_iso_fallback_format`）。
- **m3** 长周末无测试 → 已补：`test_long_weekend_monday_holiday`（Labor Day 周一休市，周二视周五数据为 fresh）。
- **m4** `daily.py` 的 `m2` CLI 命令无交易日门控 → 已修：与 `run-all` 同门控，非交易日 echo 跳过。
- **m5** `types.ts:46` 注释漂移（"0..~1" vs 后端允许 -0.01）→ 已同步为 `-0.01..~1`。
- **m6** `test_pure_function_signature` 弱 guard → 保留（架构测试已强制 `compute→models only`，冗余无害）。
- **m7** `StockExposure.total_weight` 下界 -0.01：某 ticker 跨多只 ETF 负权重腿加总跌破 -0.01 时 `run_m2` 会整单 ValidationError → 现实中极不可能（需 -1% 级跨 ETF 空头），记录，Phase 2+ 观察。
- **m8** NYSE 假日表只到 2027 → fail-safe（2028 未登记假日会被当交易日，但写入全按文件 as_of keyed、无日期污染，面板按 T+1 正确 stale）；**排期**：每年 12 月补充假日表，建议加日历更新提醒。

## 回归证据（2026-10-01，修复后）

- `pytest tests`：**45 passed**（38 → 45，新增 B1/B2/M1/M5/m1/m2/m3 测试 7 个）
- `ruff check` / `ruff format --check`：全绿
- 架构测试（`tests/test_architecture.py` AST 层级）：通过，无 god object（所有文件 <160 行）
- React 生产构建：通过（ECharts chunk >500kB 警告为已知 minor，排期做 code-splitting）
- 真实冒烟（修复前已验证，修复不涉及网络路径）：11 只 ETF 全量 516 holdings / 516 exposures，`as_of=2026-09-30`

## 遗留到后续阶段

- Phase 0 M5（CBOE robots/ToS）→ Phase 4 开工前补查。
- Phase 0 M6（EDGAR 403 系本机 egress IP）→ VPS 部署后复验。
- Phase 2 开工前用户需决策：Yahoo chart（非官方）做 EOD 主源 vs 恢复 Tiingo。

---

# REDTEAM — Phase 2 独立审查（2026-10-01）

审查人：独立红队子代理（未参与实现）→ 蓝队修复 → 复验通过 → 本文件为最终记录。

EOD 数据源：用户决策（2026-10-01）**先用 Yahoo**（chart API，adj close 优先；Tiingo 免费档为 fallback）。

## 总 verdict：CONDITIONAL → 修复后 GO

2 个 blocker 均为静默数据损坏类（与 Phase 1 同一标准），已修复并加回归测试；
5 个 minor 中 4 个已修复（minor-2 为一行变更）、1 个接受为已知限制（minor-3）。

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | `ingest/eod.py`：`adjclose` 数组短于 `timestamp` 时静默回退到未复权收盘，同一序列混用两种价格，20/60d 超额收益被写坏且无报错 | `parse` 内 fail-loud：`adjclose` 存在但长度 ≠ timestamps 长度 → `ValueError`（上游 schema 漂移） | `test_short_adjclose_raises_loudly`：fixture 截断 5 个 adjclose → 抛错；`test_prefers_adjusted_close` 仍过（正常路径不受影响） |
| B2 | `ingest/eod.py` + `compute/momentum.py`：payload 含重复时间戳时 adapter 返回 65 根 bar（64 个日期），下游 `{date: close}` 字典静默 last-wins，动量被写坏 | `parse` 内 fail-loud：`len(set(timestamps)) != len(timestamps)` → `ValueError` | `test_duplicate_timestamps_raise_loudly`：fixture 追加重复时间戳 → 抛错；`run_m3` 端到端不再可达此路径 |

## 🟡 Minor（已修复 4 / 接受 1）

| # | 问题 | 处理 |
|---|------|------|
| m1 | `YahooEodAdapter(now=naive_dt)` 在非 ET 系统上静默击穿未收盘 bar 门禁（timestamp() 按系统时区解读） | `__init__` 拒绝 naive datetime，非 ET aware 统一 `astimezone(ET)`；`test_naive_now_rejected` |
| m2 | 日常 `m3` 用 `range=3mo`（~64 bars），跨年假窗口可跌破 61-bar 门限导致 pipeline 持续 fail-loud | 日常默认改为 `range=6mo`（仍 12 个请求）；`backfill-m3` 同值 |
| m3 | `run_m3` 内三处独立 commit（bars → momentum → freshness），崩溃窗口留下 bars-without-momentum | **接受为已知限制**：freshness 未标记 → 面板诚实 STALE，重试经幂等 upsert 自愈；与 Phase 1 `run_m2` 同模式，不在 v1 改 |
| m4 | `_validate_batch` 对空 bars 列表抛 `max() arg is an empty sequence`，不指名 ticker | 先检查空列表，`ValueError(f"M3: {ticker} returned no bars ...")` |
| m5 | `run_m3(as_of=...)` 调用方覆盖可使 freshness 与 momentum 行 as_of 脱钩 | 删除该参数，`as_of` 恒由校验后的 batch 派生（三处调用点已确认无人传参） |

## ✅ 红队验证通过项（抽样证据）

- B1 一致性门：混合 latest bar 日期 → 写前 `ValueError`（含 16:00 ET 抓取跨时段场景）。
- 单 ticker 404 → `PoliteClient` 对 4xx 快速抛错，零写入（all-or-nothing）。
- 未收盘 bar 门禁：盘中丢弃 / 收盘后保留 / Yahoo 自带 `regular.end` 覆盖提前收市日 / 周末运行，均正确；bar 时间戳为 09:30 ET，按 ET 日期转换 DST 安全。
- 计算层按 benchmark 日期对齐，ticker 缺日期 → fail-loud，无静默窗口漂移。
- `GET /api/v1/momentum`：M3 未运行返回 `[]`；前端空态诚实；`Panel` fail-closed（freshness 未知 → STALE 灰化）。
- 文案诚实："价格动量信号，非资金流"，无资金流/主力/聪明钱表述；ECharts tooltip 延续 Phase 1 的 `escapeHtml`。
- 架构测试通过；新增文件 15–165 行，均在 ~300 行预算内；无分层违规。
- 回填链路：新库 `backfill-m3`（6mo≈126 bars）→ 日常 `m3`；或日常先行（64 ≥ 61），无缺口。
- 真实数据冒烟（2026-10-01）：12 ticker × 126 bars → 1512 bars 入库，11 板块动量（XLK 领涨 +7.77%/+6.43%，XLE 走弱），幂等重跑 OK。

最终：68 tests passed，ruff check + format clean，React 构建通过（ECharts chunk > 500kB 告警延续 Phase 1，defer）。

---

# Phase 3 红队：M4（13F-HR + Form 4）—— 2026-10-02

红队：独立子代理（未参与实现），全部 finding 均有可运行 PoC（MockTransport + SQLite 真实入库，未碰 live SEC）。
审查人：独立红队子代理 → 蓝队修复 → 复验通过 → 本文件为最终记录。

## 总 verdict：NO-GO → 修复后 GO

1 个 BLOCKER（静默数据损坏，污染面板核心金额指标）+ 7 个 MAJOR 已全部修复并加回归测试；
8 个 MINOR 中 6 个已修复、1 个转 VPS 验证清单、导航文案改中性词。

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | `migrations/005_m4.sql`：`form4_transaction` PK = `(accession, date, code, shares)` 不含价格/行号；同一 filing 内两笔同股数不同价格的买入（如 500股@$50.10 + 500股@$50.25）第二笔被 `DO NOTHING` 静默吃掉，入库金额 $25,050 vs 真实 $50,175；且 `stats["buys"]` 按解析计数（记 2）与 DB（1）自相矛盾 | `migrations/006_m4_redteam.sql`：重建表，新 PK = `(accession_number, ordinal)`（filing 内 0-based 行号，解析时确定性分配）；`upsert_filing` 返回实际插入行数，service 用 `assert inserted == len(transactions)` 做 B1 回归门 | `test_b1_two_lots_same_shares_both_stored`：两笔 500股不同价 → 全部入库，buys=2，总金额 $50,175；006 在 005 旧库上受控验证：增量应用、数据保留、行号重排 |

## 🟡 Major（已修复 7/7）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| M1 | `services/m4.py::run_form4`：循环内任一 filing 抛错（malformed XML、缺 ticker、偶发 403）→ 整个全市场扫描中断，freshness 永不标记；3 天 trailing window 使毒 filing 每天准时复现，约 4 天数据黑洞 | 单 filing try/except 隔离 → `stats["errors"]` 记录后继续；freshness 照常标记（带错的部分扫描 > 静默黑洞） | `test_m1_poison_filing_does_not_kill_scan`：3 filing 中间 malformed → fetched=2、errors=1、freshness 照常标记为 2026-10-01 |
| M2 | 4/A 修正案 accession 与原 filing 不同 → `has_accession` 拦不住 → 同一笔买入原值+修正值双行入库，面板双计 | EFTS `_source.form` 存入 `form4_filing.form_type`（006 新增列）；`InsiderBuyView.is_amendment`；面板 “修正” 徽标 + 文案披露“更正后的金额可能以单独行出现”（v1 不自动 supersede：XML/EFTS 均无可靠的原 accession 链接，自动压制可能静默删除真实交易） | `test_m2_amendment_flagged_not_double_counted_silently`：form=4/A → 视图 is_amendment=True |
| M3 | `parse_form4` 只取第一个 `reportingOwner`：联合申报（配偶/共同受托人常见）被错误归因，且当第一 owner 非高管时整笔真实高管买入在 `is_officer OR is_director` 过滤下静默消失 | 解析全部 owners：`insider` 为全名拼接，`is_joint_filing` 标记，officer/director/10% flags 跨 owner 取 OR（006 新增列）；面板 “联合申报” 标识 | `test_m3_joint_filers_no_silent_exclusion`：trust（非高管）+ CFO 联合 → flags 全 true，buy 正常入库，视图 is_joint_filing=True |
| M4 | 首季入库后所有持仓打绿 “新建仓” 徽标，UI 无任何提示 → 用户误读为“本季度刚建仓” | `ManagerPositionsView.has_previous_quarter`；面板在首季显示黄色提示条 + 中英 `firstQuarterNote` 文案 | `test_first_quarter_flagged_for_honest_badges`：单季 → 全 False；`test_run_13f_new_quarter_refetches`：两季 → True |
| M5 | cover-only 的 13F-HR/A 成为最新 filing → `_pick_infotable_doc` 找不到 infotable → 该经理永久拉取失败；且旧 `run_13f` all-or-nothing 拖住其余 11 家，无恢复路径 | 两层：① `run_13f` 单经理 try/except 隔离（errors 记录，不 block 其余）；② `fetch_13f_holdings` 对 `_NoInfotableDoc`（cover-only）在**同报告期**内向前回退到 base 13F-HR（`recent_13f_refs`）；真正的 ambiguous 仍 fail-loud | `test_cover_only_amendment_falls_back_to_base_filing`：最新 /A 无 infotable → 取同季 base，8 行入库；`test_one_manager_failure_isolated`：Berkshire 404 → 其余 11 家正常，errors 记录 1 条 |
| M6 | 2000 上限在**任何入库前**熔断：财报季后交易窗口超量 → 当天零数据（恰是内幕数据最有价值时面板为空） | 软/硬双层：>2000 只记 `volume_warning` 并大声 echo，扫描继续；>10000 才 fail-loud（真漂移） | `test_run_form4_volume_soft_warn_and_hard_cap`：2001 → warning=True 且 2001 全部入库；10001 → “hard cap” ValueError |
| M7 | 测试缺口：mock 忽略 EFTS `from` 参数 → 分页循环只走过单页；另发现 `hits.total` 缺失时静默截断（250→100，无报错） | mock 按 `from`/`size` 切片 + 调用计数；`search_form4` 对缺失 `hits.total` fail-loud | `test_m7_search_form4_paginates_and_missing_total_fails_loud`：250 hits → 3 次 EFTS 调用全量返回；缺 total → ValueError |

## 🟢 Minor（已修复 6 / 转验证 1 / 改文案 1）

| # | 问题 | 处理 |
|---|------|------|
| 1 | 面板文案 “按金额排序” 与 SQL `ORDER BY date DESC, value DESC` 矛盾 | 文案改为 “按时间倒序，同日内按金额排序” / “newest first, ranked by value within each day”（中英一致） |
| 2 | `sshPrnamtType` 被忽略：PRN（债券本金）行的数字会显示在 “股数” 列 | `parse_13f_infotable` 对非 SH 的 `sshPrnamtType` fail-loud（`test_parse_13f_prn_amt_type_fails_loud`）；fixture 全 SH 不受影响 |
| 3 | `q=%224%22` 脆弱性 + 未验证 `forms=4` 是否含 4/A | **转 VPS 验证清单**：沙盒 SEC 403 无法验证；在 VPS 上做一次去 `q` 的计数对比 + 确认 4/A 覆盖（见下） |
| 4 | 导航 “聪明钱 / Smart Money”——用户曾禁用该标签（M2 语境） | 改为中性 “机构与内幕（13F / Form 4）” / “Institutions & Insiders (13F / Form 4)”（用户可再改） |
| 5 | Form4Panel 不展示披露日，用户无法感知 ~2 天滞后 | 新增 “披露日 / Filed” 列（`filed_at` 已入库） |
| 6 | 面板未声明 “仅非衍生品交易” | `f4Desc` 补充 “仅含非衍生品交易” / “Non-derivative transactions only” |
| 7 | `is_10b5_1` 脚注误判：“NOT pursuant to a 10b5-1 plan” 被标为计划内 | `_is_10b5_1_plan`：10b5-1 前 40 字符内有 not/no 否定 → 不标记（`test_10b5_1_negation_not_flagged` 正反例） |
| 8 | `stats["window"]` 只记起点 | 改为 `"{start}..{end}"` |

## ✅ 红队验证通过项（抽样证据）

- 13F `<value>` 单位：fixture 实证（LULU 100,000 股 × $177.93 = $17,793,000 精确吻合）→ EDGAR 13F XML 的 value 是整美元，代码不 ×1000 正确。
- `fetch_form4_xml` 的 CIK fallback 有效（`PoliteClient` 对 404 抛 `HTTPStatusError`；URL 含全局唯一 accession，无错取文件可能）。
- S-sell 混入买入视图：`recent_open_market_buys` 只选 `is_open_market_buy=1`，无混淆。
- 首季 “new” 徽标：`diff_13f` 的 prev 为空逻辑保留（开发者可见 docstring），用户侧由面板提示条承接。
- 架构测试通过；拆分后 `ingest/edgar.py` 207 行 / `edgar_form4.py` 148 行，均在 ~300 行预算内；同包导入经分层测试允许。
- i18n：新增 6 个 key（f4ColFiled / f4Amendment / f4Joint / firstQuarterNote 等）中英齐备，TS type-lock 编译通过。

## ⚠️ VPS 上线前验证清单（沙盒 403，无法在此验证）

1. EFTS 去 `q` 对比：`forms=4` 单独查询的计数 ≈ 带 `q=%224%22` 的计数（排除静默遗漏）。
2. 确认 `forms=4` 返回 4/A（若不含，M2 的修正案场景变为 “修正案直接漏掉”——另一种静默问题）。
3. `backfill-m4` 全量：12 家 13F + 7 天 Form 4（约 4000 filings，~35min），观察 `volume_warning` 与 `errors`。
4. 真实数据冒烟（2026-10-01 曾验证 EFTS 模式：2 天 1119 hits，分页 `size=100`）。

最终：110 tests passed，ruff check + format clean，React 构建通过（含新增徽标/列/提示条）。

---

# REDTEAM — Phase 4（M5 CBOE put/call 情绪）独立审查（2026-10-02）

审查人：独立红队子代理（两轮：首轮发现 → 修复 → 第二轮复核）→ 蓝队修复 → 本文件为最终记录。

## 总 verdict：NO-GO → blocker + 3 major 修复后，第二轮复核 GO

## 🔴 Blocker（已修复，第二轮验证）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | `CboePutCallRepository.series()` 用 `ORDER BY trade_date ASC LIMIT :days`，表行数超 days 后返回**最旧** N 行而非 trailing-N；面板静默画出几个月前的数据且 freshness 显示 fresh（最坏的静默错数据）；`test_series_orders_asc_and_respects_limit` 把错误行为 pin 成契约 | subquery 先 `ORDER BY trade_date DESC LIMIT :days` 取最新 N 个日期，外层 `ORDER BY ASC`；测试重命名为 `test_series_returns_trailing_n_oldest_first`，3 行 + days=2 断言掉队的是最旧行 | 红队第二轮 scratch-DB 实证：旧 SQL 返回 09-28/09-29，新 SQL 返回 09-29/09-30；API `as_of`/`stale` 基于正确窗口 |

## 🟠 Major（已修复 3/3，第二轮验证）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| M1 | sanity bound `[0, 30]` 有洞：10x shift（0.88→8.8）与 100x shift 落在 [0,30] 内（如 0.25→25.0）静默入库；注释过度承诺"拦截 100x decimal shift" | bound 收紧为 `[0, 5.0]`（真实日频 put/call 比率极少超 2，index 极端也难破 5）；注释如实记录"落在 [0,5] 内的 shift 无法靠 range 捕获"的局限 | fixture 真值 0.88/1.03/0.53 通过；8.8 与 25.0 均 `CboeParseError`；新增 `test_parse_10x_decimal_shift_fails_loud` / `test_parse_100x_shift_inside_old_bound_fails_loud`（红队确认旧 bound 下两者都静默通过，非空测试） |
| M2 | backfill 的 `upsert` 在 try/except 之外：某日 DB 写失败直接 abort 整个 90 天回填，且失败**不在** errors 列表（与文档"单日失败记录并继续"矛盾） | upsert 移入内层 try/except：`session.rollback()` → `errors.append({"trade_date", "error": "upsert ..."})` → `continue` | 新增 `test_backfill_upsert_failure_isolated_and_recorded`：monkeypatch upsert 单日抛错，断言 errors 记录、其余天照常入库、坏日未存储 |
| M3 | `run_backfill_m5` 从不写 freshness：跑完 backfill、首次 daily run 前打开前端，`Panel.tsx` 按"未知即 stale"规则永久灰显（与 m3/m4 backfill 会 mark 不一致） | backfill 结束后独立 session：`fetched>0` → `mark("m5", 实际入库的最大日期)`；零 fetched → `touch("m5")`（touch 的 ON CONFLICT 只更新 checked_at，不覆盖已有 as_of） | 新增 `test_backfill_marks_freshness`：断言 `rec[0] == max(入库日期)`；红队确认 rollback 不污染后续 commit，mark 用独立 session |

## ✅ 红队验证通过项（两轮抽样证据）

- Parser：fixture 为小数值（0.88），`float()` 直接解析无 ×100/÷100 错误；`"67%"`/`"88"`（无百分号）→ fail-loud；`--`/空/`n/a` → fail-loud；周末 fixture 含 `Daily Market Statistics` marker 且零 ratio 行 → None（跳过不写）；23 个 ratio 行标签脚本验证各自唯一、精确单元格匹配无错位归因。
- Upsert：`007_m5_cboe.sql` 建表（`trade_date TEXT PRIMARY KEY`）+ `ON CONFLICT DO UPDATE` 单行 upsert，无 delete-then-insert；重跑幂等。
- Backfill：周末/节假日在发请求前跳过（`is_trading_day` 先行，测试 pin "零请求"）；≥2s 真实实现（`PoliteClient._polite_wait` 每次 `get()` 前强制等待，backfill 共用一个 scraper）；fetch/parse 单日失败隔离 + 记入 errors。
- days 越界：`max(1, min(365, days))`（0/负→1，100000→365，非整数→FastAPI 422 非 500）。
- 前端 null：`numOrNull` + `connectNulls: false` + tooltip `v == null ? "—"`，缺失点留 gap 而非 0。
- 死引用：全 repo grep `ingest.cboe` 零命中（`ingest/cboe.py` stub 已删，被 `services/cboe.py` 替代）。
- 架构：cboe.py 269 行（含 parser+scraper+service 三薄层）未超 300 行预算；freshness T+1 与其他模块一致；`run-all` 非交易日只 touch 不写 m5。

## ⚠️ VPS 上线前验证清单（沙盒 SEC 403，CBOE 未实测，必须在 VPS 执行）

1. CBOE 连通性：`m5` 单次抓取返回 200 且 ratio 在 [0.3, 2.0] 合理区间。
2. `backfill-m5` 干跑：`cboe_putcall` 行数 ≈ 90 天内交易日数；抽查 `total_put_call` 在 0.3–2.0 区间。
3. systemd timer dry-run：`systemctl start moneyflow.service` 一次性验证，日志干净后再 `enable --now` timer。
4. Phase 3 遗留（见上节 ⚠️）：EFTS 去 `q` 数量对比、`forms=4` 含 4/A 确认、`backfill-m4` 全量。

最终：134 tests passed，ruff check + format clean，React build 通过。第二轮红队 verdict GO。
