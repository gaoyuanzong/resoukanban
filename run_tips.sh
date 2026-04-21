#!/bin/bash
cd /home/gaoyuan/workspace/resoukanban
set -a
source .env
set +a
/usr/bin/python3 generate_tips.py >> /tmp/kanban.log 2>&1
/usr/bin/python3 /tmp/gen_pool.py >> /tmp/kanban.log 2>&1
echo "$(date) 内容池生成完毕" >> /tmp/kanban.log 2>&1
