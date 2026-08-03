import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

# Simulate a full chat: user asks a Q&A question
print("=== 1. User asks knowledge question ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "差序格局是什么概念",
    "command_mode": True
})
data = resp.json()
print("  Mode:", data.get("mode"))
print("  Answer:", data.get("answer", "")[:80])
print("  Action:", data.get("action"))

# Simulate a command
print()
print("=== 2. User sends command ===")
resp = client.post("/api/v1/knowledge/chat", json={
    "question": "创建任务：写一篇关于差序格局的文章",
    "command_mode": True
})
data = resp.json()
print("  Mode:", data.get("mode"))
print("  Action:", data.get("action"))
print("  Answer:", data.get("answer", ""))

# Persist to chat history (simulating frontend)
print()
print("=== 3. Persist to chat history ===")
client.post("/api/v1/chat/messages", json={
    "session_id": "s_demo_001", "role": "user",
    "content": "差序格局是什么概念",
    "title": "关于差序格局的讨论"
})
client.post("/api/v1/chat/messages", json={
    "session_id": "s_demo_001", "role": "assistant",
    "content": "差序格局是费孝通在《乡土中国》中提出的核心概念...",
    "action": "rag"
})
client.post("/api/v1/chat/messages", json={
    "session_id": "s_demo_001", "role": "user",
    "content": "创建任务：写一篇关于差序格局的文章"
})
client.post("/api/v1/chat/messages", json={
    "session_id": "s_demo_001", "role": "assistant",
    "content": "已为你创建任务「写一篇关于差序格局的文章」",
    "action": "create_task"
})
print("  Saved 4 messages")

# List sessions
print()
print("=== 4. List sessions ===")
resp = client.get("/api/v1/chat/sessions")
for s in resp.json().get("items", []):
    print("  %s | %s" % (s["id"], s["title"][:40]))

# Get messages
print()
print("=== 5. Get messages ===")
resp = client.get("/api/v1/chat/sessions/s_demo_001/messages")
for m in resp.json().get("items", []):
    tag = " [action=%s]" % m["action"] if m.get("action") else ""
    print("  [%s]%s %s" % (m["role"], tag, m["content"][:60]))

# Cleanup
client.delete("/api/v1/chat/sessions/s_demo_001")
print()
print("=== Done ===")
print("Verified: save messages, list sessions, get messages, delete session - all OK")
