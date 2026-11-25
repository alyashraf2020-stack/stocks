"""Describe supported capabilities without extending, or calling, the MCP allowlist."""

from app.integrations.thndr_mcp import READ_TOOLS

DOCUMENTED = {
    "create": "send_trade_proposal",
    "pending": "get_pending_proposals",
    "status": "get_proposal_status",
    "cancel": "cancel_proposal",
    "orders": "get_orders",
    "fees": "calculate_order_fees",
}


def capabilities(connection):
    granted = (
        sorted(set(connection.available) & READ_TOOLS)
        if connection.status == "CONNECTED"
        else []
    )
    return {
        "connection": connection.status,
        "scopes": connection.permissions if connection.status == "CONNECTED" else [],
        "granted_reads": granted,
        "proposal_grant": "UNKNOWN"
        if connection.status != "CONNECTED"
        else "NOT_GRANTED_IN_READ_SESSION",
        "documented": DOCUMENTED,
        "official_schema_verified": False,
        "creation_supported_by_build": False,
        "order_list_available": "get_orders" in granted,
        "correlation_supported": False,
    }


def status_view(proposal):
    # The existing authorized order list does not return a verified reference
    # that can be attributed to a local draft. Keep account reads independent.
    return {
        "submission": "NOT_SUBMITTED",
        "proposal_status": "UNKNOWN",
        "execution_status": "UNKNOWN",
        "broker_reference": None,
        "last_authoritative": None,
        "draft": proposal.id,
    }
