# Finance Manager — MVP 设计文档

| 字段 | 内容 |
|---|---|
| 状态 | Draft(brainstorming → spec) |
| 日期 | 2026-05-08 |
| 范围 | MVP:账单导入 + 跨源去重 + 规则分类 + MCP 工具集(read+write) |
| 用户 | 单人记账(MVP 阶段单用户硬编码),用户角色:专利代理人 |
| 部署 | 自建 VPS,docker compose,Cloudflare DNS |
| 上层 Agent | OpenClaw(小龙虾) / Hermes Agent(爱马仕),走 MCP 协议 |

---

## 1. 背景与目标

### 1.1 现状
- 用户(单人)长期手动记账,节假日/年关常断更
- 主要消费走支付宝、微信,底层卡为交行借记卡 2498、建行信用卡 7432、建行储蓄卡 6262
- 已熟悉 OpenClaw(小龙虾)/Hermes Agent(爱马仕),希望通过 Agent 在微信/飞书/TG 里**对话式记账**

### 1.2 目标
搭建一个 **24/7 在线的个人财务后端**:
1. **批量导入**支付宝/微信/银行账单(半月/月度节奏),自动解析、去重、规则分类
2. 通过 **MCP 工具集**给上层 Agent(OpenClaw/Hermes)提供完整的 **读写**能力,让对话式记账与查询成为日常
3. 提供 **Web UI(电脑+手机响应式)**做批量导入、可视化、手动调整
4. 后端**完全不依赖 LLM**:所有 AI 推理在 Agent 那侧完成,后端只做规则、解析、去重、CRUD

### 1.3 非目标(out of scope,留 V2/V3)
- 资产/持仓全景看板、行情监控、买卖触发提醒
- 订阅到期主动推送提醒
- 健康/饮食管理
- 多用户、注册/登录流程、密码重置
- Beancount 复式记账(可选 V3 加导出)
- 后端直接调用 Anthropic/OpenAI API(已显式删除)

---

## 2. 范围与边界

### 2.1 In-scope
| 子系统 | 内容 |
|---|---|
| 1. 账单解析 | 4 个解析器:支付宝 CSV / 微信 xlsx / 交行借记卡 PDF / 建行信用卡 PDF |
| 2. 跨源去重 | 微信→银行精确锚定;支付宝→银行模糊匹配;对话录入↔账单时间窗匹配 |
| 3. 规则分类 | 商家规则表 + 系统种子规则;未命中进"未分类"队列 |
| 4. MCP 工具集 | 10 个工具(6 read + 4 write),给 OpenClaw/Hermes 调用 |
| 5. Web UI | 5 大板块,响应式(桌面/平板/手机) |
| 6. 认证 | Web UI 单用户 JWT;MCP 静态 API token |
| 7. 部署 | docker compose + Caddy + Cloudflare DNS-01,端口 8443/9443 |

### 2.2 Out-of-scope (V2/V3)
- 资产/持仓全景(子系统 4)
- 行情监控 + 触发价提醒(子系统 5)
- 订阅到期推送提醒(子系统 6)
- 多用户、注册流程
- 健康管理(子系统 8)
- 复式记账
- 建行储蓄卡 6262 解析器(V2 加)

---

## 3. 整体架构

### 3.1 架构图

```
┌─────────────────┐                     ┌─────────────────────┐
│  浏览器          │ HTTPS+JWT           │  Hermes / OpenClaw  │
│  电脑端 / 手机端 │ (8443)              │  (Agent 自带 LLM)   │
└────────┬────────┘                     └──────────┬──────────┘
         │                                         │ MCP+APIToken (9443)
         │                                         │
         ▼                                         ▼
   ┌────────────────────────────────────────────────────┐
   │  Caddy (8443/9443, DNS-01 via Cloudflare)         │
   └─┬──────────────────────────────────────────────┬──┘
     │ 内网 docker network                          │
     ▼                                              ▼
   ┌──────────────────────┐               ┌──────────────────┐
   │ Next.js 14 (3000)    │               │ MCP Server (8765)│
   │ App Router + shadcn  │               │ Python MCP SDK   │
   └──────────┬───────────┘               └────────┬─────────┘
              │ HTTP                               │ HTTP (内网)
              ▼                                    ▼
            ┌──────────────────────────────────────────┐
            │  FastAPI Backend (8000)                  │
            │  - 解析器 / 去重 / 分类 / CRUD            │
            └──────────────────┬───────────────────────┘
                               │ SQLAlchemy
                               ▼
                       ┌────────────────┐
                       │  Postgres 16   │
                       │  (5432, 内网)  │
                       └────────────────┘
```

