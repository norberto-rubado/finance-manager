"""商户名归一化:去括号、剥离支付通道前缀、折叠空格。

spec § 4.1: merchant_normalized 用于跨源去重 (rapidfuzz 比较) 和规则匹配。
"""
import re


# 中英文括号(贪心避免吃多重嵌套)
_PARENS = re.compile(r"[(（][^()（）]*[)）]")
# 支付通道前缀(财付通-X / 支付宝-X / 银联-X),支持 ASCII 和全角破折号
_CHANNEL_PREFIX = re.compile(r"^(财付通|支付宝|银联)[\-—－＝]\s*")
# 多个空白(含全角)折成单空格
_WHITESPACE = re.compile(r"\s+")


def normalize_merchant(raw: str | None) -> str:
    """对商户名做归一化,返回稳定串供去重/规则匹配。

    步骤:
    1. None / 空 → 直接返回 ""
    2. 剥离支付通道前缀(防御性,正常情况解析器已拆走)
    3. 移除括号及内容
    4. 折叠多余空格、剪前后空白
    """
    if not raw:
        return ""
    s = raw.strip()
    s = _CHANNEL_PREFIX.sub("", s)
    s = _PARENS.sub("", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s
