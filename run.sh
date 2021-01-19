#!/bin/bash

cd $(dirname $0)

source .envrc
venv/bin/python freshdeskbot.py