### 3.2 技术栈

| 层 | 选型 | 备注 |
|---|---|---|
| Backend | Python 3.11 + FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 | 已在 `pyproject.toml` |
| 解析 | pdfplumber / openpyxl / pandas / 标准 csv 模块 | 已在依赖 |
| 模糊匹配 | rapidfuzz | 已在依赖 |
| MCP server | Python `mcp` SDK,薄包装 backend HTTP API | 新增依赖 |
| Frontend | Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui + Recharts + next-themes + lucide-react | 全新搭建 frontend/ |
| 部署 | docker compose + Caddy(caddy-dns/cloudflare 插件) | 修改现有 compose |
| DB | Postgres 16 | 已在 compose |

---

## 4. 数据模型

### 4.1 核心表(简化版,Alembic migration 时再补完整字段类型)

```sql
-- 用户(MVP 单用户硬编码,但留表为多用户做铺垫)
users (
  id PK, username unique, password_hash, created_at
)

-- 账户(银行卡/支付宝/微信/现金等)
accounts (
  id PK, user_id FK, name, type, institution, last4,
  currency default 'CNY', archived bool default false, created_at
)
-- type ∈ {bank_debit, bank_credit, alipay, wechat, cash}

-- 账单导入批次
statement_imports (
  id PK, user_id FK, account_id FK,
  source_type,                -- alipay_csv | wechat_xlsx | bank_pdf
  filename, file_hash unique, period_start, period_end,
  raw_row_count, imported_count, deduped_count, classified_count,
  imported_at
)

-- 交易(MVP 核心表)
transactions (
  id PK, user_id FK, account_id FK,
  statement_import_id FK nullable,        -- conversation/manual 来源时为 NULL
  tx_kind,                                 -- expense | income | neutral | refund
  tx_time TIMESTAMP, post_time nullable,
  amount NUMERIC(14,2), currency default 'CNY',
  amount_settled_cny NUMERIC(14,2),       -- 多币种时折算 CNY
  merchant_raw, merchant_normalized,      -- normalized = 去括号/省份/前缀
  counterparty_raw, description_raw,
  category_id FK nullable,
  classification_confidence FLOAT,        -- 0~1, 规则命中=1.0,Agent 写入=Agent 自报
  source,                                  -- bank | alipay | wechat | conversation | manual
  external_tx_id,                          -- 各源自带的交易号,源内防重导入
  external_merchant_id,                    -- 微信"商户单号"等
  payment_method_raw,                      -- 微信支付方式列原文,用于跨源精确锚定
  is_mirror bool default false,           -- 是否被识别为另一笔的"镜像"
  mirror_of_id FK nullable,               -- 指向 primary 那条
  source_unique_key,                       -- (source + external_tx_id) 防同源重复导入
  raw_payload JSONB,                      -- 原始行,审计/追溯用
  created_at, updated_at
)

-- 分类(树形)
categories (
  id PK, user_id FK, name, parent_id FK nullable,
  kind,                                    -- expense | income | neutral
  icon, color, sort_order,
  created_at
)

-- 商家规则(命中即套分类)
merchant_rules (
  id PK, user_id FK, pattern,
  match_kind,                              -- exact | contains | regex | fuzzy
  category_id FK, priority int default 100,
  hit_count int default 0,
  created_at, updated_at
)

-- 待审核去重对
dedup_candidates (
  id PK, user_id FK,
  primary_tx_id FK, mirror_tx_id FK,
  match_kind,                              -- strong | bridge | conversation
  confidence FLOAT,
  status default 'pending',                -- pending | confirmed | rejected
  reasoning JSONB,                         -- {rule, signals: [...]}
  created_at, decided_at nullable
)

-- API Token(给 MCP server 用)
api_tokens (
  id PK, user_id FK, name, token_hash unique,
  scopes,                                  -- read | write | admin
  created_at, last_used_at, revoked_at
)
```

