from jira import JIRA
from dataclasses import dataclass
import concurrent.futures
import re


@dataclass
class TicketDetails:
    key: str
    summary: str
    description: str
    issue_type: str
    status: str
    priority: str
    assignee: str
    reporter: str
    labels: list
    components: list
    acceptance_criteria: str
    comments: list
    subtasks: list
    linked_issues: list
    raw: dict


def _normalise_url(url: str) -> str:
    """Ensure URL has https:// prefix and no trailing slash."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _is_cloud(url: str) -> bool:
    return "atlassian.net" in url.lower()


class JiraClient:
    def __init__(self):
        self._client = None

    def login(self, url: str, username: str, password: str) -> bool:
        """Authenticate with Jira Cloud or Server/Data Center."""
        url = _normalise_url(url)
        cloud = _is_cloud(url)

        def _connect():
            return JIRA(
                server=url,
                basic_auth=(username, password),
                max_retries=0,
                timeout=10,
            )

        # Run with explicit timeout so the UI never hangs forever
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_connect)
            try:
                client = future.result(timeout=20)
            except concurrent.futures.TimeoutError:
                raise ConnectionError(
                    f"Connection timed out after 20 seconds.\n"
                    f"Check that '{url}' is reachable and your network/VPN is active."
                )
            except Exception as e:
                err = str(e)
                # Produce human-friendly error messages
                if "401" in err or "Unauthorized" in err or "CAPTCHA" in err.lower():
                    if cloud:
                        raise ConnectionError(
                            "Authentication failed (401).\n\n"
                            "⚠️  Jira Cloud (atlassian.net) requires an API Token, not your password.\n"
                            "Generate one at: https://id.atlassian.com/manage-profile/security/api-tokens\n"
                            "Then use it in the Password field."
                        )
                    raise ConnectionError(
                        "Authentication failed (401).\nCheck your username and password/PAT."
                    )
                if "403" in err or "Forbidden" in err:
                    raise ConnectionError(
                        "Access denied (403).\nYour account may lack permissions or IP restrictions are in place."
                    )
                if "404" in err or "Not Found" in err:
                    raise ConnectionError(
                        f"Jira not found at '{url}' (404).\nDouble-check the server URL."
                    )
                if "Name or service not known" in err or "getaddrinfo" in err or "nodename" in err:
                    raise ConnectionError(
                        f"Cannot reach '{url}'.\nCheck the URL spelling and your internet/VPN connection."
                    )
                if "SSL" in err or "certificate" in err.lower():
                    raise ConnectionError(
                        f"SSL/TLS error connecting to '{url}'.\n"
                        "If using a self-signed cert, contact your admin for the CA certificate."
                    )
                raise ConnectionError(f"Login failed: {err}")

        # Verify by fetching current user
        try:
            client.myself()
        except Exception as e:
            raise ConnectionError(f"Connected but failed to verify account: {e}")

        self._client = client
        return True

    @property
    def connected(self) -> bool:
        return self._client is not None

    def fetch_ticket(self, ticket_key: str) -> TicketDetails:
        """Fetch full ticket details from Jira."""
        if not self._client:
            raise RuntimeError("Not connected to Jira")

        issue = self._client.issue(ticket_key, expand="renderedFields")
        fields = issue.fields

        # Extract acceptance criteria from common custom field patterns
        acceptance_criteria = ""
        raw_fields = issue.raw.get("fields", {})
        for field_name, value in raw_fields.items():
            if isinstance(value, str) and field_name.startswith("customfield_"):
                # Heuristic: AC fields tend to be longer text with criteria keywords
                if any(kw in (value or "").lower() for kw in ["given", "when", "then", "accept", "criteria", "scenario"]):
                    acceptance_criteria = value
                    break

        # If no custom field found, try to extract from description
        if not acceptance_criteria and fields.description:
            desc_lower = fields.description.lower()
            for marker in ["acceptance criteria", "ac:", "given", "expected"]:
                idx = desc_lower.find(marker)
                if idx != -1:
                    acceptance_criteria = fields.description[idx:]
                    break

        comments = []
        if hasattr(fields, "comment") and fields.comment:
            for c in fields.comment.comments:
                comments.append({
                    "author": str(c.author),
                    "body": c.body,
                    "created": str(c.created),
                })

        subtasks = []
        if hasattr(fields, "subtasks") and fields.subtasks:
            for st in fields.subtasks:
                subtasks.append({
                    "key": st.key,
                    "summary": st.fields.summary,
                    "status": str(st.fields.status),
                })

        linked_issues = []
        if hasattr(fields, "issuelinks") and fields.issuelinks:
            for link in fields.issuelinks:
                linked = {}
                if hasattr(link, "outwardIssue"):
                    linked = {
                        "key": link.outwardIssue.key,
                        "summary": link.outwardIssue.fields.summary,
                        "type": link.type.outward,
                    }
                elif hasattr(link, "inwardIssue"):
                    linked = {
                        "key": link.inwardIssue.key,
                        "summary": link.inwardIssue.fields.summary,
                        "type": link.type.inward,
                    }
                if linked:
                    linked_issues.append(linked)

        return TicketDetails(
            key=ticket_key,
            summary=fields.summary or "",
            description=fields.description or "",
            issue_type=str(fields.issuetype) if fields.issuetype else "",
            status=str(fields.status) if fields.status else "",
            priority=str(fields.priority) if fields.priority else "",
            assignee=str(fields.assignee) if fields.assignee else "Unassigned",
            reporter=str(fields.reporter) if fields.reporter else "",
            labels=list(fields.labels) if fields.labels else [],
            components=[str(c) for c in fields.components] if fields.components else [],
            acceptance_criteria=acceptance_criteria,
            comments=comments,
            subtasks=subtasks,
            linked_issues=linked_issues,
            raw=issue.raw,
        )

    def format_for_ai(self, ticket: TicketDetails) -> str:
        """Format ticket details into a prompt-friendly string."""
        parts = [
            f"# Jira Ticket: {ticket.key}",
            f"## Summary\n{ticket.summary}",
            f"## Type: {ticket.issue_type} | Status: {ticket.status} | Priority: {ticket.priority}",
            f"## Description\n{ticket.description}",
        ]

        if ticket.acceptance_criteria:
            parts.append(f"## Acceptance Criteria\n{ticket.acceptance_criteria}")

        if ticket.labels:
            parts.append(f"## Labels: {', '.join(ticket.labels)}")

        if ticket.components:
            parts.append(f"## Components: {', '.join(ticket.components)}")

        if ticket.subtasks:
            sub_lines = [f"- [{s['key']}] {s['summary']} ({s['status']})" for s in ticket.subtasks]
            parts.append(f"## Subtasks\n" + "\n".join(sub_lines))

        if ticket.comments:
            comment_lines = [f"### {c['author']} ({c['created']})\n{c['body']}" for c in ticket.comments[-5:]]
            parts.append(f"## Recent Comments\n" + "\n".join(comment_lines))

        return "\n\n".join(parts)
