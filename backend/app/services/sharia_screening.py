from datetime import timedelta
from decimal import Decimal

from app.schemas.sharia import METHOD, METHOD_URL

RULES = {
    "noncompliant_income": Decimal(".05"),
    "interest_debt": Decimal(".33"),
    "interest_investments": Decimal(".33"),
    "liquid_assets": Decimal(".70"),
}


def evaluate_screen(evidence, today):
    result = {
        "status": "UNVERIFIED",
        "method": METHOD,
        "method_url": METHOD_URL,
        "limits": RULES,
        "ratios": {},
        "reasons": [],
        "evidence": evidence,
    }
    if evidence is None:
        result["reasons"].append("NO_REVIEWED_EVIDENCE")
        return result
    if not today - timedelta(days=183) <= evidence.reviewed_on <= today:
        result["reasons"].append("REVIEW_OUTDATED")
        return result
    if evidence.ordinary_share is not True:
        result["reasons"].append(
            "ORDINARY_SHARE_UNVERIFIED"
            if evidence.ordinary_share is None
            else "OUTSIDE_METHOD_SCOPE"
        )
        return result
    if evidence.activity == "PROHIBITED":
        result.update(status="NON_COMPLIANT", reasons=["PROHIBITED_ACTIVITY"])
        return result
    if evidence.activity != "PERMITTED":
        result["reasons"].append("ACTIVITY_UNVERIFIED")
    if (
        not evidence.financial_source
        or not evidence.period_end
        or not today - timedelta(days=365)
        <= evidence.period_end
        <= evidence.reviewed_on
    ):
        result["reasons"].append("FINANCIALS_MISSING_OR_OUTDATED")
        return result
    finance_base = (
        max(evidence.total_assets, evidence.average_market_value)
        if (
            evidence.total_assets
            and evidence.average_market_value
            and evidence.market_value_source
        )
        else None
    )
    denominators = {
        "noncompliant_income": evidence.total_revenue,
        "interest_debt": finance_base,
        "interest_investments": finance_base,
        "liquid_assets": evidence.total_assets,
    }
    exceeded = []
    for name, limit in RULES.items():
        numerator, denominator = getattr(evidence, name), denominators[name]
        if numerator is None or denominator is None:
            result["reasons"].append(f"MISSING_{name.upper()}")
            continue
        result["ratios"][name] = numerator / denominator
        if numerator > limit * denominator:
            exceeded.append(f"EXCEEDED_{name.upper()}")
    if exceeded:
        result.update(status="NON_COMPLIANT", reasons=exceeded + result["reasons"])
    elif not result["reasons"]:
        result.update(status="COMPLIANT", reasons=["PASSED_ALL_CHECKS"])
    return result
