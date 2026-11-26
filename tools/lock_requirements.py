# -*- coding: utf-8 -*-
"""从当前（已验证过的）环境生成依赖锁文件。

    python tools/lock_requirements.py          # requirements-lock.txt（运行 + 开发）
    python tools/lock_requirements.py --web    # requirements-web-lock.txt（生产运行）

为什么需要锁文件：requirements 里写的是 `>=` 范围，CI 每次装最新版。
上游发一次破坏性更新，CI 会毫无征兆地变红，而你并没有改任何代码。
锁文件把「这次测试通过的版本组合」固定下来。

为什么不用 `pip install --dry-run` 生成：那会解析到**当前最新版**，
而不是我们实际跑过测试的版本。这里从已安装环境算依赖闭包，锁的是验证过的组合。

只覆盖运行 + 开发依赖；可选的语音依赖（约 2.3 GB）不锁，CI 也不装。
"""
import argparse
import importlib.metadata as metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOTS = [
    ("anthropic", ()),
    ("fastapi", ()),
    ("uvicorn", ("standard",)),
    ("pytest", ()),
    ("httpx", ()),
    ("pyyaml", ()),
    ("python-multipart", ()),
    ("python-docx", ()),
    ("python-pptx", ()),
    ("reportlab", ()),
]

WEB_ROOTS = [
    ("anthropic", ()),
    ("fastapi", ()),
    ("uvicorn", ("standard",)),
    ("python-multipart", ()),
    ("python-docx", ()),
    ("python-pptx", ()),
    ("reportlab", ()),
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_OUTPUT = PROJECT_ROOT / "requirements-lock.txt"
WEB_OUTPUT = PROJECT_ROOT / "requirements-web-lock.txt"

LOCK_HEADER = """\
# 运行 + 开发依赖的锁定版本（不含可选语音依赖）。
# 由当前验证过的环境生成；CI 用它安装，避免上游更新导致 CI 突然变红。
# 更新方式：在验证过测试的环境里重跑 tools/lock_requirements.py。
"""
WEB_HEADER = """\
# 生产运行依赖的锁定版本（不含开发工具与可选语音依赖）。
# 由当前验证过的环境生成；公网部署优先用它，避免上游更新改变运行时行为。
# 更新方式：在验证过测试的环境里重跑 tools/lock_requirements.py --web。
"""


def closure(roots):
    seen = {}
    pending = list(roots)
    while pending:
        name, extras = pending.pop()
        key = canonicalize_name(name)
        entry = seen.get(key)
        if entry is None:
            try:
                dist = metadata.distribution(name)
            except metadata.PackageNotFoundError:
                print(f"  跳过未安装的依赖：{name}")
                continue
            entry = {"dist": dist, "extras": set(), "done": False}
            seen[key] = entry
        fresh = set(extras) - entry["extras"]
        if entry["done"] and not fresh:
            continue
        entry["extras"] |= set(extras)
        entry["done"] = True
        for raw in entry["dist"].requires or []:
            req = Requirement(raw)
            if req.marker:
                try:
                    if not any(req.marker.evaluate({"extra": extra})
                               for extra in ["", *entry["extras"]]):
                        continue
                except Exception:
                    pass          # 无法判断的 marker 宁可带上，缺依赖比多依赖更糟
            pending.append((req.name, tuple(req.extras)))
    return seen


def main():
    parser = argparse.ArgumentParser(description="生成依赖锁文件")
    parser.add_argument("--web", action="store_true",
                        help="生成生产运行用的 requirements-web-lock.txt")
    args = parser.parse_args()
    if args.web:
        roots, output, header = WEB_ROOTS, WEB_OUTPUT, WEB_HEADER
    else:
        roots, output, header = ROOTS, LOCK_OUTPUT, LOCK_HEADER
    seen = closure(roots)
    lines = [f"{entry['dist'].metadata['Name']}=={entry['dist'].version}"
             for _, entry in sorted(seen.items())]
    output.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {output.name}：{len(lines)} 个包")


if __name__ == "__main__":
    main()