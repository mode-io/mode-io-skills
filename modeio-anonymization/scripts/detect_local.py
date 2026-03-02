#!/usr/bin/env python3
"""
Modeio AI Anonymization Skill - Local privacy detection (no API required).
Uses regex to detect PII, compute risk score, and mask text; aligned with detectSensitiveLocal in api.ts.
Suitable for: offline use, quick scans, or preliminary detection without calling the Modeio API.
"""

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Literal, Tuple

SENSITIVE_TYPES = (
    "phone", "email", "idCard", "creditCard", "bankCard",
    "address", "name", "password", "apiKey", "ipAddress",
    "ssn", "passport", "dateOfBirth",
)
RiskLevel = Literal["low", "medium", "high"]

PLACEHOLDER_MAP = {
    "phone": "PHONE",
    "email": "EMAIL",
    "idCard": "ID_CARD",
    "creditCard": "CREDIT_CARD",
    "bankCard": "BANK_CARD",
    "address": "ADDRESS",
    "name": "NAME",
    "password": "PASSWORD",
    "apiKey": "API_KEY",
    "ipAddress": "IP_ADDRESS",
    "ssn": "SSN",
    "passport": "PASSPORT",
    "dateOfBirth": "DOB",
}

HIGH_RISK_TYPES = [
    "idCard", "creditCard", "bankCard", "password", "apiKey", "ssn", "passport",
]
MEDIUM_RISK_TYPES = ["phone", "email", "ipAddress"]

RISK_WEIGHTS = {
    "idCard": 35,
    "ssn": 35,
    "creditCard": 35,
    "bankCard": 30,
    "passport": 30,
    "password": 40,
    "apiKey": 40,
    "phone": 25,
    "email": 15,
    "ipAddress": 20,
    "address": 15,
    "name": 8,
    "dateOfBirth": 12,
}

NAME_STOPWORDS_CN = {
    "测试", "管理员", "公司", "大学", "医院", "省", "市", "区", "县", "路", "街",
}
NAME_STOPWORDS_EN = {
    "admin", "administrator", "root", "user", "test", "company", "university", "hospital",
    "street", "road",
}

NAME_CONTEXT_PATTERNS = [
    {
        "lang": "cn",
        "pattern": re.compile(
            r"(?m)(?:姓名|真实姓名|联系人|收件人|签名|署名|持卡人|开户名)\s*[：:]\s*([\u4e00-\u9fa5·]{2,6})"
        ),
    },
    {
        "lang": "en",
        "pattern": re.compile(
            r"(?m)\b(?i:(?:name|full\s*name|contact|recipient|signed\s*by|cardholder|account\s*holder))\b\s*[:=]\s*([A-Z][a-z]+(?:[ '-][A-Z][a-z]+){1,2})"
        ),
    },
]

