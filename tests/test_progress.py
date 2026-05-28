import pytest
from utils.progress import update_topics_covered


def test_update_topics_covered():
    initial_topics = {
        "Policy": False,
        "Benefits": False,
        "IT Setup": False,
        "Team": False,
        "Payroll": False,
    }

    # Policy match
    topics = update_topics_covered("What is the leave policy?", initial_topics)
    assert topics["Policy"] is True
    assert topics["Benefits"] is False

    # Benefits match
    topics2 = update_topics_covered("Tell me about health insurance", initial_topics)
    assert topics2["Benefits"] is True
    assert topics2["Policy"] is False

    # Multiple match
    topics3 = update_topics_covered(
        "How do I request a laptop and check my salary?", initial_topics
    )
    assert topics3["IT Setup"] is True
    assert topics3["Payroll"] is True
    assert topics3["Policy"] is False

    # No match
    topics4 = update_topics_covered("Hello there", initial_topics)
    assert all(not v for v in topics4.values())

    # Retain existing topics
    existing_topics = {
        "Policy": True,
        "Benefits": False,
        "IT Setup": False,
        "Team": False,
        "Payroll": False,
    }
    topics5 = update_topics_covered("How do I setup VPN?", existing_topics)
    assert topics5["Policy"] is True
    assert topics5["IT Setup"] is True
    assert topics5["Benefits"] is False
