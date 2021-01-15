#!/usr/bin/env python3

import json
import os
from pprint import pprint
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


def format_reply_time(time):
    return humanize.naturaltime(
        datetime.utcnow() - datetime.strptime(time, "%Y-%m-%dT%H:%M:%SZ")
    )


tickets = call_freshdesk_api("tickets", filter="new_and_my_open")
for ticket in sorted(tickets, key=itemgetter("updated_at"), reverse=True):
    ticket = call_freshdesk_api("tickets/{}".format(ticket["id"]), include="company")
    conversations = call_freshdesk_api("tickets/{}/conversations".format(ticket["id"]))
    msgs = [m for m in conversations if not m["private"]]
    customer_replied = msgs[-1]["incoming"] if msgs else None
    last_reply = format_reply_time(msgs[-1]["created_at"]) if msgs else None
    company_name = ticket["company"]["name"]
    reply_desc = (
        "{} replied {}".format("Customer" if customer_replied else "Agent", last_reply)
        if last_reply
        else ""
    )
    print(
        "#{id} - {company_name} - {subject} {reply_desc}".format(
            reply_desc=reply_desc, company_name=company_name, **ticket
        )
    )
