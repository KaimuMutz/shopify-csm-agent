"""Slack tool: post draft replies for human review and listen for approvals."""

from __future__ import annotations

from typing import Any

from slack_sdk.web.async_client import AsyncWebClient


class SlackTool:
    def __init__(self, bot_token: str, review_channel: str) -> None:
        self._client = AsyncWebClient(token=bot_token)
        self._channel = review_channel

    async def post_review(
        self,
        *,
        conversation_id: str,
        customer_email: str,
        intent: str,
        confidence: float,
        original_message: str,
        draft_reply: str,
        context_summary: str,
    ) -> str:
        """Post a Block Kit message with Approve / Edit / Reject actions.

        Returns the Slack message timestamp (used as a correlation handle).
        """
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"CSM draft · {intent} · conf {confidence:.2f}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer*\n{customer_email}"},
                    {"type": "mrkdwn", "text": f"*Conversation*\n`{conversation_id}`"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Original message*\n>{original_message}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Context gathered*\n{context_summary}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Draft reply*\n```{draft_reply}```"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve & send"},
                        "style": "primary",
                        "action_id": "csm_approve",
                        "value": conversation_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit"},
                        "action_id": "csm_edit",
                        "value": conversation_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "csm_reject",
                        "value": conversation_id,
                    },
                ],
            },
        ]

        resp = await self._client.chat_postMessage(channel=self._channel, blocks=blocks, text="CSM draft")
        return resp["ts"]
