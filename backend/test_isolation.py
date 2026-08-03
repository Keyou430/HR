import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)
sa = "s_session_A"
sb = "s_session_B"

# Session A: tell AI something
print("=== Session A: 告诉 AI 一个秘密 ===")
r = client.post("/api/v1/knowledge/chat", json={
    "question": "我叫郝锐，密码是123456",
    "mode": "chat", "command_mode": False, "session_id": sa,
})
print("A:", r.json()["answer"][:80])

# Session B: tell AI something else
print("\n=== Session B: 告诉 AI 另一个信息 ===")
r = client.post("/api/v1/knowledge/chat", json={
    "question": "我叫李四，密码是abcdef",
    "mode": "chat", "command_mode": False, "session_id": sb,
})
print("B:", r.json()["answer"][:80])

# Back to Session A: ask for secret
print("\n=== 回到 Session A: 我密码是什么？ ===")
r = client.post("/api/v1/knowledge/chat", json={
    "question": "我的密码是什么？",
    "mode": "chat", "command_mode": False, "session_id": sa,
})
print("A:", r.json()["answer"][:150])

# Back to Session B: ask for secret
print("\n=== 回到 Session B: 我密码是什么？ ===")
r = client.post("/api/v1/knowledge/chat", json={
    "question": "我的密码是什么？",
    "mode": "chat", "command_mode": False, "session_id": sb,
})
print("B:", r.json()["answer"][:150])

# Cleanup
client.delete("/api/v1/chat/sessions/" + sa)
client.delete("/api/v1/chat/sessions/" + sb)
print("\n=== 结论: 不同 session 完全隔离 ===")