### 4.2 索引策略
- `transactions(user_id, tx_time DESC)` —— 主查询路径
- `transactions(user_id, account_id, tx_time)` —— 账户筛选
- `transactions(source_unique_key)` UNIQUE —— 防同源重复导入
- `transactions(user_id, merchant_normalized)` —— 商家搜索/规则匹配
- `dedup_candidates(user_id, status)` —— 待审核队列
- `merchant_rules(user_id, priority DESC)` —— 规则匹配优先级

---

## 5. 导入流水线

### 5.1 上传 → 落库步骤

```
[1] 用户上传文件 (Web UI 拖拽 / API POST /statements/import)
      │
      ▼
[2] 计算 file_hash,查 statement_imports.file_hash 是否已存在
      ├─ 已存在 → 返回 409 提示用户
      └─ 不存在 → 落到 uploads/ 卷
      │
      ▼
[3] 调对应解析器(支付宝/微信/交行/建行)
    输出: List[RawTransaction] + 元信息(period, account_inferred)
      │
      ▼
[4] 写入 statement_imports 行
    批量 insert 到 transactions(source, source_unique_key 防重)
      │
      ▼
[5] 跨源去重(详见 §6)
    标记 is_mirror=true 或写 dedup_candidates(pending)
      │
      ▼
[6] 规则分类(详见 §7)
    命中规则 → 写 category_id,confidence=1.0
    未命中  → category_id=NULL(进"未分类"队列)
      │
      ▼
[7] 跳转 /statements/{id}/review 复查页
    展示: 待审核去重对 + 未分类交易
```

### 5.1.1 账户自动推断
解析器输出 `account_hint = {type, institution, last4?}`。导入时:

1. 查 `accounts WHERE user_id=? AND institution=? AND last4=?(or IS NULL)`
2. **命中** → 用现有 account 的 id
3. **未命中** → 自动创建一行 `account`,字段:
   - `name`:自动起为 `"建设银行信用卡 7432"` / `"交通银行储蓄卡 2498"` 等
   - `type` / `institution` / `last4` / `currency` 沿用 hint
4. 用户后续可在 `/accounts` 改名

支付宝 / 微信由于无明确卡号 hint,固定走单一全局账户(`institution='支付宝'/'微信支付'`, `last4=NULL`)。

### 5.2 解析器接口(统一抽象)

```python
class StatementParser(Protocol):
    source_type: str    # "alipay_csv" | "wechat_xlsx" | "bank_pdf_ccb_credit" | "bank_pdf_bocom_debit"

    def detect(self, file_bytes: bytes, filename: str) -> bool: ...
    """嗅探文件是否归这个解析器处理(用于自动路由)"""

    def parse(self, file_bytes: bytes) -> ParseResult: ...

@dataclass
class ParseResult:
    raw_transactions: list[RawTransaction]
    account_hint: AccountHint         # 推断到的账户(交行2498/建行7432等)
    period_start: datetime
    period_end: datetime
    metadata: dict                    # 总笔数/收入/支出汇总(用于校验)

@dataclass
class RawTransaction:
    tx_time: datetime
    post_time: datetime | None
    amount: Decimal                   # 始终为正
    currency: str
    amount_settled_cny: Decimal       # 信用卡外币交易折算后
    tx_kind: str                      # expense | income | neutral | refund
    merchant_raw: str
    counterparty_raw: str | None
    description_raw: str | None
    external_tx_id: str | None
    payment_method_raw: str | None    # 微信"建设银行信用卡(7432)"
    raw_row: dict                     # 原始字段
```

### 5.3 各解析器的关键点

#### 5.3.1 支付宝 CSV
- **编码 GBK**(必须显式指定)
- 跳过前 4 行元信息;第 5 行表头;数据从第 6 行开始
- 仅保留 `交易状态 = "交易成功"` 的行(过滤"交易关闭"等)
- 16 列字段 → RawTransaction 映射:

