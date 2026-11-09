# -*- coding: utf-8 -*-
"""calc.py 的行为验证：正常输入、边界值、反推一致性、无效输入。

运行：python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calc  # noqa: E402


class TestForward(unittest.TestCase):
    """税前 → 税后，逐档核对到分。"""

    def check(self, gross, tax, net, level):
        r = calc.from_gross(D(gross))
        self.assertEqual(r["tax"], D(tax), "个税 %s" % gross)
        self.assertEqual(r["net"], D(net), "税后 %s" % gross)
        self.assertEqual(r["level"], level, "级数 %s" % gross)

    def test_known_values(self):
        # 4000 元是减除费用的分界：以下按 800 元，以上按 20%
        self.check("4000", "640.00", "3360.00", 1)      # (4000-800)*20%
        self.check("4000.01", "640.00", "3360.01", 1)   # 按 20% 减除，尾差一分
        self.check("5000", "800.00", "4200.00", 1)      # 5000*0.8*20%
        self.check("8000", "1280.00", "6720.00", 1)
        self.check("10000", "1600.00", "8400.00", 1)

    def test_brackets(self):
        # 应纳税所得额 20000：收入 25000，仍在 20% 档
        self.check("25000", "4000.00", "21000.00", 1)
        # 25000.01 → 应纳税所得额 20000.008 → 进 30% 档
        r = calc.from_gross(D("25000.01"))
        self.assertEqual(r["level"], 2)
        self.assertEqual(r["rate"], D("0.30"))
        self.assertEqual(r["quick"], D("2000"))
        # 应纳税所得额 50000：收入 62500，30% 档上沿
        self.check("62500", "13000.00", "49500.00", 2)
        self.check("70000", "15400.00", "54600.00", 3)   # 56000*40%-7000
        self.check("100000", "25000.00", "75000.00", 3)  # 80000*40%-7000

    def test_below_threshold(self):
        # 800 元及以下无应纳税所得额，不预扣
        for gross in ("0.01", "500", "800"):
            r = calc.from_gross(D(gross))
            self.assertEqual(r["tax"], D("0.00"), gross)
            self.assertEqual(r["net"], calc.money(D(gross)), gross)
        r = calc.from_gross(D("800"))
        self.assertEqual(r["taxable"], D("0.00"))
        self.assertEqual(r["deduction"], D("800"))

    def test_deduction_mode(self):
        self.assertEqual(calc.from_gross(D("4000"))["deduction_mode"], "flat")
        self.assertEqual(calc.from_gross(D("4000.01"))["deduction_mode"], "percent")
        self.assertEqual(calc.from_gross(D("8000"))["deduction"], D("1600.00"))


class TestReverse(unittest.TestCase):
    """税后 → 税前：解析解必须与正向完全一致。"""

    def test_roundtrip(self):
        for gross in ("801", "4000", "4000.01", "5000", "8000", "25000", "25000.01",
                      "62500", "62500.01", "70000", "123456.78", "1000000"):
            forward = calc.from_gross(D(gross))
            back = calc.from_net(forward["net"])
            self.assertEqual(back["gross"], forward["gross"],
                             "往返不一致：%s → 税后 %s → %s" % (gross, forward["net"], back["gross"]))
            self.assertEqual(back["tax"], forward["tax"])

    def test_known_values(self):
        self.assertEqual(calc.from_net(D("6720"))["gross"], D("8000.00"))
        self.assertEqual(calc.from_net(D("6720"))["tax"], D("1280.00"))
        self.assertEqual(calc.from_net(D("3360"))["gross"], D("4000.00"))
        self.assertEqual(calc.from_net(D("21000"))["gross"], D("25000.00"))
        self.assertEqual(calc.from_net(D("49500"))["gross"], D("62500.00"))
        self.assertEqual(calc.from_net(D("54600"))["gross"], D("70000.00"))

    def test_breaks(self):
        # 分段断点两侧必须连续
        for low, high in (("800", "800.01"), ("3359.99", "3360"), ("49500", "49500.01")):
            a = calc.from_net(D(low))
            b = calc.from_net(D(high))
            self.assertLess(a["gross"], b["gross"], "%s→%s" % (low, high))
        # 800 元以内不产生税
        self.assertEqual(calc.from_net(D("800"))["tax"], D("0.00"))
        self.assertEqual(calc.from_net(D("800"))["gross"], D("800.00"))

    def test_exact_net(self):
        # 用户给的税后金额必须原样回到结果里，不能被回代误差顶掉
        for net in ("1", "500", "1000", "3370.55", "20999.99", "50000", "123456.78"):
            r = calc.from_net(D(net))
            self.assertEqual(r["net"], calc.money(D(net)), net)
            self.assertEqual(r["input_net"], calc.money(D(net)), net)


class TestParse(unittest.TestCase):
    """输入解析：正常、空、无效。"""

    def test_plain(self):
        p = calc.parse("8000")
        self.assertEqual(p["kind"], "ok")
        self.assertEqual(p["direction"], "gross")
        self.assertEqual(p["amount"], D("8000.00"))

    def test_variants(self):
        cases = {
            "8000": D("8000.00"),
            "8,000": D("8000.00"),
            "8000元": D("8000.00"),
            "8000 元": D("8000.00"),
            "８０００": D("8000.00"),          # 全角
            "1.5万": D("15000.00"),
            "1.5w": D("15000.00"),
            "¥8000": D("8000.00"),
            "人民币 8000 块": D("8000.00"),
        }
        for text, expected in cases.items():
            p = calc.parse(text)
            self.assertEqual(p["kind"], "ok", text)
            self.assertEqual(p["amount"], expected, text)

    def test_direction(self):
        for text in ("税后 6720", "6720 税后", "到手6720", "实发 6720", "net 6720", "净额6720"):
            p = calc.parse(text)
            self.assertEqual(p["kind"], "ok", text)
            self.assertEqual(p["direction"], "net", text)
        for text in ("税前 8000", "8000 税前", "应发8000", "gross 8000"):
            p = calc.parse(text)
            self.assertEqual(p["direction"], "gross", text)

    def test_empty(self):
        # 只有方向词或什么都没写：给示例，不报错
        for text in ("", "   ", "税后", "税前", "net"):
            self.assertEqual(calc.parse(text)["kind"], "empty", repr(text))

    def test_errors(self):
        self.assertEqual(calc.parse("0")["kind"], "error")
        self.assertEqual(calc.parse("0.00")["kind"], "error")
        self.assertEqual(calc.parse("8000 5000")["kind"], "error")      # 两个金额
        self.assertEqual(calc.parse("税后 税前 8000")["kind"], "error")  # 方向冲突
        self.assertEqual(calc.parse("999999999")["kind"], "error")      # 超过 1 亿
        self.assertEqual(calc.parse("abc")["kind"], "error")            # 不是金额
        self.assertEqual(calc.parse("帮我算一下")["kind"], "error")
        self.assertTrue(calc.parse("8000 5000")["message"])


class TestFormat(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(calc.fmt(D("6720")), "6,720.00")
        self.assertEqual(calc.fmt(D("1234567.8")), "1,234,567.80")
        self.assertEqual(calc.fmt(D("0")), "0.00")


if __name__ == "__main__":
    unittest.main()
