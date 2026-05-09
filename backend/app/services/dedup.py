"""跨源去重 service — spec § 6。

5 个信号:
- ①  同源 external_tx_id 重复 → 已在 importer.persist_raw_transactions 处理
- ②  微信→银行精确锚定 (wechat_to_bank_anchor) — 本 task
- ③  强重复(同源/跨源同日同额同商家高重合)— Task 11
- ④  桥接(支付宝→银行)— Task 12
- ⑤  对话↔账单 — Task 13

公开入口 run_dedup_pass:Task 13 添加,顺序调用 ② → ③ → ④ → ⑤。
"""
import re
from datetime import datetime, timedelta

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, DedupCandidate, Transaction


_LAST4_RE = re.compile(r"(\d{4})")
_ONE_DAY = timedelta(days=1)


def _extract_last4(payment_method: str | None) -> str | None:
    """从微信"建设银行信用卡(7432)" 抽 4 位数字。"""
    if not payment_method:
        return None
    m = _LAST4_RE.search(payment_method)
    return m.group(1) if m else None


def _make_pair(
    user_id: int,
    primary_id: int,
    mirror_id: int,
    *,
    match_kind: str,
    confidence: float,
    status: str,
    reasoning: dict,
) -> DedupCandidate:
    return DedupCandidate(
        user_id=user_id,
        primary_tx_id=primary_id,
        mirror_tx_id=mirror_id,
        match_kind=match_kind,
        confidence=confidence,
        status=status,
        reasoning=reasoning,
    )


def wechat_to_bank_anchor(
    db: Session, *, user_id: int, new_wechat_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6.2 ②:对新进微信交易,按 (last4, ±1d, amount) 找银行 mirror。

    - 唯一命中 → strong/confirmed,标 bank.is_mirror=True
    - 多命中 → 都开 strong/pending pair,等用户决断
    - 0 命中 → 不动
    """
    if not new_wechat_ids:
        return []

    pairs_created: list[DedupCandidate] = []

    wechat_txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(new_wechat_ids),
            Transaction.user_id == user_id,
            Transaction.source == "wechat",
        )
    ).scalars().all()

    for w in wechat_txs:
        last4 = _extract_last4(w.payment_method_raw)
        if not last4:
            continue
        tmin = w.tx_time - _ONE_DAY
        tmax = w.tx_time + _ONE_DAY

        candidates = db.execute(
            select(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.source == "bank",
                Transaction.is_mirror.is_(False),
                Transaction.amount == w.amount,
                Transaction.currency == w.currency,
                Transaction.tx_time >= tmin,
                Transaction.tx_time <= tmax,
                Account.last4 == last4,
            )
        ).scalars().all()

        if len(candidates) == 0:
            continue

        if len(candidates) == 1:
            b = candidates[0]
            b.is_mirror = True
            b.mirror_of_id = w.id
            pair = _make_pair(
                user_id, primary_id=w.id, mirror_id=b.id,
                match_kind="strong", confidence=0.99, status="confirmed",
                reasoning={
                    "rule": "wechat_to_bank_anchor",
                    "signals": ["last4_match", "amount_eq", "tx_time_within_1d", "unique_match"],
                    "last4": last4,
                    "delta_seconds": int((b.tx_time - w.tx_time).total_seconds()),
                },
            )
            db.add(pair)
            pairs_created.append(pair)
        else:
            for b in candidates:
                pair = _make_pair(
                    user_id, primary_id=w.id, mirror_id=b.id,
                    match_kind="strong", confidence=0.85, status="pending",
                    reasoning={
                        "rule": "wechat_to_bank_anchor",
                        "signals": ["last4_match", "amount_eq", "tx_time_within_1d",
                                    "ambiguous_multi_match"],
                        "last4": last4,
                        "candidates_count": len(candidates),
                    },
                )
                db.add(pair)
                pairs_created.append(pair)

    db.flush()
    return pairs_created


_ONE_HOUR = timedelta(hours=1)
_STRONG_RATIO_THRESHOLD = 80


def strong_dedup_cross_source(
    db: Session, *, user_id: int, new_tx_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6.3 ③:同/跨源 ±1h ratio≥80 强重复。

    本算法:
    - 仅处理 source 不同的 (A, B) 对
    - 候选范围:本次新进 ids ∪ 已有未 mirror 交易,在新进 tx 时间窗口内
    - 命中:auto-confirm,bank 那条优先标 mirror;若两侧都非 bank,后到的(created_at 大)标 mirror
    """
    if not new_tx_ids:
        return []

    pairs_created: list[DedupCandidate] = []

    new_txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(new_tx_ids),
            Transaction.user_id == user_id,
            Transaction.is_mirror.is_(False),
        )
    ).scalars().all()

    for tx in new_txs:
        if tx.is_mirror:  # 在循环里被前面的 pair 标了
            continue
        # 在 ±1h、同金额、不同 source、未 mirror 中找候选
        cands = db.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.id != tx.id,
                Transaction.is_mirror.is_(False),
                Transaction.source != tx.source,
                Transaction.amount == tx.amount,
                Transaction.currency == tx.currency,
                Transaction.tx_time >= tx.tx_time - _ONE_HOUR,
                Transaction.tx_time <= tx.tx_time + _ONE_HOUR,
            )
        ).scalars().all()

        for cand in cands:
            ratio = fuzz.WRatio(tx.merchant_normalized or "", cand.merchant_normalized or "")
            if ratio < _STRONG_RATIO_THRESHOLD:
                continue
            # 决定谁作 mirror:bank 优先;否则 created_at 大者(后到)
            if tx.source == "bank" and cand.source != "bank":
                primary, mirror = cand, tx
            elif cand.source == "bank" and tx.source != "bank":
                primary, mirror = tx, cand
            else:
                # 比 created_at,后到的标 mirror
                primary, mirror = (
                    (tx, cand) if (tx.created_at or datetime.min) <= (cand.created_at or datetime.min)
                    else (cand, tx)
                )
            mirror.is_mirror = True
            mirror.mirror_of_id = primary.id
            pair = _make_pair(
                user_id, primary_id=primary.id, mirror_id=mirror.id,
                match_kind="strong", confidence=min(0.99, ratio / 100.0),
                status="confirmed",
                reasoning={
                    "rule": "strong_dedup_cross_source",
                    "signals": ["amount_eq", "currency_eq", "tx_time_within_1h",
                                f"merchant_ratio={ratio}"],
                    "ratio": ratio,
                },
            )
            db.add(pair)
            pairs_created.append(pair)
            break  # 同 tx 一旦匹配到,不重复配

    db.flush()
    return pairs_created