| CSV 列 (中文表头) | 映射到 | 备注 |
|---|---|---|
| 交易号 | `external_tx_id` | 支付宝内部唯一,源内防重导入 |
| 商家订单号 | `external_merchant_id` | |
| 交易创建时间 | `raw_payload['created_at']` | 不入主字段 |
| 付款时间 | `tx_time` | 主时间锚点 |
| 最近修改时间 | `raw_payload['modified_at']` | |
| 交易来源地 | `raw_payload['source_origin']` | "外部商家"/"淘宝"等 |
| 类型 | `raw_payload['biz_type']` | "即时到账交易"/"担保交易"等 |
| 交易对方 | `merchant_raw` + `counterparty_raw` | |
| 商品名称 | `description_raw` | |
| 金额(元) | `amount`,`amount_settled_cny`(同值) | 始终为正 |
| 收/支 | 推断 `tx_kind` | "支出"→expense / "收入"→income / "/"或空→neutral |
| 交易状态 | (filter) | 仅保留"交易成功" |
| 服务费 | `raw_payload['service_fee']` | |
| 成功退款 | `raw_payload['refund']` | 非 0 时同时插入一条 refund 类型交易 |
| 备注 | `raw_payload['note']` | |
| 资金状态 | `raw_payload['fund_status']` | "已支出"/"已收入"/"-",辅助 tx_kind 校验 |

- `currency = 'CNY'`(支付宝 CSV 不暴露外币)
- `payment_method_raw = NULL`(支付宝 CSV 不暴露底层卡)
- `account_hint`:固定为 `{type: alipay, institution: '支付宝', last4: NULL}`

#### 5.3.2 微信支付 xlsx
- 跳过前 17 行元信息;第 18 行表头;数据从第 19 行开始
- **关键:支付方式列**写明底层卡(`建设银行信用卡(7432)` 等)→ 用于跨源锚定
- `tx_kind` 推断:`收/支` 列 = "支出" → expense;= "收入" → income;= "中性交易" → neutral

#### 5.3.3 交行借记卡 PDF(交通银行)
- pdfplumber 抽表,6 列:`交易日期 / 交易地点 / 交易方式 / 借贷状态 / 交易金额 / 余额`
- 借贷状态 `借 Dr` → expense;`贷 Cr` → income
- 时间格式 `YYYY-MM-DD`
- **识别中转方关键词**(支付宝/蚂蚁/拉扎斯/云闪付/支付平台/财付通)→ 写入 `payment_method_raw` 辅助去重

#### 5.3.4 建行信用卡 PDF(建设银行)
- pdfplumber 抽表,9 列:`序号 / 交易日 / 银行记账日 / 卡号后4位 / 交易描述 / 交易币 / 交易金额 / 结算币 / 结算金额`
- 时间格式 `YYYYMMDD` 无分隔符
- **多币种**:`交易币` ≠ `结算币` 时,`amount` 用交易币原值,`amount_settled_cny` 用结算币
- **银联入账**(描述含"银联入账")+ 金额为负 → `tx_kind=neutral, category=信用卡还款`(命中种子规则)
- **财付通-X / 支付宝-X** 前缀 → 写入 `payment_method_raw` 辅助跨源识别

---

## 6. 去重算法

### 6.1 信号优先级

```
① external_tx_id 完全相等(同源重复导入) → 跳过,不入库
② 微信→银行精确锚定                    → strong, auto-confirm
③ 强重复(同源/跨源同日同额同商家高重合) → strong, auto-confirm
④ 桥接重复(支付宝→银行,中转方+金额匹配) → bridge, pending
⑤ 对话↔账单(conversation 与同日同额匹配) → conversation, pending
```

### 6.2 ② 微信→银行精确锚定算法

```
对每条新进的微信交易 W:
  从 W.payment_method_raw 提取 "(\d{4})" → last4
  在 transactions 表中查:
      source IN (bank), tx_time ∈ [W.tx_time - 1d, W.tx_time + 1d],
      account.last4 = last4, amount = W.amount, is_mirror = false
  → 命中唯一一条 B:
      标记 B.is_mirror=true, B.mirror_of_id=W.id
      写 dedup_candidates(strong, confidence=0.99, status=confirmed)
      不计入统计但保留可追溯
  → 命中多条:进 pending,人工选
  → 0 条:不处理(可能就是用零钱付的、或银行账单还没导)
```

### 6.3 ③ 强重复算法(同源 + 跨源通用)

