import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)
sid = "s_ctx_test_001"

# Round 1: Tell AI something
print("=== Round 1: 告诉 AI 一个事实 ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "我叫郝锐，我是物理学院的老师",
    "mode": "chat",
    "command_mode": False,
    "session_id": sid,
})
print("AI:", resp.json().get("answer", "")[:100])

# Persist both messages (simulating frontend sync)
client.post("/api/v1/chat/messages", json={
    "session_id": sid, "role": "user",
    "content": "我叫郝锐，我是物理学院的老师", "title": "上下文记忆测试",
})
client.post("/api/v1/chat/messages", json={
    "session_id": sid, "role": "assistant",
    "content": resp.json().get("answer", ""),
})

# Round 2: Ask AI to recall
print()
print("=== Round 2: 追问之前的信息 ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "我叫什么名字？我是哪个学院的？",
    "mode": "chat",
    "command_mode": False,
    "session_id": sid,
})
print("AI:", resp.json().get("answer", "")[:200])

# Cleanup
client.delete("/api/v1/chat/sessions/" + sid)
print()
print("=== Done ===")
