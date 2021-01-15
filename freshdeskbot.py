#!/usr/bin/env python3

import json
import os
import urllib.request
from base64 import b64encode
from pprint import pprint
from operator import itemgetter
from datetime import datetime

FRESHDESK_KEY = os.environ["FRESHDESK_KEY"]
FRESHDESK_URL = os.environ["FRESHDESK_URL"]
FRESHDESK_AGENT_ID = os.environ["FRESHDESK_AGENT_ID"]
SLACK_URL = os.environ["SLACK_URL"]
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]


def call_freshdesk_api(url):
    root_url = "https://{}.freshdesk.com/api/v2/".format(FRESHDESK_URL)

    auth_header = "Basic " + b64encode("{}:X".format(FRESHDESK_KEY).encode()).decode()
    request = urllib.request.Request("{}{}".format(root_url, url))
    request.add_header("Authorization", auth_header)
    response = urllib.request.urlopen(request)
    return json.load(response)


def format_reply_time(time):
    dt = datetime.strptime(time, "%Y-%m-%dT%H:%M:%SZ")
    ago = (datetime.utcnow() - dt).total_seconds()

    months = int(ago // (60 * 60 * 24 * 28))  # 28 days
    weeks = int(ago // (60 * 60 * 24 * 7) ) # 7 days
    days = int(ago // (60 * 60 * 24))  # 1 day
    hours = int(ago // (60 * 60))  # 1 hour

    readable = (
        "{months} months ago"
        if months
        else "{weeks} weeks ago"
        if weeks
        else "{days} days ago"
        if days
        else "{hours} hours ago"
        if hours
        else "just now"
    )
    return readable.format(months=months, weeks=weeks, days=days, hours=hours)


tickets = call_freshdesk_api("tickets?filter=new_and_my_open")
for ticket in sorted(tickets, key=itemgetter("id"), reverse=True):
    ticket = call_freshdesk_api(
        "tickets/{}?include=conversations,company".format(ticket["id"])
    )
    msgs = [m for m in ticket["conversations"] if not m["private"]]
    customer_replied = msgs[-1]["incoming"] if msgs else None
    last_reply = format_reply_time(msgs[-1]["created_at"]) if msgs else None
    company_name = ticket["company"]["name"]
    print(
        "#{id} - {company_name} - {subject} {responder_id} {customer_replied} {last_reply}".format(
            customer_replied=customer_replied,
            last_reply=last_reply,
            company_name=company_name,
            **ticket
        )
    )
