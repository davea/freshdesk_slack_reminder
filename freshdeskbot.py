#!/usr/bin/env python3

import json
import os
import requests
import humanize
from operator import itemgetter
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
    "text": "*<https://{}.freshdesk.com/a/tickets/filters/search?orderBy=updated_at&orderType=desc&q[]=agent%3A%5B0%5D&q[]=status%3A%5B0%5D&ref=all_tickets|Your open Freshdesk tickets>*".format(
        FRESHDESK_URL
    ),
    "attachments": [],
}

tickets = call_freshdesk_api("tickets", filter="new_and_my_open")
for ticket in sorted(tickets, key=itemgetter("updated_at"), reverse=True):
    ticket = call_freshdesk_api("tickets/{}".format(ticket["id"]), include="company")
    conversations = call_freshdesk_api("tickets/{}/conversations".format(ticket["id"]))
    msgs = [m for m in conversations if not m["private"]]
    customer_replied = msgs[-1]["incoming"] if msgs else None
    last_reply = format_reply_time(msgs[-1]["created_at"]) if msgs else None
    company = ticket["company"]["name"]
    reply_desc = (
        "{} replied {}".format("Customer" if customer_replied else "Agent", last_reply)
        if last_reply
        else ""
    )
    fallback = "#{id} - {company_name} - {subject} {reply_desc}".format(
        reply_desc=reply_desc, company_name=company, **ticket
    )
    slack_message["attachments"].append(
        {
            "fallback": fallback,
            "text": "<https://{url}.freshdesk.com/a/tickets/{id}|#{id}> {company}".format(
                url=FRESHDESK_URL, id=ticket["id"], company=company
            ),
            "pretext": "",
            "color": "#d00000" if customer_replied else "#00d000",
            "fields": [
                {
                    "title": ticket["subject"],
                    "value": reply_desc,
                },
            ],
        }
    )

call_slack_webhook(slack_message)