```
对每对候选交易 (A, B),其中 source 不同:
  if A.tx_time, B.tx_time within ±1h:
    if A.amount == B.amount and same currency:
      sim = rapidfuzz.WRatio(A.merchant_normalized, B.merchant_normalized)
      if sim >= 80:
        → strong, auto-confirm,标 mirror
```

### 6.4 ④ 桥接重复算法(支付宝→银行)

```
对每条银行交易 B,若 B.merchant_raw 包含中转方关键词
(支付宝|蚂蚁|拉扎斯|云闪付|支付平台|财付通):
  candidates = transactions 中:
    source = alipay, tx_time ∈ [B.tx_time - 1d, B.tx_time + 1d],
    is_mirror = false
  尝试匹配:
    a) 单笔金额相等 → bridge candidate, confidence=0.85
    b) 多笔金额可聚合等于 B.amount(贪心) → bridge candidate, confidence=0.65
  全部进 dedup_candidates(bridge, status=pending)
  reasoning 字段记录算法路径
```

### 6.5 ⑤ 对话录入↔账单对账

```
对每条新进的账单交易 X:
  查 conversation 来源、tx_time ∈ ±1d、amount 相等的交易 C
  if rapidfuzz.WRatio(X.merchant_normalized, C.merchant_normalized) >= 70:
    写 dedup_candidates(conversation, pending)
    UI/Agent 端展示给用户决定保留哪条
```

### 6.6 去重结果对统计的影响
- `is_mirror=true` 的交易**不计入**支出/收入汇总(已确认的镜像)
- 但**保留在数据库**,可在交易列表用 toggle 显示/隐藏
- `dedup_candidates(status=pending)` 状态下,**两条都正常计入**(因为还没决断哪条是镜像) → 用户/Agent 在审核页或通过 `confirm_dedup_pair` 工具决断后,被标 mirror 的那条立即从汇总中扣除
- 默认导入复查页会显示一个提醒条幅:"当前还有 N 对待审核重复对未决断,本月汇总可能偏高"

---

## 7. 分类系统

### 7.1 种子规则(系统启动时 alembic 自动 seed)

| pattern | match_kind | category | priority | 备注 |
|---|---|---|---|---|
| `银联入账.*\d{4}` | regex | 信用卡还款(neutral) | 10 | 信用卡 PDF 还款记录 |
| `财付通-` | contains | (跨源标记,不直接分类) | 20 | 提示这是微信通道镜像 |
| `支付宝-` / `蚂蚁(杭州)` | contains | (跨源标记) | 20 | 提示这是支付宝通道镜像 |
| `云闪付` | contains | (跨源标记) | 20 | 银联代付 |
| `luckin coffee` / `瑞幸咖啡` | fuzzy | 餐饮/咖啡 | 50 | |
| `星巴克` | fuzzy | 餐饮/咖啡 | 50 | |
| `中国移动` | contains | 通讯/话费 | 50 | |
| `中国联通` | contains | 通讯/话费 | 50 | |
| `中国电信` | contains | 通讯/话费 | 50 | |
| `拉扎斯网络科技` | contains | 餐饮/外卖 | 50 | 饿了么 |
| `美团` | fuzzy | 餐饮/外卖 | 50 | |
| `淘宝平台商户` | contains | 购物/淘宝 | 50 | |
| `京东商城` | contains | 购物/京东 | 50 | |
| `中华全国专利代理师协会` | contains | 职业/会费 | 30 | 用户身份 |
| 微信红包-单发 | exact | 转账/红包 | 60 | (基于交易类型) |
| ...(共约 25-30 条种子) | | | | |

### 7.2 分类匹配流程

```
对每条 transaction T(category_id IS NULL):
  按 priority ASC 遍历用户自加规则 + 种子规则:
    if match(T.merchant_normalized, rule):
      T.category_id = rule.category_id
      T.classification_confidence = 1.0
      rule.hit_count += 1
      break
  if T.category_id IS NULL:
    保持未分类 → 进"未分类"队列等用户/Agent 处理
```

### 7.3 用户加规则的入口
- **Web UI**:在交易详情页/导入复查页选了分类后,提示"以后所有 [商家名] 自动归 [分类]?" → 创建规则
- **MCP**:Agent 调 `bulk_update_category_by_merchant(pattern, category, also_add_rule=true)` 同时改批量交易+加规则

---

## 8. MCP Server 工具集

