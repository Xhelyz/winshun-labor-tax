# -*- coding: utf-8 -*-
"""plugin.json 的静态校验：按 WinShun 官方 schema 的约束逐项核对。

本机没有安装 jsonschema，这里按 schema 原文（schema/plugin.schema.json）把
用到的约束写成断言，避免引入额外依赖。运行：python -m unittest tests.test_manifest
"""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(ROOT, "plugin.json")


class TestManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            cls.m = json.load(f)

    def test_required(self):
        # schema: required = ["manifest", "id", "name", "version", "commands"]
        for key in ("manifest", "id", "name", "version", "commands"):
            self.assertIn(key, self.m)

    def test_manifest_version(self):
        # schema: "manifest": {"const": 1}
        self.assertEqual(self.m["manifest"], 1)

    def test_id(self):
        # schema pattern: ^[a-z0-9_-]([a-z0-9._-]*[a-z0-9_-])?$，且要和文件夹名一致
        self.assertRegex(self.m["id"], r"^[a-z0-9_-]([a-z0-9._-]*[a-z0-9_-])?$")
        self.assertEqual(self.m["id"], os.path.basename(ROOT))

    def test_version(self):
        # 插件库要求三段
        self.assertRegex(self.m["version"], r"^\d+\.\d+\.\d+$")

    def test_runtime(self):
        rt = self.m["runtime"]
        self.assertIn(rt["mode"], ("once", "resident"))
        self.assertIn(rt["program"], ("python", "pwsh", "powershell", "node"))
        self.assertRegex(rt["script"], r"^(?![/\\]).+$")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, rt["script"])), "入口脚本不存在")
        self.assertGreaterEqual(rt["timeoutMs"], 100)
        self.assertLessEqual(rt["timeoutMs"], 10000)
        self.assertGreaterEqual(rt["debounceMs"], 0)
        self.assertLessEqual(rt["debounceMs"], 2000)

    def test_commands(self):
        commands = self.m["commands"]
        self.assertTrue(commands)
        ids = [c["id"] for c in commands]
        self.assertEqual(len(ids), len(set(ids)), "命令 id 重复")
        for cmd in commands:
            self.assertRegex(cmd["id"], r"^[a-z0-9._-]+$")
            keywords = cmd["keyword"]
            keywords = keywords if isinstance(keywords, list) else [keywords]
            for kw in keywords:
                # schema pattern: ^[^\s"]+$ —— 不能含空格和引号
                self.assertTrue(kw)
                self.assertNotRegex(kw, r"[\s\"]")
            icon = cmd.get("icon", "")
            self.assertFalse(icon.lower().endswith(".svg"), "不支持 SVG 图标")

    def test_no_permissions(self):
        # 纯计算插件不需要任何权限；有的话必须在 README 说明理由
        self.assertEqual(self.m["permissions"], [])

    def test_schema_field(self):
        self.assertTrue(self.m["$schema"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
