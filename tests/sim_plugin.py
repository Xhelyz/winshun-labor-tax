# -*- coding: utf-8 -*-
"""协议级仿真：按 Win顺 一次性插件的环境变量契约启动 main.py，核对 stdout。

这验证的是「脚本产出符合协议的 JSON」，不等于宿主内的真实往返；
宿主侧还需在 Win顺 里打开插件开关并检查消息记录。

运行：python tests/sim_plugin.py
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "main.py")

failures = []


def run(env_extra):
    env = dict(os.environ)
    env.update({k: str(v) for k, v in env_extra.items()})
    # 只留最小环境，避免本机 WS_* 残留干扰
    for key in list(env):
        if key.startswith("WS_") and key not in env_extra:
            env.pop(key)
    proc = subprocess.run([sys.executable, MAIN], capture_output=True, env=env, timeout=30)
    return proc


def parse(proc, label):
    out = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        failures.append("%s：退出码 %d，stderr=%s" % (label, proc.returncode,
                                                     proc.stderr.decode("utf-8", "replace")[:300]))
        return None
    if not out:
        failures.append("%s：stdout 为空" % label)
        return None
    try:
        data = json.loads(out)
    except ValueError as e:
        failures.append("%s：stdout 不是 JSON（%s）：%s" % (label, e, out[:200]))
        return None
    return data


def check_items(data, label, expect_ids):
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        failures.append("%s：items 为空或不是数组" % label)
        return []
    ids = [i.get("id") for i in items]
    if len(ids) != len(set(ids)):
        failures.append("%s：id 不唯一 %s" % (label, ids))
    for row in items:
        if not row.get("title"):
            failures.append("%s：有行缺 title %s" % (label, row))
    for want in expect_ids:
        if want not in ids:
            failures.append("%s：缺少 id=%s，实际 %s" % (label, want, ids))
    return items


def by_id(items, wanted):
    for row in items:
        if row.get("id") == wanted:
            return row
    return None


def main():
    cases = [
        ("正常-税前 8000", {"WS_QUERY": "8000", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                            "WS_TRIGGER": "keyword", "WS_TEXT": "劳务 8000"},
         ["net", "tax", "taxable", "gross", "rate", "swap", "note"]),
        ("正常-反推 税后 6720", {"WS_QUERY": "税后 6720", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                                "WS_TRIGGER": "keyword", "WS_TEXT": "劳务 税后 6720"},
         ["gross", "net", "tax", "swap"]),
        ("边界-4000", {"WS_QUERY": "4000", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                       "WS_TRIGGER": "keyword"}, ["net", "tax"]),
        ("边界-800 不预扣", {"WS_QUERY": "800", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                          "WS_TRIGGER": "keyword"}, ["net", "note"]),
        ("大额-100000", {"WS_QUERY": "100000", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                        "WS_TRIGGER": "keyword"}, ["net", "rate"]),
        ("空输入", {"WS_QUERY": "", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                    "WS_TRIGGER": "keyword"}, ["hint-gross", "hint-net"]),
        ("无效输入", {"WS_QUERY": "abc", "WS_COMMAND": "labor", "WS_KEYWORD": "劳务",
                      "WS_TRIGGER": "keyword"}, ["error"]),
    ]

    results = {}
    for label, env, expect in cases:
        data = parse(run(env), label)
        if data is None:
            continue
        items = check_items(data, label, expect)
        results[label] = items
        print("[查询] %-22s %s" % (label, " / ".join(i["title"] for i in items[:3])))

    # 数值断言：按题目给的口径核对
    items = results.get("正常-税前 8000") or []
    net = by_id(items, "net")
    tax = by_id(items, "tax")
    if net and "6,720.00" not in net["title"]:
        failures.append("税前 8000 的税后不是 6,720.00：%s" % net["title"])
    if tax and "1,280.00" not in tax["title"]:
        failures.append("税前 8000 的个税不是 1,280.00：%s" % tax["title"])
    if net and net.get("copy") != "6720.00":
        failures.append("税前 8000 的复制值不是 6720.00：%r" % net.get("copy"))

    items = results.get("正常-反推 税后 6720") or []
    gross = by_id(items, "gross")
    if gross and "8,000.00" not in gross["title"]:
        failures.append("税后 6720 反推的税前不是 8,000.00：%s" % gross["title"])

    # 空状态必须给出可 Tab 填充的示例
    items = results.get("空输入") or []
    hints = [i for i in items if i.get("autocomplete")]
    if len(hints) < 2:
        failures.append("空状态缺少带 autocomplete 的示例行")

    # 动作：Enter 复制该行数字
    proc = run({"WS_ACTION": "default", "WS_COMMAND": "labor", "WS_QUERY": "8000",
                "WS_ITEM": json.dumps({"id": "net", "title": "税后到手 6,720.00 元",
                                       "copy": "6720.00"}, ensure_ascii=False)})
    data = parse(proc, "动作-复制")
    if isinstance(data, dict):
        texts = [e.get("text") for e in data.get("effects", []) if e.get("type") == "copy"]
        if texts != ["6720.00"]:
            failures.append("动作复制的值不对：%r" % (data.get("effects"),))
        else:
            print("[动作] Enter 复制 -> %s" % texts[0])

    # 动作：换向
    proc = run({"WS_ACTION": "swap", "WS_COMMAND": "labor", "WS_QUERY": "8000",
                "WS_ITEM": json.dumps({"id": "swap", "data": {"query": "劳务 税后 6720.00"}},
                                      ensure_ascii=False)})
    data = parse(proc, "动作-换向")
    if isinstance(data, dict):
        queries = [e.get("text") for e in data.get("effects", []) if e.get("type") == "setQuery"]
        if queries != ["劳务 税后 6720.00"]:
            failures.append("换向没有正确设置查询：%r" % (data.get("effects"),))
        else:
            print("[动作] 换向 -> %s" % queries[0])

    print()
    if failures:
        print("失败 %d 项：" % len(failures))
        for f in failures:
            print(" -", f)
        return 1
    print("全部通过（查询 %d 组 + 动作 2 组）" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
