"""normalize_merchant 单元测试。覆盖括号 / 通道前缀 / 多余空格 / 空字符串。"""
import pytest

from app.services.statement_parser.normalize import normalize_merchant


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 中文括号:省份/城市标注剥离
        ("蚂蚁(杭州)网络技术", "蚂蚁网络技术"),
        ("淘宝(中国)软件有限公司", "淘宝软件有限公司"),
        # 英文括号
        ("Luckin Coffee (Beijing)", "Luckin Coffee"),
        # 通道前缀(防御性兜底)
        ("财付通-luckin coffee", "luckin coffee"),
        ("支付宝-中国移动", "中国移动"),
        ("银联-星巴克", "星巴克"),
        # 全角破折号
        ("财付通—瑞幸咖啡", "瑞幸咖啡"),
        # 多余空格折叠
        ("瑞幸  咖啡   北京", "瑞幸 咖啡 北京"),
        # 前后空白
        ("  美团外卖  ", "美团外卖"),
        # 空字符串 / None 安全
        ("", ""),
    ],
)
def test_normalize_merchant_cases(raw, expected):
    assert normalize_merchant(raw) == expected


def test_normalize_merchant_none_returns_empty():
    """传 None 返回空串,不抛异常。"""
    assert normalize_merchant(None) == ""


def test_normalize_merchant_idempotent():
    """二次跑等于一次跑。"""
    s = "蚂蚁(杭州)网络技术"
    once = normalize_merchant(s)
    twice = normalize_merchant(once)
    assert once == twice


def test_normalize_merchant_preserves_pure_name():
    """不该改的不改。"""
    assert normalize_merchant("瑞幸咖啡") == "瑞幸咖啡"
    assert normalize_merchant("KFC") == "KFC"
