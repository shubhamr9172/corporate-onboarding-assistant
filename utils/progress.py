import re
from typing import Dict

# Define keyword patterns for matching
TOPIC_KEYWORDS = {
    "Policy": [r"\bpolicy\b", r"\bcode of conduct\b", r"\brules\b", r"\bcompliance\b", r"\bleave\b", r"\bholiday\b"],
    "Benefits": [r"\binsurance\b", r"\bpf\b", r"\bprovident fund\b", r"\bbonus\b", r"\ballowance\b", r"\bmedical\b", r"\breimburse\b", r"\bgym\b"],
    "IT Setup": [r"\blaptop\b", r"\bvpn\b", r"\bemail\b", r"\btools\b", r"\bsoftware\b", r"\baccess\b", r"\bcredentials\b", r"\bpassword\b", r"\bwifi\b"],
    "Team": [r"\bmanager\b", r"\bteam\b", r"\borg chart\b", r"\breporting\b", r"\bdepartment\b", r"\bdepartment names\b"],
    "Payroll": [r"\bsalary\b", r"\bpayslip\b", r"\bctc\b", r"\bdeductions\b", r"\btax\b", r"\bwithholding\b", r"\bbank account\b"]
}

def update_topics_covered(current_message: str, current_topics: Dict[str, bool]) -> Dict[str, bool]:
    """
    Scans the current user message for keywords.
    If matches are found, updates the status of that onboarding topic to True.
    Never uses LLM calls. Pure Python string scanning.
    """
    updated_topics = current_topics.copy() if current_topics else {
        "Policy": False,
        "Benefits": False,
        "IT Setup": False,
        "Team": False,
        "Payroll": False
    }
    
    message_lower = current_message.lower()
    
    for topic, patterns in TOPIC_KEYWORDS.items():
        # If already completed, skip checks
        if updated_topics.get(topic):
            continue
            
        for pattern in patterns:
            if re.search(pattern, message_lower):
                updated_topics[topic] = True
                break  # Matched one keyword, move to next topic
                
    return updated_topics
