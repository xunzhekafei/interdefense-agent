# -*- coding: utf-8 -*-
"""把 YaxeZhang/Just-Code 的 BAT/字节题抽成项目 schema（只取题目，不含解法/代码）。

    python interview/import_justcode.py --source ../.tmp_justcode

来源：https://github.com/YaxeZhang/Just-Code（MIT）
只读取 BAT/bytedance.md、BAT/Algorithm.md、BAT/*.md 单题标题和 BAT/knowledge.md，
不导入 LeetCode 题解目录、解法代码或 PDF。
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "interview" / "data"
ROLE = "算法工程师"
SOURCE = "YaxeZhang/Just-Code (MIT)"
COMPANY = "字节跳动"
NUMBER = re.compile(r"^\s*\d+(?:[.、]\d*)?(?:[.、]\s*|\s+)")


def clean(raw: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw)
    text = NUMBER.sub("", text)
    text = text.strip(" -*`#>|")
    return re.sub(r"\s+", " ", text).strip()


def accept(title: str) -> bool:
    if not 4 <= len(title) <= 120:
        return False
    return not any(word in title.lower() for word in (
        "题目", "解法", "python solution", "todo", "目录", "readme", "license"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="../.tmp_justcode")
    args = parser.parse_args()
    base = Path(args.source) / "BAT"
    records, seen = [], set()

    def add(title, category):
        title = clean(title)
        if not accept(title) or title in seen:
            return
        seen.add(title)
        records.append({
            "question": title,
            "keywords": [category, COMPANY],
            "role": ROLE,
            "category": category,
            "level": "",
            "stage": "",
            "lang": "zh",
            "source": SOURCE,
            "company": COMPANY,
        })

    # 1) bytedance.md：按岗位分节，表格第一列是题目
    bytedance = base / "bytedance.md"
    if bytedance.is_file():
        section = "字节"
        for line in bytedance.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            title = cells[0]
            if not title or title == "题目" or set(title) <= set("-: "):
                continue
            add(title, f"字节-{section}")

    # 2) Algorithm.md：H3 标题是算法题名，题干正文不导入
    algorithm = base / "Algorithm.md"
    if algorithm.is_file():
        for match in re.finditer(r"^###\s+(.+)$",
                                 algorithm.read_text(encoding="utf-8", errors="ignore"), re.M):
            add(match.group(1), "算法专题")

    # 3) BAT/*.md 单题文件：取第一个 ### 标题
    for path in sorted(base.glob("*.md")):
        if path.name in ("bytedance.md", "Algorithm.md", "knowledge.md"):
            continue
        for match in re.finditer(r"^###\s+(.+)$",
                                 path.read_text(encoding="utf-8", errors="ignore"), re.M):
            add(match.group(1), "编程题")
            break

    # 4) knowledge.md：知识点列表
    knowledge = base / "knowledge.md"
    if knowledge.is_file():
        for line in knowledge.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = clean(line)
            if line and not line.startswith(("-", "*", "#")):
                add(line, "基础知识")

    output = DATA / "algorithm_questions.json"
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("written", output, "questions", len(records))
    counts = {}
    for record in records:
        counts[record["category"]] = counts.get(record["category"], 0) + 1
    print("categories", counts)
    for record in records[:12]:
        print("-", record["category"], "|", record["question"])


if __name__ == "__main__":
    main()