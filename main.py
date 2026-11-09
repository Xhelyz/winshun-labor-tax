# -*- coding: utf-8 -*-
"""Win顺 插件入口：劳务报酬计算器（一次性 once 模式）。

协议见 WinShun docs/plugins.md；本文件只做协议适配，计算与解析在 calc.py。
查询只读输入、只输出结果，不写文件、不联网、不动剪贴板。
"""

import winshun
import calc

FALLBACK_KEYWORD = "劳务"


def _plain(value):
    """速算扣除数这类整数金额的展示文字（去掉小数位）。"""
    return "%d" % int(value)


def _rate_text(r):
    """预扣率与速算扣除数的展示文字。"""
    return "%d%%（速算扣除数 %s）" % (int(r["rate"] * 100), _plain(r["quick"]))


def _bracket_text(r):
    """所属级数与区间说明。"""
    level = r["level"]
    if level == 1:
        return "预扣率表二第 1 级：不超过 20,000 元"
    if level == 2:
        return "预扣率表二第 2 级：20,000 至 50,000 元的部分"
    return "预扣率表二第 3 级：超过 50,000 元的部分"


def _deduction_text(r):
    """减除费用的展示文字。"""
    if r["deduction_mode"] == "flat":
        return "减除费用 %s（4,000 元以下按 800 元）" % calc.fmt(r["deduction"])
    return "减除费用 %s（收入的 20%%）" % calc.fmt(r["deduction"])


def preview_text(r, direction):
    """悬停时显示的完整明细。"""
    head = "劳务报酬所得个人所得税（按次预扣预缴）"
    if direction == "net":
        head = "劳务报酬：已知税后到手，反推税前（按次预扣预缴）"

    lines = [
        head,
        "",
        "税前收入        %s 元" % calc.fmt(r["gross"]),
        _deduction_text(r),
        "应纳税所得额    %s 元" % calc.fmt(r["taxable"]),
        "预扣率          %s" % _rate_text(r),
        "预扣个税        %s 元" % calc.fmt(r["tax"]),
        "税后到手        %s 元" % calc.fmt(r["net"]),
        "",
        "依据：《个人所得税扣缴申报管理办法（试行）》",
        "      国家税务总局公告 2018 年第 61 号 附件预扣率表二",
        "口径：仅个人所得税，不含增值税及附加",
        "年度汇算时并入综合所得，多退少补",
    ]
    return "\n".join(lines)


def _note_item(r):
    """口径提示（不可执行）。"""
    if r["gross"] <= 800:
        title = "收入不超过 800 元，不预扣个税"
        subtitle = "减除费用 800 元后应纳税所得额为 0；年度汇算照常并入综合所得"
    else:
        title = "预扣税额不等于最终税负"
        subtitle = "年度汇算时并入综合所得，多退少补；本结果不含增值税及附加"
    return winshun.item("note", title, subtitle, valid=False)


def _swap_item(r, direction, keyword):
    """换向计算：Enter 直接切到另一个方向，Tab 把命令填进输入框。"""
    kw = keyword or FALLBACK_KEYWORD
    if direction == "gross":
        target = "%s 税后 %s" % (kw, r["net"])
        title = "换向：按税后 %s 反推税前" % calc.fmt(r["net"])
    else:
        target = "%s %s" % (kw, r["gross"])
        title = "换向：按税前 %s 正算税后" % calc.fmt(r["gross"])
    return winshun.item(
        "swap", title, "Enter 切换方向，Tab 填入输入框",
        autocomplete=target,
        actions=[winshun.action("swap", "换向计算", "Enter")],
        data={"query": target},
    )


def _rows(r, direction, keyword):
    """结果行：第一行永远是用户最想拿到的那个数。"""
    preview = preview_text(r, direction)
    tax_title = "预扣个税 %s 元" % calc.fmt(r["tax"])
    tax_sub = "应纳税所得额 %s × %d%% − %s" % (
        calc.fmt(r["taxable"]), int(r["rate"] * 100), _plain(r["quick"]))
    taxable_title = "应纳税所得额 %s 元" % calc.fmt(r["taxable"])
    rate_title = "预扣率 %d%%，速算扣除数 %s" % (int(r["rate"] * 100), _plain(r["quick"]))

    net_row = winshun.item(
        "net", "税后到手 %s 元" % calc.fmt(r["net"]),
        "税前 %s − 个税 %s" % (calc.fmt(r["gross"]), calc.fmt(r["tax"])),
        copy=str(r["net"]), preview=preview,
    )
    gross_row = winshun.item(
        "gross", "税前收入 %s 元" % calc.fmt(r["gross"]),
        _deduction_text(r),
        copy=str(r["gross"]), preview=preview,
    )
    tax_row = winshun.item("tax", tax_title, tax_sub, copy=str(r["tax"]), preview=preview)
    taxable_row = winshun.item(
        "taxable", taxable_title,
        "收入 %s − 减除费用 %s" % (calc.fmt(r["gross"]), calc.fmt(r["deduction"])),
        copy=str(r["taxable"]), preview=preview,
    )
    rate_row = winshun.item("rate", rate_title, _bracket_text(r),
                            copy="%d%%" % int(r["rate"] * 100), preview=preview)
    swap_row = _swap_item(r, direction, keyword)
    note_row = _note_item(r)

    if direction == "gross":
        order = [net_row, tax_row, taxable_row, gross_row, rate_row, swap_row, note_row]
    else:
        order = [gross_row, tax_row, taxable_row, net_row, rate_row, swap_row, note_row]
    # 主答案行放一个计算器图标
    order[0].setdefault("icon", "glyph:U+E8EF")
    return order


def _empty_rows(keyword):
    """空状态：给出可直接 Tab 填充的示例，不让用户猜写法。"""
    kw = keyword or FALLBACK_KEYWORD
    return [
        winshun.item("hint-gross", "税前 → 税后", "例：%s 8000" % kw,
                     autocomplete="%s 8000" % kw, valid=False),
        winshun.item("hint-net", "税后 → 税前", "例：%s 税后 6720" % kw,
                     autocomplete="%s 税后 6720" % kw, valid=False),
        winshun.item("hint-format", "金额写法", "8000、8,000、8000元、1.5万 都可以", valid=False),
    ]


def _error_rows(message, keyword=""):
    kw = keyword or FALLBACK_KEYWORD
    return [winshun.item("error", "无法计算：" + message,
                         "例：%s 8000 或 %s 税后 6720" % (kw, kw),
                         valid=False)]


def build_items(text, keyword=""):
    """查询 → 结果行列表（纯函数，便于离线验证）。"""
    result = calc.parse(text)
    if result["kind"] == "empty":
        return _empty_rows(keyword)
    if result["kind"] == "error":
        return _error_rows(result["message"], keyword)

    if result["direction"] == "net":
        r = calc.from_net(result["amount"])
    else:
        r = calc.from_gross(result["amount"])
    return _rows(r, result["direction"], keyword)


def main():
    if winshun.is_action():
        request = winshun.action_request()
        if request.action == "swap":
            target = (request.item.get("data") or {}).get("query")
            if target:
                # 填好命令并保留窗口，列表会按新查询刷新
                winshun.effects(winshun.set_query(target), winshun.keep())
            return
        value = request.item.get("copy") or ""
        if value:
            winshun.effects(winshun.copy(value), winshun.notify("已复制 " + value), winshun.hide())
        return

    q = winshun.query()
    winshun.reply(build_items(q.text, q.keyword))


if __name__ == "__main__":
    main()
