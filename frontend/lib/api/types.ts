// 镜像 backend Pydantic schemas(backend/app/schemas/*.py)。
// 字段名保持 snake_case 与 backend 对齐。改 backend schema 后必须同步本文件。
//
// Decimal 字段:Pydantic v2 默认序列化为字符串以保留精度,**不要**改成 number。
// Date/DateTime 字段:Pydantic v2 默认 ISO8601 字符串。

// ============ 公共错误类型(Task 4) ============
export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

export class ApiClientError extends Error {
  status: number;
  code: string;
  detail?: unknown;

  constructor(status: number, payload: ApiError) {
    super(payload.message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = payload.code;
    this.detail = payload.detail;
  }
}

// ============ Auth ============
export interface LoginIn {
  username: string;
  password: string;
}

/** 登录成功响应(token 在 cookie,body 只回 user 信息)。 */
export interface LoginOut {
  user_id: number;
  username: string;
}

export interface MeOut {
  id: number;
  username: string;
}

// ============ Account ============
export type AccountType = 'bank_debit' | 'bank_credit' | 'alipay' | 'wechat' | 'cash';

export interface AccountOut {
  id: number;
  name: string;
  type: AccountType;
  institution: string | null;
  last4: string | null;
  currency: string;
  archived: boolean;
}

export interface AccountCreate {
  name: string;
  type: AccountType;
  institution?: string | null;
  last4?: string | null;
  currency?: string;
}

export interface AccountUpdate {
  name?: string | null;
  institution?: string | null;
  last4?: string | null;
  archived?: boolean | null;
}

// ============ Category ============
export type CategoryKind = 'expense' | 'income' | 'neutral';

export interface CategoryOut {
  id: number;
  name: string;
  parent_id: number | null;
  kind: CategoryKind;
  icon: string | null;
  color: string | null;
  sort_order: number;
}

export interface CategoryCreate {
  name: string;
  parent_id?: number | null;
  kind: CategoryKind;
  icon?: string | null;
  color?: string | null;
  sort_order?: number;
}

export interface CategoryUpdate {
  name?: string | null;
  parent_id?: number | null;
  icon?: string | null;
  color?: string | null;
  sort_order?: number | null;
}

// ============ MerchantRule ============
/** rule.match_kind:exact / contains / regex / fuzzy。
 *  注意:与 dedup.match_kind(strong/bridge/conversation)同名但不同枚举。 */
export type RuleMatchKind = 'exact' | 'contains' | 'regex' | 'fuzzy';

export interface MerchantRuleOut {
  id: number;
  pattern: string;
  match_kind: RuleMatchKind;
  category_id: number | null; // null = marker rule(只标 hit_count)
  priority: number;
  hit_count: number;
}

export interface MerchantRuleCreate {
  pattern: string;
  match_kind: RuleMatchKind;
  category_id?: number | null;
  priority?: number;
}

export interface MerchantRuleUpdate {
  pattern?: string | null;
  match_kind?: RuleMatchKind | null;
  category_id?: number | null;
  priority?: number | null;
}

// ============ Transaction ============
export type TxKind = 'expense' | 'income' | 'neutral' | 'refund';
export type SourceKind = 'bank' | 'alipay' | 'wechat' | 'conversation' | 'manual';

export interface TransactionOut {
  id: number;
  account_id: number;
  statement_import_id: number | null;
  tx_kind: TxKind;
  tx_time: string; // ISO datetime
  post_time: string | null; // ISO datetime
  amount: string; // Decimal,可正可负;具体方向由 tx_kind 决定
  currency: string;
  amount_settled_cny: string; // Decimal
  merchant_raw: string | null;
  merchant_normalized: string | null;
  description_raw: string | null;
  category_id: number | null;
  classification_confidence: number | null;
  source: SourceKind;
  is_mirror: boolean;
  mirror_of_id: number | null;
}

export interface TransactionListOut {
  items: TransactionOut[];
  total: number;
  limit: number;
  offset: number;
}

/** GET /api/transactions query string。limit 1..500,offset >=0。 */
export interface TransactionQuery {
  date_from?: string; // ISO datetime
  date_to?: string;
  account_id?: number;
  category_id?: number | null; // null 表示未分类
  kind?: TxKind;
  source?: SourceKind;
  is_mirror?: boolean;
  keyword?: string; // merchant_normalized 模糊
  limit?: number;
  offset?: number;
}

export interface TransactionPatchIn {
  category_id?: number | null;
  tx_kind?: TxKind | null;
}

/** POST /api/transactions/bulk-update-by-merchant — spec § 8.1。 */
export interface BulkUpdateByMerchantIn {
  pattern: string;
  match_kind?: 'exact' | 'contains' | 'regex' | 'fuzzy'; // 默认 contains
  category_id: number;
  also_add_rule?: boolean; // 默认 true
}

export interface BulkUpdateResult {
  affected_count: number;
  rule_id: number | null; // also_add_rule=true 时返回新建/复用的 rule_id
}

// ============ Statement Import ============
export interface StatementImportOut {
  id: number;
  account_id: number | null;
  source_type: string;
  filename: string;
  file_hash: string;
  period_start: string | null; // ISO datetime
  period_end: string | null;
  raw_row_count: number;
  imported_count: number;
  deduped_count: number;
  classified_count: number;
  imported_at: string; // ISO datetime
}

/** POST /api/statements/import 响应。 */
export interface ImportResponse {
  import_id: number;
  source_type: string;
  raw_row_count: number;
  imported_count: number;
  deduped_strong_count: number; // 自动去重(② + ③)
  dedup_pending_count: number; // 待审核(④ + ⑤)
  classified_count: number;
  unclassified_count: number;
}

export interface StatementImportListOut {
  items: StatementImportOut[];
  total: number;
}

/** GET /api/statements/{id}/review — 复查页一站式 bundle。 */
export interface ReviewBundle {
  statement: StatementImportOut;
  pending_pairs: DedupPairOut[];
  unclassified_transactions: TransactionOut[];
}

// ============ Dedup ============
/** dedup.match_kind:strong / bridge / conversation。
 *  注意:与 rule.match_kind(exact/contains/regex/fuzzy)同名但不同枚举。 */
export type DedupMatchKind = 'strong' | 'bridge' | 'conversation';
export type PairStatus = 'pending' | 'confirmed' | 'rejected';

export interface DedupPairOut {
  id: number;
  primary_tx_id: number;
  mirror_tx_id: number;
  match_kind: DedupMatchKind;
  confidence: number;
  status: PairStatus;
  reasoning: Record<string, unknown> | null;
}

export interface PendingPairListOut {
  items: DedupPairOut[];
  total: number;
}

/** POST /api/dedup/{pair_id}/confirm | /reject body。 */
export interface DedupDecisionIn {
  action: 'confirm' | 'reject';
  note?: string | null;
}

// ============ Summary ============
export type SummaryGroupBy = 'category' | 'account' | 'merchant';
export type SummaryPeriod = 'day' | 'week' | 'month' | 'year';

export interface SummaryBreakdownItem {
  group_key: string; // category name / account name / merchant_normalized
  group_id: number | null;
  amount: string; // Decimal
  count: number;
}

export interface SummaryOut {
  period: SummaryPeriod;
  date_from: string; // ISO datetime
  date_to: string;
  group_by: SummaryGroupBy;
  total_expense: string; // Decimal
  total_income: string;
  breakdown: SummaryBreakdownItem[];
}
