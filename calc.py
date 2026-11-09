# -*- coding: utf-8 -*-
"""劳务报酬所得个人所得税预扣预缴：正向（税前→税后）与反向（税后→税前）。

纯计算模块：不读写文件、不联网、不依赖宿主，便于单独测试。

政策依据
--------
《国家税务总局关于发布〈个人所得税扣缴申报管理办法（试行）〉的公告》
（国家税务总局公告 2018 年第 61 号）第八条及附件《个人所得税预扣率表二
（居民个人劳务报酬所得预扣预缴适用）》：

1. 减除费用：每次收入不超过 4 000 元的按 800 元计算；4 000 元以上的按收入的 20% 计算。
2. 预扣预缴应纳税所得额 = 收入 - 减除费用。
3. 应预扣预缴税额 = 应纳税所得额 × 预扣率 - 速算扣除数。
4. 预扣率表二：不超过 20 000 元 20%（速算扣除数 0）；超过 20 000 元至 50 000 元的部分
   30%（速算扣除数 2 000）；超过 50 000 元的部分 40%（速算扣除数 7 000）。

不含增值税及附加：个人提供劳务的增值税按小规模纳税人处理，月销售额 10 万元以下免征
（财政部 税务总局公告 2023 年第 19 号，执行至 2027-12-31）；附加税费还随城建税税率
（7%/5%/1%）分档、各地口径不一。在小额场景下这些通常为 0，给出统一数字反而会误导，
因此本模块只算个人所得税。详见 README。
"""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

D = Decimal
CENT = D("0.01")

LIMIT_4000 = D("4000")          # 减除费用的分界收入
DEDUCTION_FLAT = D("800")       # 不超过 4 000 元时的减除费用
DEDUCTION_RATE = D("0.2")       # 4 000 元以上时的减除比例

# 预扣率表二：(本级上限, 预扣率, 速算扣除数)；None 表示无上限
TABLE = (
    (D("20000"), D("0.20"), D("0")),
    (D("50000"), D("0.30"), D("2000")),
    (None, D("0.40"), D("7000")),
)

MAX_AMOUNT = D("100000000")     # 1 亿元；超过按输入错误处理

# 反解分段断点（税后到手金额）。由正向公式求逆得到：
#   net <= 800              gross = net
#   800 < net <= 3360       gross = (net - 160) / 0.8      4000 元以下段：net = 0.8·gross + 160
#   3360 < net <= 21000     gross = net / 0.84             20% 档：net = 0.84·gross
#   21000 < net <= 49500    gross = (net - 2000) / 0.76    30% 档：net = 0.76·gross + 2000
#   net > 49500             gross = (net - 7000) / 0.68    40% 档：net = 0.68·gross + 7000
NET_BREAKS = (D("800"), D("3360"), D("21000"), D("49500"))


def money(value):
    """按分四舍五入（ROUND_HALF_UP，财务口径）。"""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    """千分位、两位小数，用于展示。"""
    return "{:,.2f}".format(money(value))


def bracket(taxable):
    """返回 (级数, 预扣率, 速算扣除数)。"""
    for level, (upper, rate, quick) in enumerate(TABLE, 1):
        if upper is None or taxable <= upper:
            return level, rate, quick
    level = len(TABLE)
    return level, TABLE[-1][1], TABLE[-1][2]


def from_gross(gross):
    """税前收入 → 税后到手。返回明细字典，金额均为 Decimal（两位小数）。"""
    gross = money(gross)
    if gross <= LIMIT_4000:
        deduction = DEDUCTION_FLAT
        mode = "flat"
    else:
        deduction = money(gross * DEDUCTION_RATE)
        mode = "percent"

    taxable = gross - deduction
    if taxable < 0:
        taxable = D("0")          # 收入不足 800 元时收入额为 0，不预扣

    level, rate, quick = bracket(taxable)
    tax = money(taxable * rate - quick)
    if tax < 0:
        tax = D("0.00")

    return {
        "gross": gross,
        "deduction": deduction,
        "deduction_mode": mode,
        "taxable": money(taxable),
        "level": level,
        "rate": rate,
        "quick": quick,
        "tax": tax,
        "net": money(gross - tax),
    }


