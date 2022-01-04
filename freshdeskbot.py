#!/usr/bin/env python3

import json
import os
import requests
import humanize
from operator import itemgetter
from itertools import groupby
from datetime import datetime
from collections import defaultdict

FRESHDESK_KEY = os.environ["FRESHDESK_KEY"]
FRESHDESK_URL = os.environ["FRESHDESK_URL"]
FRESHDESK_AGENT_MAPPING = os.environ["FRESHDESK_AGENT_MAPPING"]
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


agent_slack_mapping = {
    int(agent): channel
    for agent, channel in (i.split(":") for i in FRESHDESK_AGENT_MAPPING.split(","))
}


def slack_message_template(agent):
    return {
        "channel": agent_slack_mapping[agent],
        "username": "Freshdesk summary",
        "icon_emoji": ":freshdesk:",
        "attachments": [],
        "text": "",
    }


def status_query():
    all_statuses = call_freshdesk_api("ticket_fields", type="default_status")[0][
        "choices"
    ]
    ignored_statuses = {"Resolved", "Closed"}
    statuses = [k for k, v in all_statuses.items() if v[0] not in ignored_statuses]

    return '"{}"'.format(" OR ".join("status:{}".format(str(i)) for i in statuses))


tickets = call_freshdesk_api("search/tickets", query=status_query())["results"]
messages_by_agent = defaultdict(list)
awaiting_reply = defaultdict(int)
new_tickets = 0
for agent, tickets in groupby(
    sorted(tickets, key=lambda t: t["responder_id"] or 0, reverse=True),
    itemgetter("responder_id"),
):
    for i, ticket in enumerate(
        sorted(tickets, key=itemgetter("updated_at"), reverse=True)
    ):
        if agent and agent not in agent_slack_mapping:
            continue
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
            awaiting_reply[agent] += 1
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
        messages_by_agent[agent].append(
            {
                "fallback": fallback,
                "text": "<https://{url}.freshdesk.com/a/tickets/{id}|#{id}> *{company}*: {subject}".format(
                    url=FRESHDESK_URL,
                    id=ticket["id"],
                    company=company,
                    subject=ticket["subject"],
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

for agent in [k for k in messages_by_agent.keys() if k]:
    # Generate a nicer summary for e.g. notifications
    slack_message = slack_message_template(agent)
    if awaiting_reply[agent]:
        slack_message["text"] += "{} ticket{} awaiting reply.".format(
            humanize.apnumber(awaiting_reply[agent]).title(),
            "s" if awaiting_reply[agent] > 1 else "",
        )
    if new_tickets:
        slack_message["text"] += " {} new ticket{}.".format(
            humanize.apnumber(new_tickets).title(), "s" if new_tickets > 1 else ""
        )
    slack_message["attachments"] = messages_by_agent[agent]
    if messages_by_agent[None]:  # unassigned tickets
        slack_message["attachments"].extend(messages_by_agent[None])
    call_slack_webhook(slack_message)
