# US Money Flow Tracker（美股资金流追踪）

美股资金流向追踪网页：数据源全部 **$0 / 零认证**，日频 **T+1**（v1 明确不做盘中实时），前后端分离，
全站中英双语。线上仓库：https://github.com/kyledeveloper/stock-sector-fund-tracker

## 起源

做一个散户可用的美股资金追踪工具。A 股 vs 美股对比后选定美股（数据源更开放、$0 可达）。
立项约束：零成本数据源、日频 T+1、前端用 React（为日后产品矩阵预留，可整体迁入 monorepo 或独立域名）。

## 关键决策（按时间）

- **Phase 0 PoC（2026-10-01）**：5 个数据源逐一 spike（ETF.com / SSGA 持仓 / EOD 行情 / CBOE put-call / EDGAR）。
  裁决：在 $0 无认证条件下**不存在真正的逐日资金流数据源** → M1（板块资金流）被砍（用户决策 D）；
  M2 重定义为"持仓敞口快照"，诚实替代原"持仓×板块流"公式。
- **诚实性原则**：面板强制标注"持仓快照、非资金流；权重日变化主要来自价格波动"；禁用"主力/聪明钱"标签；
  导航命名为"机构与内幕（13F / Form 4）"。
- **M3 数据源（用户决策，2026-10-01）**：Yahoo chart API 为主源，Tiingo 免费档为 fallback（非官方接口，ToS 灰色地带，用户已知悉）。
- **双语（用户要求，2026-10-01）**：所有产品必须中英双语。实现为零依赖 i18n（`web/src/i18n/dict.ts` + `LangContext.tsx`，
  TS type-lock 缺英文 key 即编译失败）；后端只返回语言中立的 code/numbers。
- **M5 CBOE（用户决策，2026-10-02）**：robots.txt 不禁 daily 页，但 ToS §2 与"每日抓取+存 90 天历史"存在冲突；
  用户选择按原计划做。缓解：每日单请求、诚实 UA、间隔 ≥2s、不分发原始 HTML、面板只展示聚合比率。

## 四个模块

| 模块 | 数据源 | 内容 |
|------|--------|------|
| M2 持仓敞口快照 | SSGA 11 只行业 ETF 每日官方持仓 | 跨板块个股敞口加总排名、板块集中度、权重日变化（**非资金流**） |
| M3 板块动量/轮动 | Yahoo EOD（Tiingo 备选） | 11 行业 ETF vs SPY 的 20/60 日超额收益 + 简化 RRG 四象限 |
| M4 机构与内幕 | SEC EDGAR | 12 家机构 13F-HR 观察名单（QoQ diff：new/increased/decreased/exited）+ 全市场 Form 4 每日扫描（非衍生品、10b5-1/修正案/联合申报标注） |
| M5 期权情绪 | CBOE 公开市场统计 | total / equity put-call ratio 双线 + 0.7 参考线，90 天滚动历史（延迟展示，非预测） |

## 工程方法

- **TDD + 对抗**：每阶段 RED（先写失败测试）→ GREEN → BLUE → **独立红队攻击** → 修 blocker → 红队复验签字（`REDTEAM.md`），
  不通过不得进入下一阶段。Phase 3 修掉 1 blocker + 7 majors（全是静默数据损坏类）；Phase 4 红队第一轮 NO-GO（4 个问题，
  含一个"数据超 90 天后面板静默画旧数据"的严重 bug），修复后第二轮 GO。
- **架构（防 god object）**：分层 `ingest / compute / store / services / api / pipeline`，单文件 ~300 行软上限；
  `tests/test_architecture.py` 强制依赖方向（compute 纯函数不许碰 I/O，api 只调 services）；SQLite WAL + Repository 模式，
  换 Postgres 只改 store 层。`store/repos.py` 超 440 行后被拆分为按领域分包。
- **数据诚实**：所有 parser fail-loud（缺行、`--`、小数点错位一律抛错，绝不写脏数据）；freshness watchdog
 （as-of ET 标注、T+2 自动置灰）；非交易日跳过写入（禁止把周五数据记到周六）；全时间统一存 ET。
- **测试**：pytest + vcrpy（外部 API 录制回放，测试零真实网络）+ freezegun + ruff；134 tests green。

## 技术栈

Python 3.12 / FastAPI / Pydantic v2（全系统唯一契约）/ SQLAlchemy 2.0 / httpx / SQLite（WAL）/
React + TypeScript + Vite + ECharts / API 统一版本化 `/api/v1`

## 快速开始

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd web && npm ci && npm run build && cd ..

# 每日 pipeline（幂等，可单独重跑）：m2 → m3 → m4 → m5
.venv/bin/python -m moneyflow.pipeline.daily run-all

# 历史回填（只需一次；M4/M5 需要可直连 SEC/CBOE 的网络）
.venv/bin/python -m moneyflow.pipeline.daily backfill-m3   # M3 约 6 个月 EOD
.venv/bin/python -m moneyflow.pipeline.daily backfill-m4   # 12 家 13F + 7 天 Form 4
.venv/bin/python -m moneyflow.pipeline.daily backfill-m5   # 90 天 put/call，串行约 3 分钟

# 启动 API（前端 dist 由 FastAPI 直接 serve）
PYTHONPATH=src .venv/bin/python -m uvicorn moneyflow.api.main:app --host 127.0.0.1 --port 8000
```

生产部署（VPS + systemd timer + 备份 + 冒烟清单）见 [`docs/DEPLOY.md`](docs/DEPLOY.md)。

## 阶段历史

Phase 0 数据源 PoC → Phase 1 M2 持仓敞口 → Phase 2 M3 板块动量 → 双语基建 →
Phase 3 M4 机构与内幕（红队 B1+7 majors 全修）→ `repos.py` 拆分重构 →
Phase 4 M5 期权情绪 + hardening + 部署文档（红队 round1 NO-GO → round2 GO）→ GitHub 发布

## 明确非目标（v1）

无盘中实时；无实时期权流；13F 有 45 天滞后；不做 A 股；无板块资金流（M1 已砍，v2 再议）。