### 8.1 工具清单(10 个)

#### Read(6 个)
| 工具 | 入参 | 出参 |
|---|---|---|
| `list_transactions` | `date_range?, category?, account?, kind?, limit=50, offset=0` | `transactions[]`,字段精简(id, time, amount, merchant, category) |
| `get_summary` | `period[day/week/month/year], group_by[category/account/merchant], date_range?` | `summary: { total_expense, total_income, breakdown: [{group, amount, count}] }` |
| `get_account_balances` | (无) | `accounts: [{id, name, type, last4, latest_balance, latest_balance_at}]` |
| `find_merchant` | `keyword` | `merchants: [{normalized, count, total_amount, sample_categories}]` |
| `list_pending_dedup_pairs` | `limit=20` | `pairs: [{id, primary, mirror, match_kind, confidence, reasoning}]` |
| `list_pending_classifications` | `limit=20` | `transactions: [{id, time, amount, merchant, suggested_categories[]}]` |

#### Write(4 个)
| 工具 | 入参 | 出参 |
|---|---|---|
| `add_transaction` | `time, amount, currency='CNY', merchant, category?, account?, kind='expense'` | `transaction_id, applied_rule?, classified_category` |
| `update_category` | `transaction_id, category` | `ok, before_category, after_category` |
| `bulk_update_category_by_merchant` | `pattern, category, match_kind='contains', also_add_rule=true` | `affected_count, rule_id?` |
| `confirm_dedup_pair` | `pair_id, action[confirm/reject]` | `ok, primary_tx_id, mirror_tx_id, action_taken` |

### 8.2 鉴权
所有工具都需要 `Authorization: Bearer <api_token>`。token 在 `.env` 配 `MCP_API_TOKEN`,可在 Web UI"设置"页生成新 token / 吊销老 token。

### 8.3 错误返回
所有工具失败时返回 MCP 标准错误格式 `{ code, message, data? }`,常见错误码:
- `AUTH_FAILED`(token 无效)
- `NOT_FOUND`(transaction_id 不存在)
- `VALIDATION_ERROR`(入参不合法)
- `CONFLICT`(如重复确认 dedup_pair)

---

## 9. Web UI 模块与路由

### 9.1 路由表

| 路径 | 用途 | 移动端适配 |
|---|---|---|
| `/login` | 单用户登录 | ✓ |
| `/` | 首页(本月概览 + 待办 + 最近 10 笔) | ✓ |
| `/transactions` | 交易列表(筛选/搜索/分页/批量改类) | ✓ 表格→卡片 |
| `/statements` | 账单导入(拖拽上传 + 历史导入列表) | ✓ |
| `/statements/[id]/review` | 单次导入复查页(待审核去重 + 未分类) | ✓ |
| `/accounts` | 账户列表(余额/类型/编辑) | ✓ |
| `/categories` | 分类管理(树形) | ✓ |
| `/rules` | 商家规则管理 | ✓ |
| `/settings` | API token 管理 / 修改密码 / 暗色模式 | ✓ |
| `/subscriptions` | (V2 占位) | — |
| `/watchlist` | (V2 占位) | — |

### 9.2 设计风格
- **shadcn/ui** 组件库为基础,Tailwind 配置使用 shadcn 默认 token
- **暗色模式**默认开启(数据敏感感)+ 用户可切回亮色,`next-themes` 实现
- **图表**用 Recharts,统一柱状/折线/饼图样式
- **字体**:Inter(英文/数字)+ 思源黑体或苹方(中文,通过 next/font 加载)
- **响应式断点**:sm 640 / md 768 / lg 1024 / xl 1280
- **手机布局**:导航折叠成 bottom tab bar,表格转卡片堆叠

### 9.3 关键页面草图(文字版)
- **首页**:顶部 4 张卡片(本月支出 / 本月收入 / 净额 / 待审核数);中部"近 10 笔"列表;底部 7 天支出折线图
- **导入复查页**:顶部进度条(已确认 X / Y);左 tab "待审核去重对" + 右 tab "未分类交易",每对/每条都有"快速操作"按钮
- **交易列表**:左侧筛选(账户/分类/时间/金额),右侧表格(手机端转卡片);批量勾选后底部出现"批量改类"工具栏

---

