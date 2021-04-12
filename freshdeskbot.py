#!/usr/bin/env python3

import json
import os
import requests
import humanize
from operator import itemgetter
from itertools import groupby
from datetime import datetime

FRESHDESK_KEY = os.environ["FRESHDESK_KEY"]
FRESHDESK_URL = os.environ["FRESHDESK_URL"]
FRESHDESK_AGENT_ID = os.environ["FRESHDESK_AGENT_ID"]
SLACK_URL = os.environ["SLACK_URL"]
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]


def call_freshdesk_api(url, add_root=True, **kwargs):
    root_url = "https://{}.freshdesk.com/api/v2/".format(FRESHDESK_URL)
    if add_root:
        url = "{}{}".format(root_url, url)
    auth = (FRESHDESK_KEY, "X")

    response = requests.get(url, auth=auth, params=kwargs)
    results = response.json()

    if response.links.get("next"):
        results.extend(
            call_freshdesk_api(response.links["next"]["url"], add_root=False)
        )

    return results


def call_slack_webhook(payload):
    requests.post(SLACK_URL, data={"payload": json.dumps(payload)})


def format_reply_time(time):
    return humanize.naturaltime(
        datetime.utcnow() - datetime.strptime(time, "%Y-%m-%dT%H:%M:%SZ")
    )


slack_message = {
    "channel": SLACK_CHANNEL,
    "username": "Freshdesk summary",
    "icon_emoji": ":freshdesk:",
    "attachments": [],
    "text": "",
}

tickets = call_freshdesk_api("tickets", filter="new_and_my_open")
awaiting_reply = 0
new_tickets = 0
for agent, tickets in groupby(
    sorted(tickets, key=lambda t: t["responder_id"] or 0, reverse=True),
    itemgetter("responder_id"),
):
    for i, ticket in enumerate(
        sorted(tickets, key=itemgetter("updated_at"), reverse=True)
    ):
        pretext = ""
        if i == 0:
            if agent:
                pretext = "*<https://{}.freshdesk.com/a/tickets/filters/search?orderBy=updated_at&orderType=desc&q[]=agent%3A%5B0%5D&q[]=status%3A%5B0%5D&ref=all_tickets|Your unresolved tickets>*".format(
                    FRESHDESK_URL
                )
            else:
                pretext = "*<https://{}.freshdesk.com/a/tickets/filters/search?orderBy=updated_at&orderType=desc&q[]=agent%3A%5B-1%5D&q[]=status%3A%5B0%5D&ref=all_tickets|New & unassigned tickets>*".format(
                    FRESHDESK_URL
                )

        ticket = call_freshdesk_api(
            "tickets/{}".format(ticket["id"]), include="company"
        )
        conversations = call_freshdesk_api(
            "tickets/{}/conversations".format(ticket["id"])
        )
        msgs = [m for m in conversations if not m["private"]]
        customer_replied = (
            msgs[-1]["incoming"] if msgs else True
        )  # if no conversations assume it's a new incoming ticket
        if customer_replied and agent:
            awaiting_reply += 1
        if customer_replied and not agent:
            new_tickets += 1
        last_reply = format_reply_time(msgs[-1]["created_at"]) if msgs else None
        company = ticket["company"].get("name", "Unknown")
        reply_desc = (
            "{} replied {}".format(
                "Customer" if customer_replied else "Agent", last_reply
            )
            if last_reply
            else ""
        )
        fallback = "#{id} - {company_name} - {subject} {reply_desc}".format(
            reply_desc=reply_desc, company_name=company, **ticket
        )
        slack_message["attachments"].append(
            {
                "fallback": fallback,
                "text": "<https://{url}.freshdesk.com/a/tickets/{id}|#{id}> *{company}*: {subject}".format(
                    url=FRESHDESK_URL, id=ticket["id"], company=company, subject=ticket['subject']
                ),
                "pretext": pretext,
                "color": "#d00000" if customer_replied else "#00d000",
                "fields": [
                    {
                        "value": reply_desc,
                    },
                ],
            }
        )

# Generate a nicer summary for e.g. notifications
if awaiting_reply:
    slack_message["text"] += "{} ticket{} awaiting reply. ".format(
        humanize.apnumber(awaiting_reply).title(), "s" if awaiting_reply > 1 else ""
    )
if new_tickets:
    slack_message["text"] += "{} new ticket{}.".format(
        humanize.apnumber(new_tickets).title(), "s" if new_tickets > 1 else ""
    )

call_slack_webhook(slack_message)
