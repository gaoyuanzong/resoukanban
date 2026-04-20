# Phase 2: Web 管理界面

## 启动
```bash
python3 server.py
```
然后访问 http://localhost:8080 或 http://<本机IP>:8080

## 功能
- 左侧：点击任意模式查看预览
- 中间：PNG 预览大图 + 推送按钮
- 右侧：当前配置 + 推送历史
- 支持修改配置后即时预览

## API 端点
- `GET /api/modes` — 所有模式列表
- `GET /api/preview?mode=xxx&page=3` — PNG 预览图
- `GET /api/push?mode=xxx&page=3` — 推送到墨水屏
- `GET /api/history` — 推送历史 JSON
- `GET /api/config` — 当前配置
- `POST /api/config` — 更新配置（JSON body）
