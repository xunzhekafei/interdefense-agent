# -*- coding: utf-8 -*-
"""题库层岗位差异化分析（不调用模型）。

    python evals/role_bank_diff.py

统计每个岗位的题量、分类分布，以及岗位之间题目文本的 Jaccard 相似度。
"""
import collections
import itertools
import json
import re
from pathlib import Path

ROLES = {
    "Android 工程师": "android_questions.json",
    "iOS 工程师": "ios_questions.json",
    "DevOps 工程师": "devops_questions.json",
    "产品经理": "product_questions.json",
    "数据工程师": "data_engineering_questions.json",
    "PHP 工程师": "php_questions.json",
    "Node.js 工程师": "node_questions.json",
}
DATA = Path("interview/data")
OUT = Path("evals/results/role_bank_diff.md")


def token_set(text: str) -> set:
    words = set(re.findall(r"[a-z0-9]{2,}", text.lower()))
    chinese = {text[i:i + 2] for i in range(len(text) - 1)
               if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff"}
    return words | chinese


def main():
    questions, categories, tokens = {}, {}, {}
    for role, filename in ROLES.items():
        records = json.loads((DATA / filename).read_text(encoding="utf-8"))
        questions[role] = [record["question"] for record in records]
        categories[role] = collections.Counter(record["category"] for record in records)
        tokens[role] = set()
        for question in questions[role]:
            tokens[role] |= token_set(question)

    similarity = {}
    for role_a, role_b in itertools.product(ROLES, ROLES):
        a, b = tokens[role_a], tokens[role_b]
        similarity[(role_a, role_b)] = len(a & b) / len(a | b) if a and b else 0.0

    lines = ["# 岗位题库差异化分析", "",
             "不调用模型，只比较各岗位题库的题目文本与分类分布。", "",
             "| 岗位 | 题数 | 分类数 | 主要分类 | 与其他岗位平均相似度 |",
             "| --- | --- | --- | --- | --- |"]
    for role in ROLES:
        others = [similarity[(role, other)] for other in ROLES if other != role]
        average = sum(others) / len(others) if others else 0.0
        top = "、".join(f"{name} {count}" for name, count in categories[role].most_common(3))
        lines.append(f"| {role} | {len(questions[role])} | {len(categories[role])} | {top} | {average:.3f} |")

    lines += ["", "## 岗位间相似度（越低越差异化）", "",
              "| 岗位 | " + " | ".join(ROLES) + " |",
              "| --- | " + " | ".join("---" for _ in ROLES) + " |"]
    for role_a in ROLES:
        lines.append("| " + role_a + " | " + " | ".join(
            f"{similarity[(role_a, role_b)]:.3f}" for role_b in ROLES) + " |")

    lines += ["", "## 各岗位题目样例", ""]
    for role in ROLES:
        lines.append(f"### {role}")
        for question in questions[role][:5]:
            lines.append(f"- {question}")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("报告：", OUT)


if __name__ == "__main__":
    main()