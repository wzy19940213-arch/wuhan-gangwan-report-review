#!/usr/bin/env python3
"""Validate a local review ledger's structure, not its engineering correctness.

Python 3.9+, standard library only. No report access, network, or file writes.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence


CATEGORIES = {"technical", "standards", "equipment", "calculation", "format", "attachments"}
SEVERITIES = {"重大", "重要", "一般"}
STATUSES = {"confirmed", "conditional", "pending"}
FORMATS = {"pdf", "docx", "doc"}
BASIS_KINDS = {"standard", "design", "report", "calculation"}
LIMITATION = "仅检查台账结构；未验证规范真实性、计算正确性、锚点位置或一条一问题。"


def _reject_constant(value: str) -> None:
    raise ValueError("不允许非有限 JSON 数值：" + value)


def _unique_object(pairs: Any) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 对象含重复字段：" + key)
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    """Parse JSON, accepting a leading BOM and rejecting ambiguous objects."""
    return json.loads(text.lstrip("\ufeff"), parse_constant=_reject_constant,
                      object_pairs_hook=_unique_object)


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def validate(data: Any) -> List[str]:
    """Return all available structural errors; an empty list means structure only."""
    errors = []

    def error(path: str, message: str) -> None:
        errors.append(path + ": " + message)

    def obj(value: Any, path: str, required: set, optional: set) -> bool:
        if not isinstance(value, dict):
            error(path, "必须是对象（不接受数组或多位置锚点）")
            return False
        for key in sorted(required - value.keys()):
            error(path + "." + key, "缺少必需字段")
        for key in sorted(value.keys() - required - optional, key=str):
            error(path + "." + str(key), "未知字段")
        return True

    def string(value: Any, path: str) -> bool:
        if not isinstance(value, str) or not value.strip():
            error(path, "必须是非空字符串")
            return False
        return True

    def enum(value: Any, path: str, choices: set) -> None:
        if not isinstance(value, str) or value not in choices:
            error(path, "必须为 " + ", ".join(sorted(choices)))

    def numbers(value: Any, path: str) -> None:
        # Also catches overflow such as 1e999 accepted as inf by json.loads.
        if isinstance(value, float) and not math.isfinite(value):
            error(path, "不允许 NaN 或 Infinity 等非有限数值")
        elif isinstance(value, dict):
            for key, item in value.items():
                numbers(item, path + "." + str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                numbers(item, path + "[" + str(index) + "]")

    numbers(data, "$")
    if not obj(data, "$", {"schema_version", "source", "findings"}, set()):
        return errors
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        error("$.schema_version", "必须是整数 1（不能为 true 或 1.0）")
    source = data.get("source")
    if obj(source, "$.source", {"name", "sha256"}, set()):
        string(source.get("name"), "$.source.name")
        sha = source.get("sha256")
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None:
            error("$.source.sha256", "必须是 64 位十六进制 SHA-256 字符串；不会自动读取原报告核对")
    findings = data.get("findings")
    if not isinstance(findings, list):
        error("$.findings", "必须是数组")
        return errors
    seen = set()
    required = {"id", "category", "severity", "status", "anchor", "observed", "basis", "action"}
    for index, finding in enumerate(findings):
        path = "$.findings[" + str(index) + "]"
        if not obj(finding, path, required, {"calculation"}):
            continue
        identifier = finding.get("id")
        if string(identifier, path + ".id"):
            if identifier in seen:
                error(path + ".id", "ID 重复：" + identifier)
            seen.add(identifier)
        enum(finding.get("category"), path + ".category", CATEGORIES)
        enum(finding.get("severity"), path + ".severity", SEVERITIES)
        enum(finding.get("status"), path + ".status", STATUSES)
        string(finding.get("observed"), path + ".observed")
        string(finding.get("action"), path + ".action")
        anchor = finding.get("anchor")
        ap = path + ".anchor"
        if obj(anchor, ap, {"format"}, {"page1", "quote", "locator", "bbox"}):
            enum(anchor.get("format"), ap + ".format", FORMATS)
            if "page1" in anchor and (type(anchor["page1"]) is not int or anchor["page1"] < 1):
                error(ap + ".page1", "必须是从 1 起的正整数页码")
            for field in ("quote", "locator"):
                if field in anchor:
                    string(anchor[field], ap + "." + field)
            if not any(isinstance(anchor.get(k), str) and anchor[k].strip()
                       for k in ("quote", "locator")):
                error(ap, "quote 和 locator 至少提供一个非空字符串")
            if "bbox" in anchor:
                box = anchor["bbox"]
                if not isinstance(box, list) or len(box) != 4 or not all(_finite(v) for v in box):
                    error(ap + ".bbox", "必须为四个有限数字的数组 [x0, y0, x1, y1]；布尔值不是数字")
                elif not (0 <= box[0] < box[2] and 0 <= box[1] < box[3]):
                    error(ap + ".bbox", "必须满足 0 ≤ x0 < x1 且 0 ≤ y0 < y1")
        basis = finding.get("basis")
        if not isinstance(basis, list):
            error(path + ".basis", "必须是数组")
        else:
            for bi, item in enumerate(basis):
                bp = path + ".basis[" + str(bi) + "]"
                if not obj(item, bp, {"kind", "citation", "verified"}, {"reference"}):
                    continue
                enum(item.get("kind"), bp + ".kind", BASIS_KINDS)
                string(item.get("citation"), bp + ".citation")
                if type(item.get("verified")) is not bool:
                    error(bp + ".verified", "必须是 true 或 false 布尔值")
                if "reference" in item:
                    string(item["reference"], bp + ".reference")
                if (finding.get("status") == "confirmed" and item.get("kind") == "standard"
                        and item.get("verified") is not True):
                    error(bp + ".verified", "confirmed 问题的 standard 依据必须标记 verified=true；未核实应使用 conditional 或 pending")
        if "calculation" in finding:
            calc = finding["calculation"]
            cp = path + ".calculation"
            if obj(calc, cp, {"expression", "inputs", "result"}, {"unit", "rounding"}):
                string(calc.get("expression"), cp + ".expression")
                inputs = calc.get("inputs")
                if not isinstance(inputs, dict):
                    error(cp + ".inputs", "必须为输入名称到有限数字的对象")
                else:
                    for name, value in inputs.items():
                        string(name, cp + ".inputs 的键")
                        if not _finite(value):
                            error(cp + ".inputs." + str(name), "必须是有限数字（不能为布尔值）")
                if not _finite(calc.get("result")):
                    error(cp + ".result", "必须是有限数字（不能为布尔值）")
                for field in ("unit", "rounding"):
                    if field in calc:
                        string(calc[field], cp + "." + field)
    return errors


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", help="本地 UTF-8 JSON 台账；使用 - 从标准输入读取")
    parser.add_argument("--json", action="store_true", dest="json_output", help="输出机器可读 JSON 结果")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read() if args.ledger == "-" else Path(args.ledger).read_bytes()
        data = parse_json(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        message = "无法读取或解析台账：" + str(exc)
        if args.json_output:
            print(json.dumps({"valid": False, "errors": [message], "limitation": LIMITATION}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 2
    try:
        errors = validate(data)
    except RecursionError:
        errors = ["$: 嵌套层级过深，无法进行结构校验"]
    if args.json_output:
        print(json.dumps({"valid": not errors, "errors": errors, "limitation": LIMITATION}, ensure_ascii=False))
    elif errors:
        print("结构校验未通过（" + str(len(errors)) + "项）：", file=sys.stderr)
        for error in errors:
            print("- " + error, file=sys.stderr)
        print(LIMITATION, file=sys.stderr)
    else:
        print("结构校验通过；问题条数：" + str(len(data["findings"])) + "。" + LIMITATION)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