## 10. 认证

### 10.1 Web UI(JWT)
- 登录:`POST /api/auth/login` body `{username, password}` → 验证 → 签 JWT,设 httpOnly cookie `fm_session`(SameSite=Lax, Secure, 30 天)
- 登出:`POST /api/auth/logout` → 清 cookie
- 中间件:除 `/api/auth/login` 外所有 `/api/*` 都验证 cookie 中 JWT
- secret:`JWT_SECRET_KEY`(`.env`,`openssl rand -hex 32`)
- 单用户:`ADMIN_USERNAME` + `ADMIN_PASSWORD_HASH`(bcrypt)在 `.env` 中配置

### 10.2 MCP Server(API Token)
- 中间件:所有 MCP 工具调用前验证 `Authorization: Bearer <token>`
- token 在 DB `api_tokens` 表存 hash;`token_hash = sha256(token)`
- 创建/吊销:`POST/DELETE /api/admin/tokens`(Web UI 设置页)
- 默认 scopes:`read,write`(MVP 单用户单 token,scope 仅占位)
- 启动时,如果 `MCP_API_TOKEN` 环境变量存在但 DB 无记录 → 自动种入(便捷开发)

---

## 11. 部署与运维

### 11.1 docker-compose 修订(生产 profile)
- 添加 `caddy` 服务,占用宿主机 `8443`/`9443`
- 移除 backend/mcp/postgres 的 host 端口映射(只暴露给 docker network)
- 添加 profiles: `dev`(全部端口映射到主机) / `prod`(只 caddy 暴露)

### 11.2 Caddyfile

```
{
  email {env.CADDY_ACME_EMAIL}
}

money.yourdomain.com:8443 {
  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN}
  }
  handle /api/* {
    reverse_proxy backend:8000
  }
  handle {
    reverse_proxy frontend:3000
  }
}

money.yourdomain.com:9443 {
  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN}
  }
  reverse_proxy mcp:8765
}
```

**注意**:Caddy 默认镜像不含 cloudflare DNS 插件,需要用 `caddy:2-builder` 镜像构建自定义 caddy 二进制(`xcaddy build --with github.com/caddy-dns/cloudflare`),或直接用社区镜像 `slothcroissant/caddy-cloudflaredns`。docker-compose 里写明。

### 11.3 .env 模板补充

```
# 域名 + Cloudflare(部署时填)
DOMAIN=money.yourdomain.com
CLOUDFLARE_API_TOKEN=...           # Zone.DNS:Edit scope only
CADDY_ACME_EMAIL=you@example.com

# 鉴权
JWT_SECRET_KEY=...                  # openssl rand -hex 32
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$...      # bcrypt
MCP_API_TOKEN=...                   # openssl rand -hex 32

# 移除:ANTHROPIC_API_KEY / ANTHROPIC_MODEL(后端不再调 LLM)
```

### 11.4 备份策略
- 每天 03:00 cron 跑 `pg_dump` → 用 `age` 加密 → rclone 同步到 Cloudflare R2(兼容 S3)
- 保留最近 30 天每日 + 最近 12 个月月初
- 解密密钥保留你**本地**(不放 VPS),恢复时本地解密上传

### 11.5 防火墙(VPS)
- 入站:**仅** `22 (SSH key only) / 8443 / 9443`
- 强烈建议:`fail2ban` + ufw + 禁密码登录

---

## 12. 安全与隐私

| 风险 | 缓解措施 |
|---|---|
| Postgres 凭证泄露 | 强密码 + 不暴露 5432 给外网,仅 docker network 内访问 |
| MCP API token 泄露 | 短随机 + Web UI 一键吊销并签新 token |
| JWT secret 泄露 | `.env` 严格权限(0600),不入 git,`.env.example` 仅占位 |
| 备份泄露 | `age` 加密 + 解密密钥保留本地,云端只有密文 |
| 真名 + 消费画像泄露 | 暗色 UI 默认关闭"显示余额";设置中支持隐去末 4 位 |
| HTTPS 中间人 | DNS-01 自动签发 + HSTS header |
| 暴力登录 | bcrypt + 失败 5 次锁定 30 min(`/api/auth/login` rate limit) |

---

## 13. V2/V3 路线图(明示出 MVP 范围)