def from_net(net):
    """税后到手 → 税前收入（按分段解析解求逆，再回代校验到分）。"""
    net = money(net)
    if net <= NET_BREAKS[0]:
        gross = net
    elif net <= NET_BREAKS[1]:
        gross = (net - D("160")) / D("0.8")
    elif net <= NET_BREAKS[2]:
        gross = net / D("0.84")
    elif net <= NET_BREAKS[3]:
        gross = (net - D("2000")) / D("0.76")
    else:
        gross = (net - D("7000")) / D("0.68")

    result = from_gross(money(gross))
    # 四舍五入可能让回代结果与输入的税后金额差 1 分，最多微调 2 分钱找回整数解
    if abs(result["net"] - net) > CENT / 2:
        for delta in (CENT, -CENT, CENT * 2, -CENT * 2):
            trial = from_gross(result["gross"] + delta)
            if trial["net"] == net:
                result = trial
                break
    result["input_net"] = net
    return result


# ---- 输入解析 ---------------------------------------------------------------

REVERSE_WORDS = ("税后", "到手", "实发", "实得", "净额", "净收入", "after", "net")
FORWARD_WORDS = ("税前", "应发", "before", "gross")

# 全角数字与标点 → 半角
_WIDTH = {ord(c): ord("0") + i for i, c in enumerate("０１２３４５６７８９")}
_WIDTH.update({ord("．"): ord("."), ord("，"): ord(","), ord("　"): ord(" ")})
# 这些字符在金额里没有意义，直接丢掉（空格保留，用来分隔两个金额，避免粘成一个数）
_DROP = "\t\u00a0¥￥元块圆人民币"

_NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(万|w|W)?")
# 千分位逗号：只在后面正好跟三位数字、且这三位之后不再是数字时才算分隔符，
# 这样 "8,000" 会被合并，"8000,5000" 仍被识别成两个金额。
_GROUP_SEP = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")


def normalize(text):
    """全角转半角，去掉货币符号和“元/块”这类单位词，合并千分位逗号。"""
    s = (text or "").translate(_WIDTH)
    s = _GROUP_SEP.sub("", s)
    for ch in _DROP:
        s = s.replace(ch, "")
    return s


def parse(text):
    """解析用户输入。

    返回 {"kind": "ok", "direction": "gross"|"net", "amount": Decimal}
    或   {"kind": "empty"}
    或   {"kind": "error", "message": str}
    """
    s = normalize(text)
    low = s.lower()
    reverse = any(w in low for w in REVERSE_WORDS)
    forward = any(w in low for w in FORWARD_WORDS)
    if reverse and forward:
        return {"kind": "error", "message": "不能同时写税前和税后"}

    found = _NUM.findall(s)
    if not found:
        # 去掉方向词后还剩内容，说明用户写了别的东西，明确报错而不是装作空输入
        rest = low
        for word in REVERSE_WORDS + FORWARD_WORDS:
            rest = rest.replace(word, "")
        if rest.strip():
            return {"kind": "error", "message": "没有找到金额"}
        return {"kind": "empty"}
    if len(found) > 1:
        return {"kind": "error", "message": "一次只能算一笔，请只输入一个金额"}

    number, unit = found[0]
    try:
        amount = D(number)
    except InvalidOperation:
        return {"kind": "error", "message": "金额格式无法识别"}
    if unit:
        amount *= D("10000")

    if amount <= 0:
        return {"kind": "error", "message": "金额需要大于 0"}
    if amount > MAX_AMOUNT:
        return {"kind": "error", "message": "金额超过 1 亿，请核对后重试"}

    return {
        "kind": "ok",
        "direction": "net" if reverse else "gross",
        "amount": money(amount),
    }
