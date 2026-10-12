"""Defense-in-depth text redaction and narrowly scoped abuse rejection; no command execution."""

import re


# --- Recognizable secrets are replaced before prompts reach providers/history. ---
PATTERNS = (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"\bAIza[\w-]{30,}\b",
    r"\bsk-(?:or-v1-)?[\w-]{16,}\b",
    r"\b(?:ghp_|github_pat_)[\w]{20,}\b",
    # Quoted assignments/JSON can contain spaces or escaped quotes; redact the complete value first.
    r"""(?i)\b(?:password|api[_-]?key|access[_-]?token|secret)["']?\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""",
    r"(?i)\b(?:password|api[_-]?key|access[_-]?token|secret)[\"']?\s*[:=]\s*[\"']?[^\s\"',;]+",
    r"(?i)\bBearer\s+[A-Za-z0-9._-]{16,}",
)


def redact(text: str) -> tuple[str, bool]:
    """Return redacted text and a changed flag; limited patterns are not comprehensive DLP."""
    clean = text
    for pattern in PATTERNS:
        clean = re.sub(pattern, "[REDACTED SECRET]", clean)
    return clean, clean != text


def refusal(question: str) -> str | None:
    """Reject explicit credential theft/malware creation; ordinary command explanation remains allowed."""
    lowered = question.casefold()
    malicious = (
        r"\b(?:write|create|build|deploy)\s+(?:(?:a|an|working|functional|python|windows|code|script|for|that|is)\s+){0,5}"
        r"(?:ransomware|credential stealer|password stealer)\b",
        r"\b(?:steal|exfiltrate)\b.{0,35}\b(?:passwords|credentials|api keys)\b",
    )
    if any(re.search(pattern, lowered) for pattern in malicious):
        return "I can help explain the risk or secure a system, but I cannot help create malware or steal credentials."
    return None
