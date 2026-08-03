import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)
sid = "s_mem_test"

# Round 1
print("=== Round 1 ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "我叫张三，在腾讯做产品经理，最近在研究AIGC",
    "mode": "chat",
    "command_mode": False,
    "session_id": sid,
})
print("AI:", resp.json()["answer"][:120])

# Round 2 - should remember
print("\n=== Round 2 ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "我叫什么名字？在哪个公司？",
    "mode": "chat",
    "command_mode": False,
    "session_id": sid,
})
print("AI:", resp.json()["answer"][:200])

# Round 3 - deeper recall
print("\n=== Round 3 ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "我在研究什么方向？",
    "mode": "chat",
    "command_mode": False,
    "session_id": sid,
})
print("AI:", resp.json()["answer"][:200])

client.delete("/api/v1/chat/sessions/" + sid)
print("\n=== Done ===")