REGEX_PATTERNS = [
    {
        "type": "idCard",
        "label": "ID Card",
        "patterns": [
            r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b",
            r"\b[1-9]\d{5}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}\b",
            r"\b[A-Z]{1,2}\d{6}\([0-9A]\)",
            r"\b[A-Z][12]\d{8}\b",
        ],
    },
    {
        "type": "phone",
        "label": "Phone Number",
        "patterns": [
            r"(?<!\d)(?:(?:\+|00)86[-.\s]?)?1(?:3\d|4[5-79]|5[0-35-9]|6[5-7]|7[0-8]|8\d|9[189])[-.\s]?\d{4}[-.\s]?\d{4}(?!\d)",
            r"(?<!\d)(?:\+?1[-.\s]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[-.\s]?[2-9]\d{2}[-.\s]?\d{4}(?:\s?(?:#|x|ext\.?|extension)\s?\d{1,6})?(?!\d)",
            r"(?<!\d)(?:\+44[-.\s]?7\d{3}|0?7\d{3})[-.\s]?\d{3}[-.\s]?\d{3}(?!\d)",
            r"(?<!\d)\+[2-9]\d{1,2}[-.\s]?(?:\(\d{2,4}\)|\d{2,4})[-.\s]?\d{3,4}[-.\s]?\d{3,4}(?!\d)",
            r"(?<!\d)0\d{2,3}[-.\s]\d{7,8}(?!\d)",
        ],
    },
    {
        "type": "email",
        "label": "Email",
        "patterns": [r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"],
    },
    {
        "type": "creditCard",
        "label": "Credit Card",
        "patterns": [
            r"\b4[0-9]{12}(?:[0-9]{3})?\b",
            r"\b(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}\b",
            r"\b3[47][0-9]{13}\b",
            r"\b6(?:011|5[0-9]{2})[0-9]{12}\b",
            r"\b(?:2131|1800|35\d{3})\d{11}\b",
            r"\b62[0-9]{14,17}\b",
            r"\b4[0-9]{3}[-\s][0-9]{4}[-\s][0-9]{4}[-\s][0-9]{4}\b",
            r"\b5[1-5][0-9]{2}[-\s][0-9]{4}[-\s][0-9]{4}[-\s][0-9]{4}\b",
        ],
    },
    {
        "type": "bankCard",
        "label": "Bank Card",
        "patterns": [
            r"\b(?:622|621|620|623|625|626|627|628|629)\d{13,16}\b",
            r"\b[1-9]\d{3}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4,7}\b",
        ],
    },
    {
        "type": "ipAddress",
        "label": "IP Address",
        "patterns": [
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
            r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        ],
    },
    {
        "type": "ssn",
        "label": "SSN",
        "patterns": [
            r"\b(?!000|666|9\d{2})[0-8]\d{2}-(?!00)\d{2}-(?!0000)\d{4}\b",
            r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
        ],
    },
    {
        "type": "passport",
        "label": "Passport",
        "patterns": [r"\b[EGDSPHegdsph][a-zA-Z]?\d{8}\b", r"\b[A-Z]{2}\d{7}\b"],
    },
    {
        "type": "dateOfBirth",
        "label": "Date of Birth",
        "patterns": [
            r"(?:19[5-9]\d|20[0-2]\d)年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日",
            r"(?:生日|出生|DOB|birthday|born)[：:\s]*(?:19[5-9]\d|20[0-2]\d)[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])",
        ],
    },
    {
        "type": "apiKey",
        "label": "API Key",
        "patterns": [
            r"\bsk-[a-zA-Z0-9]{20,}\b",
            r"\b[sp]k_(?:live|test)_[a-zA-Z0-9]{20,}\b",
            r"\bAKIA[0-9A-Z]{16}\b",
            r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b",
            r"(?:api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*[:=]\s*[\"']?[a-zA-Z0-9_-]{20,}[\"']?",
            r"\bBearer\s+[a-zA-Z0-9_-]{20,}",
            r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
        ],
    },
    {
        "type": "password",
        "label": "Password",
        "patterns": [
            r"(?:password|passwd|pwd|secret|credential)\s*[:=]\s*[\"']?[^\s\"']{6,64}[\"']?",
            r"--(?:password|passwd|pwd)\s+[\"']?[^\s\"']{6,64}[\"']?",
        ],
    },
    {
        "type": "address",
        "label": "Address",
        "patterns": [
            r"[\u4e00-\u9fa5]{2,}(?:省|自治区)[\u4e00-\u9fa5]{2,}(?:市|自治州|盟)[\u4e00-\u9fa5]{2,}(?:区|县|市|旗)[\u4e00-\u9fa5\d]+(?:路|街|道|巷|弄)[\u4e00-\u9fa5\d]*号?",
            r"\d{1,5}\s+[A-Za-z\s]{2,25}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\.?(?:\s*,?\s*(?:Apt|Suite|Unit|#)\s*\d+)?",
        ],
    },
]


def _compile_patterns() -> List[Dict[str, Any]]:
    out = []
    for entry in REGEX_PATTERNS:
        # dateOfBirth 等含英文关键词的 pattern 需要 IGNORECASE
        patterns = entry["patterns"]
        flags = re.IGNORECASE if entry["type"] == "dateOfBirth" else 0
        out.append({
            "type": entry["type"],
            "label": entry["label"],
            "patterns": [re.compile(p, flags) for p in patterns],
        })
    return out


_COMPILED = _compile_patterns()


def _infer_risk_level(stype: str) -> RiskLevel:
    if stype in HIGH_RISK_TYPES:
        return "high"
    if stype in MEDIUM_RISK_TYPES:
        return "medium"
    return "low"


def _calculate_risk_score(items: List[Dict[str, Any]]) -> int:
    if not items:
        return 0
    type_count: dict[str, int] = {}
    for it in items:
        t = it["type"]
        type_count[t] = type_count.get(t, 0) + 1
    score = 0.0
    for t, count in type_count.items():
        w = RISK_WEIGHTS.get(t, 15)
        score += w + (count - 1) * w * 0.3
    if len(type_count) >= 2:
        score *= 1 + (len(type_count) - 1) * 0.15
    return max(0, min(100, round(score)))


def _generate_placeholder(stype: str, index: int) -> str:
    tag = PLACEHOLDER_MAP.get(stype, "PII")
    return f"[{tag}_{index}]"


def _is_overlapping(
    start: int, end: int, ranges: List[Tuple[int, int]]
) -> bool:
    for rs, re in ranges:
        if (start >= rs and start < re) or (end > rs and end <= re) or (start <= rs and end >= re):
            return True
    return False


def _is_valid_name_candidate(value: str, lang: str) -> bool:
    cleaned = value.strip().strip("\"'`")
    if not cleaned:
        return False
    lower = cleaned.lower()
    if any(c.isdigit() for c in cleaned):
        return False
    if "@" in cleaned or "http://" in lower or "https://" in lower:
        return False
    if "_" in cleaned or "/" in cleaned:
        return False

    if lang == "cn":
        if not re.fullmatch(r"[\u4e00-\u9fa5·]{2,6}", cleaned):
            return False
        if any(token in cleaned for token in NAME_STOPWORDS_CN):
            return False
        return True

    cleaned = re.sub(r"\s+", " ", cleaned)
    if not re.fullmatch(r"[A-Za-z]+(?:[ '-][A-Za-z]+){1,2}", cleaned):
        return False
    tokens = [tok for tok in re.split(r"[ '-]+", cleaned) if tok]
    if len(tokens) < 2 or len(tokens) > 3:
        return False
    if any(tok.lower() in NAME_STOPWORDS_EN for tok in tokens):
        return False
    if any(len(tok) < 2 for tok in tokens):
        return False
    if any(not tok[0].isupper() for tok in tokens):
        return False
    return True


def _detect_names_by_context(
    text: str, occupied_ranges: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    names: List[Dict[str, Any]] = []
    for entry in NAME_CONTEXT_PATTERNS:
        lang = entry["lang"]
        pattern = entry["pattern"]
        for m in pattern.finditer(text):
            value = m.group(1).strip().strip("\"'`")
            start_index = m.start(1)
            end_index = m.end(1)
            if _is_overlapping(start_index, end_index, occupied_ranges):
                continue
            if not _is_valid_name_candidate(value, lang):
                continue
            occupied_ranges.append((start_index, end_index))
            names.append({
                "type": "name",
                "label": "Name",
                "value": value,
                "startIndex": start_index,
                "endIndex": end_index,
            })
    return names


def detect_sensitive_local(text: str) -> Dict[str, Any]:
    """
    Local PII detection (same behavior as detectSensitiveLocal in api.ts).
    Returns a DetectionResult-shaped dict: originalText, sanitizedText, items, riskScore, riskLevel.
    """
    if not text or len(text) < 5:
        return {
            "originalText": text or "",
            "sanitizedText": text or "",
            "items": [],
            "riskScore": 0,
            "riskLevel": "low",
        }

    all_matches: List[Dict[str, Any]] = []
    matched_ranges: List[Tuple[int, int]] = []

    for entry in _COMPILED:
        stype = entry["type"]
        label = entry["label"]
        for pattern in entry["patterns"]:
            for m in pattern.finditer(text):
                value = m.group(0)
                start_index = m.start()
                end_index = m.end()
                if not _is_overlapping(start_index, end_index, matched_ranges):
                    matched_ranges.append((start_index, end_index))
                    all_matches.append({
                        "type": stype,
                        "label": label,
                        "value": value,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    })

    all_matches.extend(_detect_names_by_context(text, matched_ranges))

    all_matches.sort(key=lambda x: x["startIndex"])

    type_counters: Dict[str, int] = {}
    items: List[Dict[str, Any]] = []
    item_id = 0
    for m in all_matches:
        type_counters[m["type"]] = type_counters.get(m["type"], 0) + 1
        idx = type_counters[m["type"]]
        masked = _generate_placeholder(m["type"], idx)
        item_id += 1
        items.append({
            "id": str(item_id),
            "type": m["type"],
            "label": m["label"],
            "value": m["value"],
            "maskedValue": masked,
            "confidence": 85,
            "riskLevel": _infer_risk_level(m["type"]),
            "startIndex": m["startIndex"],
            "endIndex": m["endIndex"],
        })

    # 从后往前替换，避免偏移变化
    sanitized = text
    for it in sorted(items, key=lambda x: -x["startIndex"]):
        sanitized = (
            sanitized[: it["startIndex"]]
            + it["maskedValue"]
            + sanitized[it["endIndex"] :]
        )

    risk_score = _calculate_risk_score(items)
    risk_level: RiskLevel = (
        "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low"
    )

    return {
        "originalText": text,
        "sanitizedText": sanitized,
        "items": items,
        "riskScore": risk_score,
        "riskLevel": risk_level,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local PII detection (regex): output detected items, risk score, and masked text; no API call."
    )
    parser.add_argument("-i", "--input", type=str, default=None)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full JSON; otherwise only output sanitizedText.",
    )
    args = parser.parse_args()

    raw = args.input or ""
    if not raw.strip():
        print("Error: input is empty", file=sys.stderr)
        sys.exit(1)

    result = detect_sensitive_local(raw)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Status: local detection done", file=sys.stderr)
        print(f"riskScore: {result['riskScore']}, riskLevel: {result['riskLevel']}", file=sys.stderr)
        print(f"items: {len(result['items'])}", file=sys.stderr)
        print(result["sanitizedText"])


if __name__ == "__main__":
    main()
