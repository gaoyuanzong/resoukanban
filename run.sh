#!/bin/bash
cd /home/gaoyuan/workspace/resoukanban
set -a
source .env
set +a
echo "=== run.sh start $(date) ===" >> /tmp/kanban.log
/usr/bin/python3 main.py >> /tmp/kanban.log 2>&1
echo "=== run.sh end $(date) ===" >> /tmp/kanban.log