| 版本 | 内容 |
|---|---|
| V2.0 | 资产/持仓全景看板 + 行情数据接入(sina/tencent) + 触发价提醒(MCP push) |
| V2.1 | 订阅/会员到期主动推送(crontab + MCP push 给 OpenClaw/Hermes) |
| V2.2 | 建行储蓄卡 PDF 解析器 + 招行 / 工行 解析器 |
| V2.3 | Beancount 格式导出(`export_beancount` 工具) |
| V3.0 | 健康/饮食管理(独立子项目,可能复用 MCP server 模式) |
| V3.1 | 多用户(注册/登录/邀请) |

---

## 14. Open Questions(部署时由用户填空)

| 字段 | 占位 | 用户需提供 |
|---|---|---|
| 域名 | `money.yourdomain.com` | 实际购买的域名 |
| Cloudflare API Token | `<TOKEN>` | Zone.DNS:Edit scope token |
| ACME 邮箱 | `you@example.com` | 收 Let's Encrypt 通知 |
| Postgres 密码 | (随机) | 实施时 `openssl rand -hex 16` 生成 |
| JWT secret | (随机) | `openssl rand -hex 32` |
| MCP API token | (随机) | `openssl rand -hex 32` |
| 单用户密码 | (用户设) | 部署时 bcrypt 一次,放 `.env` |
| R2 bucket | `finance-backups` | 用户在 Cloudflare 创建 |
| R2 凭证 | (用户拉) | R2 Access Key ID/Secret |

---

## 15. 已显式作出的决策记录

| # | 问题 | 决策 | 理由 |
|---|---|---|---|
| 1 | MVP 子系统选哪个? | A:账单导入 + 去重 + 分类 | 命中"节假日断更后批量补账"痛点;数据底座 |
| 2 | 解析器范围 | C 起步 → 实际 4 个(支付宝 CSV / 微信 xlsx / 交行 PDF / 建行信用卡 PDF) | 覆盖 user 主要消费链路 |
| 3 | 数据模型 | A:单式流水账(非 Beancount) | 简单;去重作算法不作模型;vibe coding 友好 |
| 4 | 去重姿态 | A:强重复合并 + 桥接审核 | 准 + 可追溯;契合"半月一次审核"节奏 |
| 5 | 分类策略 | C:规则表 + Agent 协助处理未命中 | 后端零 LLM;商家记忆=规则表;天然契合批量节奏 |
| 6 | 部署模式 | D:自建 VPS | 用户已有,接 Agent 必需 |
| 7 | MCP 范围 | B:read + write 完整版 | 用户日常 = Agent 录入 + 偶尔批量导入查漏 |
| 8a | Web UI 认证 | A:单用户硬编码 + JWT | 单人项目最简,留多用户接入点 |
| 8b | MCP 认证 | E:静态 API token | MCP 协议天然兼容 |
| (废) | AI 模型选哪个? | (作废)后端不调 LLM | 用户原话:"使用小龙虾或 OpenClaw 调用,我不会直接在程序里用 AI" |
| 10 | 银行清单 | 4 个解析器,建行储蓄卡 V2 | 限 MVP 工作量 |
| 11 | UI 风格 | B:通用 SaaS(shadcn/ui) | 手机适配最稳 + 现成组件库 + 美观下限高 |
| 12 | 端口 | 8443(Web)+ 9443(MCP) | 用户 VPS 80/443 已占用 |
| 13 | DNS | A:Cloudflare + DNS-01 challenge | 主流且免费 |

---

## 16. 实施切片建议(给 writing-plans 阶段参考)

可以拆 4-5 个相对独立的实施切片,逐切片做 plan + 实施 + 验证:

1. **切片 A**:数据库 schema + Alembic 迁移 + 种子分类/规则
2. **切片 B**:4 个解析器(可并行,但建议按支付宝→微信→交行→建行顺序,因为难度递增)
3. **切片 C**:导入流水线 + 去重算法 + 规则分类 + REST API
4. **切片 D**:Web UI(login → 首页 → 交易列表 → 导入复查 → 账户/分类/规则/设置)
5. **切片 E**:MCP server 9 个工具 + 部署(Caddy/.env/备份)

每切片完成后跑一次端到端验证,再进入下一切片。

---

(end of design doc)
