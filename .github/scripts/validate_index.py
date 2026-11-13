#!/usr/bin/env python3
"""module-index.json 校验器。

用法：
  python validate_index.py --index module-index.json            # 在线模式（会查 GitHub Release）
  python validate_index.py --index module-index.json --offline  # 只做静态规则

退出码：0 = 全部通过；1 = 有错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

ALLOWED_PREFIX = "https://github.com/LKSkyBound/ScriptEase-Modules/releases/download/"
REQUIRED = ["id", "name", "version", "download_url", "sha256", "module_type"]
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
SEMVER = re.compile(r"^\d+\.\d+(\.\d+)?$")


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def github_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ScriptEase-CI", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def validate(index: dict, offline: bool) -> list[str]:
    errors: list[str] = []
    modules = index.get("modules")
    if not isinstance(modules, list):
        fail(errors, "顶层缺少 modules 数组")
        return errors

    seen_ids: set[str] = set()

    for i, m in enumerate(modules):
        label = f"modules[{i}]"
        if not isinstance(m, dict):
            fail(errors, f"{label} 不是对象")
            continue

        name = m.get("name") or m.get("id") or label
        print(f"\n[{name}]")

        missing = [f for f in REQUIRED if not m.get(f)]
        for field in missing:
            fail(errors, f"{label} 缺少字段 {field}")
        if missing:
            continue

        mid = m["id"]
        if mid in seen_ids:
            fail(errors, f"{label} id 重复：{mid}")
        seen_ids.add(mid)

        version = str(m["version"])
        if not SEMVER.match(version):
            fail(errors, f"{label} version 不是 x.y 或 x.y.z：{version}")
        else:
            ok(f"version {version}")

        url = m["download_url"]
        if not isinstance(url, str) or not url.startswith(ALLOWED_PREFIX):
            fail(errors, f"{label} download_url 不在官方前缀内：{url}")
            continue
        ok("download_url 前缀合法")

        rest = url[len(ALLOWED_PREFIX):]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            fail(errors, f"{label} download_url 结构不完整：{url}")
            continue
        tag, filename = parts
        expected_tag = f"v{version}"
        if tag != expected_tag:
            fail(errors, f"{label} tag 应为 {expected_tag}，实际 {tag}")
        else:
            ok(f"tag = {tag}")
        if not filename.lower().endswith(".zip"):
            fail(errors, f"{label} 资产不是 zip：{filename}")
        else:
            ok(f"filename = {filename}")

        sha = str(m["sha256"])
        if not HEX64.match(sha):
            fail(errors, f"{label} sha256 不是 64 位十六进制：{sha[:40]}…")
            continue
        ok("sha256 格式合法")

        size_kb = m.get("size_kb")
        if not isinstance(size_kb, int) or size_kb <= 0:
            fail(errors, f"{label} size_kb 非正整数：{size_kb}")
        else:
            ok(f"size_kb = {size_kb}")

        if offline:
            continue

        # 在线核对 Release 资产
        api = f"https://api.github.com/repos/LKSkyBound/ScriptEase-Modules/releases/tags/{tag}"
        try:
            release = github_json(api)
        except Exception as exc:  # noqa: BLE001
            fail(errors, f"{label} 无法读取 Release {tag}：{exc}")
            continue

        assets = release.get("assets") or []
        asset = next((a for a in assets if a.get("name") == filename), None)
        if asset is None:
            names = ", ".join(a.get("name", "?") for a in assets) or "（无资产）"
            fail(errors, f"{label} Release {tag} 下没有 {filename}；实际：{names}")
            continue
        ok(f"Release 资产存在：{filename}")

        if asset.get("size") != size_kb * 1024 and abs(asset.get("size", 0) - size_kb * 1024) > 1024:
            fail(errors, f"{label} 大小不符：资产 {asset.get('size')}B vs 索引 {size_kb}KB")
        else:
            ok(f"大小一致（{asset.get('size')}B）")

        digest = (asset.get("digest") or "").replace("sha256:", "").lower()
        if not digest:
            fail(errors, f"{label} GitHub 未返回 digest，无法验证内容")
        elif digest != sha.lower():
            fail(errors, f"{label} sha256 不符：资产 {digest} vs 索引 {sha}")
        else:
            ok("sha256 与资产一致")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="module-index.json")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.index):
        print(f"找不到索引文件：{args.index}")
        return 1

    try:
        with open(args.index, encoding="utf-8") as fh:
            index = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"JSON 解析失败：{exc}")
        return 1

    errors = validate(index, args.offline)
    print()
    if errors:
        print(f"结果：{len(errors)} 个问题，索引不可发布。")
        return 1
    print("结果：全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
