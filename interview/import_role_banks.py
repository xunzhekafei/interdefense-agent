# -*- coding: utf-8 -*-
"""把许可证合规的岗位题库抽成项目 schema（只取题目，不导入答案）。

    python interview/import_role_banks.py --source ../.tmp_banks

来源与许可记录在 interview/data/ROLE_BANKS_SOURCE.md。
"""
import argparse
import json
import re
from pathlib import Path

SCHEMA_KEYS = ("question", "keywords", "role", "category", "level", "stage", "lang", "source")
STOP = ("如何", "为什么", "什么", "是否", "的区别", "区别", "原理", "实现",
        "机制", "是什么", "有哪些", "怎么", "哪些", "以及", "吗", "呢")
NUMBER = re.compile(r"^\s*\d+(?:[.、]\d*)?(?:[.、]\s*|\s+)")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MARKDOWN = re.compile(r"[*_`#>|]")
EMOJI = re.compile(r"[🟢🟡🔴✅🔮]")


def clean(raw: str) -> str:
    text = LINK.sub(r"\1", raw)
    text = EMOJI.sub("", text)
    text = MARKDOWN.sub("", text)
    text = NUMBER.sub("", text)
    text = text.strip(" -—·:：")
    return re.sub(r"\s+", " ", text).strip()


def keywords_for(title: str, category: str) -> list[str]:
    english = re.findall(r"[A-Za-z][A-Za-z0-9+#._-]*", title)
    parts = re.split(r"[\s，,。？?！!：:；;、（）()【】\[\]/]+", title)
    chinese = []
    for part in parts:
        if not re.search(r"[\u4e00-\u9fff]", part):
            continue
        cleaned = part
        for stop in STOP:
            cleaned = cleaned.replace(stop, "")
        if 2 <= len(cleaned) <= 12:
            chinese.append(cleaned)
    result = []
    for token in [*english, *chinese, category]:
        token = token.strip()
        if token and token not in result:
            result.append(token)
    return result[:10]


def accept(title: str, min_len: int = 6, max_len: int = 160) -> bool:
    if not min_len <= len(title) <= max_len:
        return False
    if any(word in title.lower() for word in ("目录", "table of contents", "contributors",
                                              "readme", "license", "答案", "解析", "源码",
                                              "一句话结论", "体系讲解", "考察意图")):
        return False
    return True


def add(records, seen, title, category, role, lang, source):
    title = clean(title)
    if not accept(title) or title in seen:
        return
    seen.add(title)
    records.append({
        "question": title,
        "keywords": keywords_for(title, category),
        "role": role,
        "category": category,
        "level": "",
        "stage": "",
        "lang": lang,
        "source": source,
    })


def files(root: Path, pattern="*.md"):
    return sorted(path for path in root.rglob(pattern)
                  if ".github" not in path.parts and "node_modules" not in path.parts)


def android(records, seen, root: Path):
    for path in files(root / "android-awesome"):
        category = path.parent.name
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"^#{4,5}\s+(.+)$", line)
            if match:
                add(records, seen, match.group(1), category, "Android 工程师", "zh",
                    "JsonChao/Awesome-Android-Interview (Apache-2.0)")
    for path in (root / "android-cn").glob("*.md"):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"^\s*-\s+(.+)$", line)
            if match and ("?" in match.group(1) or "？" in match.group(1)):
                add(records, seen, match.group(1), "中文指南", "Android 工程师", "zh",
                    "stormzhang/android-interview-questions-cn (Apache-2.0)")
    for path in (root / "android-en").glob("*.md"):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"^\s*-\s*\*\*Question\*\*:\s*(.+)$", line)
            if match:
                add(records, seen, match.group(1), "英文问答", "Android 工程师", "en",
                    "amitshekhariitbhu/android-interview-questions (Apache-2.0)")


def ios(records, seen, root: Path):
    path = root / "ios-en" / "Resources" / "English.md"
    category = "iOS"
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"^(\s*)\*\s+\[([^\]]+)\]\(#", line)
        if not match:
            continue
        indent, title = match.group(1), match.group(2)
        if not indent:
            category = clean(title)
            continue
        add(records, seen, title, category, "iOS 工程师", "en",
            "dashvlas/awesome-ios-interview (MIT)")


def devops(records, seen, root: Path):
    path = root / "devops" / "README.md"
    category = "General"
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        header = re.search(r"<a name='[^']+'>([^<]+)</a>", line)
        if header:
            category = re.sub(r"\s*Questions?:?\s*$", "", clean(header.group(1))) or "General"
        match = re.match(r"^\*\s+(.+)$", line)
        if match and "?" in match.group(1):
            add(records, seen, match.group(1), category, "DevOps 工程师", "en",
                "chassing/linux-sysadmin-interview-questions (Unlicense)")


def product(records, seen, root: Path):
    for path in sorted((root / "pm" / "questions").glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        category = path.stem
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"^\*\*Q\d+.*?—\s*(.+?)\*\*\s*$", line)
            if match:
                add(records, seen, match.group(1), category, "产品经理", "en",
                    "landedjobs/ai-pm-interview-prep (MIT)")


def data_engineering(records, seen, root: Path):
    for path in files(root / "mlops", "README.md"):
        category = path.parent.name
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"^###\s+Q\d+\.\s*(.+)$", line)
            if match:
                add(records, seen, match.group(1), category, "数据工程师", "en",
                    "SepidehHosseinian/MLOPs-Interview-Questions (CC0-1.0)")


def php(records, seen, root: Path):
    base = root / "php" / "docs"
    for path in files(base):
        if path.stem == "index":
            continue
        rel = path.relative_to(base)
        category = rel.parts[0] if len(rel.parts) > 1 else "PHP"
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"^#\s+\[L\d\]\s*(.+)$", line)
            if match:
                add(records, seen, match.group(1), category, "PHP 工程师", "zh",
                    "colinlet/PHP-Interview-QA (Apache-2.0)")


def node(records, seen, root: Path):
    path = root / "node-go" / "README.md"
    category = "Node/Go"
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        heading = re.match(r"^#{2,3}\s+(.+)$", line)
        if heading:
            title = clean(heading.group(1))
            if title and len(title) <= 40 and "table of contents" not in title.lower():
                category = title
        match = re.match(r"^\|\s*\d+\s*\|\s*\[([^\]]+)\]", line)
        if match:
            add(records, seen, match.group(1), category, "Node.js 工程师", "en",
                "Gauthamjm007/Backend-NodeJS-Golang-Interview_QA (MIT)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="../.tmp_banks")
    parser.add_argument("--output", default="interview/data")
    args = parser.parse_args()
    root = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    groups = {
        "android_questions.json": android,
        "ios_questions.json": ios,
        "devops_questions.json": devops,
        "product_questions.json": product,
        "data_engineering_questions.json": data_engineering,
        "php_questions.json": php,
        "node_questions.json": node,
    }
    for filename, extractor in groups.items():
        records, seen = [], set()
        extractor(records, seen, root)
        (output / filename).write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(filename, len(records))


if __name__ == "__main__":
    main()