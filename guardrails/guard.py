import re
import os
import logging
import unicodedata
from typing import Tuple, List, Dict, Any

logger = logging.getLogger("app.guard")

# Regex pattern definitions for safety checks
PII_PATTERNS = [
    r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # Credit Cards
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",  # Emails (warn, but allow support email helpdesk@company.com)
    r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",  # Phone numbers
    r"\b(?:ssn|passport|password|pwd|credentials|secret)\s*[:=]\s*\S+",  # Potential secrets leakage
]

INJECTION_KEYWORDS = [
    "ignore all previous instructions",
    "ignore previous instructions",
    "system prompt",
    "print the system instructions",
    "you must now act as",
    "new instructions",
    "forget what we talked about",
]

TOXIC_KEYWORDS = ["bastard", "idiot", "dumb", "fool", "shit", "fuck", "bitch"]

# Read from env configuration (Issue #8)
BUDGET_LIMIT_USD = float(os.getenv("SESSION_BUDGET_USD", "0.50"))


def validate_input(message: str, current_cost: float) -> Tuple[bool, str]:
    """
    Sanitizes user input for injections, toxic comments, PII leaks, and budget overruns.
    Returns (is_safe, failure_reason).
    """
    # 1. Budget check
    if current_cost >= BUDGET_LIMIT_USD:
        logger.warning(
            f"Input blocked: budget limit reached (${current_cost:.4f} >= ${BUDGET_LIMIT_USD:.2f})."
        )
        return (
            False,
            "Your conversation session has reached its budget limit. Please reset the chat or escalate to HR.",
        )

    # Unicode homoglyph, diacritics, and whitespace normalization to prevent bypasses (Issue #6)
    message_norm = unicodedata.normalize("NFKC", message)
    message_nfd = unicodedata.normalize("NFD", message_norm)
    message_no_accents = "".join(
        c for c in message_nfd if unicodedata.category(c) != "Mn"
    )
    message_clean = re.sub(r"\s+", " ", message_no_accents).strip()
    message_lower = message_clean.lower()

    # 2. Prompt Injection check
    for kw in INJECTION_KEYWORDS:
        if kw in message_lower:
            logger.warning(f"Input blocked: injection keyword detected ('{kw}').")
            return (
                False,
                "Invalid query: Direct instruction adjustments are not permitted.",
            )

    # 3. Toxicity check
    for kw in TOXIC_KEYWORDS:
        if kw in message_lower:
            logger.warning(f"Input blocked: toxic content detected ('{kw}').")
            return False, "Message blocked: Please maintain professional language."

    # 4. PII check
    # We redact/block queries trying to send sensitive credentials
    for pattern in PII_PATTERNS:
        matches = re.findall(pattern, message_clean, re.IGNORECASE)
        # Filter out company email helpdesk reference
        valid_matches = [m for m in matches if "helpdesk@company.com" not in str(m)]
        if valid_matches:
            logger.warning("Input blocked: potential PII or secrets leak detected.")
            return (
                False,
                "Message blocked: Do not submit password text or credential numbers.",
            )

    return True, "Input validation passed."


def validate_output(answer: str, source_docs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Sanitizes output response. Checks for hallucinations (ensuring support in sources)
    and prevents leaking system tokens or keys.
    Returns (is_safe, sanitized_response_or_reason).
    """
    answer_clean = answer.strip()

    # 1. Check for API key / credential patterns in LLM response
    api_key_pattern = r"(?:AIzaSy[A-Za-z0-9-_]{33}|key-[a-zA-Z0-9]{32})"
    if re.search(api_key_pattern, answer_clean):
        logger.error("Output blocked: LLM attempted to leak an internal API key.")
        return False, "Response blocked: System safety filter triggered."

    # 2. Check grounding: If context is empty but LLM answers with facts, it might be hallucinated.
    # If the answer is "I don't know", allow it.
    is_idk = (
        "don't know" in answer_clean.lower()
        or "apologize" in answer_clean.lower()
        or "escalation ticket" in answer_clean.lower()
    )
    if not source_docs and not is_idk:
        logger.warning(
            "Output warning: LLM answered without grounding context. Appending warning."
        )
        return (
            True,
            answer_clean
            + "\n\n*Note: This answer is generated from general defaults as no specific onboarding documents were retrieved.*",
        )

    return True, answer_clean
