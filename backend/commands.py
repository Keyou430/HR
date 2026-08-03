"""指令系统：通过对话窗口发送自然语言指令来执行工作台操作。

流程：
1. 用户在聊天窗口输入自然语言指令（如「帮我创建任务：明天交报告」）
2. classify_command() 调用 Hermes 判断是否为指令并提取参数
3. execute_command() 在本地执行实际操作（创建任务/日程等）
4. 将执行结果返回给用户
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

from config import Settings
from hermes import HermesGatewayError, hermes_chat
from store import store

logger = logging.getLogger("replica.commands")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(_handler)
    logger.propagate = False


def _build_system_prompt() -> str:
    """构建指令分类的系统 prompt，注入当前日期以便 Hermes 正确解析相对日期。"""
    today = date.today()
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_names[today.weekday()]

    return f"""你是 Replica 协同门户的指令解析器。你需要判断用户的输入是一般对话还是操作指令。

当前日期：{today.isoformat()}（{weekday}）

## 支持的指令类型

### 1. create_task — 创建任务
参数: title (任务标题), tag (标签: 今天/明天/本周/本月), due_time (截止时间 HH:MM，可选)
触发词: "创建任务"、"添加任务"、"新建任务"、"帮我加一个"、"提醒我"、"别忘了"、"帮我创建"、"帮我建一个"

### 2. update_task — 更新/完成任务
参数: title (要查找的任务标题关键词 或 数字ID), done (true=标记完成, false=标记未完成)
触发词: "完成任务"、"标记完成"、"做完了"、"搞定"、"完成了"
注意: 如果用户提供数字（如"1234"），可能是任务 ID——将数字同时填入 title 和 id 字段

### 3. delete_task — 删除任务
参数: title (要查找的任务标题关键词 或 数字ID)
触发词: "删除任务"、"移除任务"、"取消任务"、"删掉"
注意: 如果用户提供数字（如"1234"），可能是任务 ID——将数字同时填入 title 和 id 字段

### 4. create_event — 创建日历日程
参数: title (日程标题), date (日期 YYYY-MM-DD), tone (颜色: blue/green/orange)
触发词: "添加日程"、"创建日程"、"帮我安排"、"约了"、"开会"、"会议"

### 5. chat — 普通对话
触发: 知识问答、闲聊、不匹配上述指令的输入

## 重要规则

- 如果用户输入是一个操作请求（创建/修改/删除任务或日程），必须提取为指令。
- 如果是知识问题、闲聊、询问信息，返回 action="chat"。
- **关键**：如果用户的输入是一段长篇分析、理论推演、学术讨论、政策分析、社会现象解读，或者包含大量专业术语和复杂句式——这一定是 chat，不是指令。用户是在请求知识分析和观点，不是在请求你替他做事。
- **关键**：以"为什么"、"如何"、"怎样"、"怎么"开头的问题，99% 是 chat（用户在求解释/分析），除非后面紧跟明确的动作指令（如"怎么创建一个任务"）。
- **关键**：如果输入超过 100 个字且读起来像一篇文章或论述，一定是 chat。操作指令通常很短（一句话说清楚要做什么）。
- **关键**：如果用户问的是"如果…会怎样"、"如何理解…"、"如何看待…"、"分析…"、"评价…"这类问题，一定是 chat。
- date 参数必须是 YYYY-MM-DD 格式。根据当前日期推断相对日期：
  - "今天" = {today.isoformat()}
  - "明天" = 明天日期
  - "后天" = 后天日期
  - "下周一/二…" = 下周对应日期
  - "下周" = 下周同一天
- tag 参数必须是: 今天 / 明天 / 本周 / 本月
- 如果用户没有明确指定 tag，默认使用 "今天"
- tone 参数默认使用 "blue"

## 输出格式

必须只输出一行纯 JSON（不要 markdown 代码块包裹，不要 ```json）：

{{"action": "<action>", "params": {{...}}, "reply": "给用户的友好确认消息"}}

如果 action 是 chat，params 为空对象，reply 为空字符串。

## 示例

用户: "帮我创建一个任务：明天下午3点提交季度报告"
输出: {{"action": "create_task", "params": {{"title": "提交季度报告", "tag": "明天", "due_time": "15:00"}}, "reply": "好的，已为你创建任务「提交季度报告」，截止明天 15:00 ✅"}}

用户: "完成了提交季度报告这个任务"
输出: {{"action": "update_task", "params": {{"title": "提交季度报告", "done": true}}, "reply": "已将任务「提交季度报告」标记为完成 ✓"}}

用户: "下周三下午2点和产品团队开评审会"
输出: {{"action": "create_event", "params": {{"title": "和产品团队评审会", "date": "下周三对应日期", "tone": "blue"}}, "reply": "已添加日程「和产品团队评审会」📅"}}

用户: "什么是机器学习"
输出: {{"action": "chat", "params": {{}}, "reply": ""}}

用户: "今天天气怎么样"
输出: {{"action": "chat", "params": {{}}, "reply": ""}}

用户: "帮我把「整理周报」删掉"
输出: {{"action": "delete_task", "params": {{"title": "整理周报"}}, "reply": "已删除任务「整理周报」🗑️"}}

用户: "如何理解差序格局对现代社会治理的影响？"
输出: {{"action": "chat", "params": {{}}, "reply": ""}}

用户: "如果在一个快速变迁的社会中，制度设计的理性逻辑与乡土文化惯性产生冲突，会带来什么后果？"
输出: {{"action": "chat", "params": {{}}, "reply": ""}}

用户: "分析一下香港土地制度与差序格局之间的关系"
输出: {{"action": "chat", "params": {{}}, "reply": ""}}
"""


async def classify_command(settings: Settings, question: str) -> dict:
    """调用 Hermes 将用户输入分类为指令或普通对话。

    返回格式: {"action": str, "params": dict, "reply": str}
    如果分类失败或 LLM 不可用，返回 chat 动作。
    """
    try:
        raw = await hermes_chat(
            settings=settings,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": question},
            ],
        )
        raw = raw.strip()

        # 清洗可能的 markdown 代码块包裹
        if raw.startswith("```"):
            lines = raw.split("\n")
            # 去掉第一行 ```json 和最后一行 ```
            content_lines = [
                line for line in lines if not line.strip().startswith("```")
            ]
            raw = "\n".join(content_lines)

        result = json.loads(raw)

        # 归一化 action 为小写，防止大小写变体导致匹配失败
        if isinstance(result, dict) and "action" in result and isinstance(result["action"], str):
            result["action"] = result["action"].strip().lower()

        # 基本合法性校验
        if not isinstance(result, dict) or "action" not in result:
            logger.warning("Command classification returned invalid structure: %r", raw[:200])
            return {"action": "chat", "params": {}, "reply": ""}

        logger.info(
            "Command classified: action=%s params=%s",
            result.get("action"), result.get("params"),
        )
        return result

    except (HermesGatewayError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Command classification failed, falling back to chat: %s", exc)
        return {"action": "chat", "params": {}, "reply": ""}


def execute_command(cmd: dict) -> dict:
    """根据分类结果执行实际操作。

    cmd: classify_command() 的返回值 {"action": str, "params": dict, "reply": str}

    返回格式:
        {"answer": str, "mode": "command", "action": str, "result": dict | None}
    """
    action = cmd.get("action", "chat")
    params = cmd.get("params", {})
    default_reply = cmd.get("reply", "")

    if action == "chat":
        return {"answer": "", "mode": "command", "action": "chat", "result": None}

    try:
        if action == "create_task":
            return _handle_create_task(params, default_reply)

        if action == "update_task":
            return _handle_update_task(params, default_reply)

        if action == "delete_task":
            return _handle_delete_task(params, default_reply)

        if action == "create_event":
            return _handle_create_event(params, default_reply)

        # 未知 action
        logger.warning("Unknown command action: %s", action)
        return {"answer": default_reply or "抱歉，无法识别该指令。", "mode": "command", "action": action, "result": None}

    except Exception as exc:
        logger.error("Command execution error: action=%s params=%s error=%s", action, params, exc, exc_info=True)
        return {
            "answer": f"❌ 指令执行失败：{exc}",
            "mode": "command",
            "action": action,
            "result": None,
        }


# ── 各指令的私有处理函数 ──


def _handle_create_task(params: dict, reply: str) -> dict:
    title = str(params.get("title") or "").strip()
    if not title:
        return {"answer": "❌ 请提供任务标题。例如：「创建任务：明天交报告」", "mode": "command", "action": "create_task", "result": None}

    tag = params.get("tag") or "今天"
    # 规范化 tag
    valid_tags = {"今天", "明天", "本周", "本月"}
    if tag not in valid_tags:
        tag = "今天"

    due_time = params.get("due_time") or None
    if due_time and not isinstance(due_time, str):
        due_time = None

    task = store.create_task({"title": title, "tag": tag, "due_time": due_time})

    # 优先使用 Hermes 给出的友好回复，仅在缺失时构造默认回复
    if reply:
        response = reply
    else:
        response = f"✅ 已创建任务「{title}」（{tag}"
        if due_time:
            response += f"，截止 {due_time}"
        response += "）"

    return {"answer": response, "mode": "command", "action": "create_task", "result": task}


def _handle_update_task(params: dict, reply: str) -> dict:
    title_keyword = str(params.get("title") or "").strip()
    task_id_val = params.get("id") or params.get("task_id")
    task_id_str = str(task_id_val).strip() if task_id_val is not None else ""

    if not title_keyword and not task_id_str:
        return {"answer": "❌ 请提供要更新的任务标题或 ID。", "mode": "command", "action": "update_task", "result": None}

    tasks_data = store.list_tasks()
    all_tasks: list[dict] = tasks_data.get("items", [])

    # 策略 0：纯数字当 ID 查找
    matched: list[dict] = []
    if title_keyword.isdigit():
        task_id = int(title_keyword)
        matched = [t for t in all_tasks if t.get("id") == task_id]
    elif task_id_str.isdigit():
        task_id = int(task_id_str)
        matched = [t for t in all_tasks if t.get("id") == task_id]

    # 策略 1：标题精确匹配
    if not matched and title_keyword:
        matched = [t for t in all_tasks if t.get("title") == title_keyword]

    # 策略 2：标题包含匹配
    if not matched and title_keyword:
        matched = [t for t in all_tasks if title_keyword in (t.get("title") or "")]

    if not matched:
        task_list = "、".join(f"「{t['title']}」(ID:{t['id']})" for t in all_tasks[:10])
        task_hint = f"\n当前任务：{task_list}" if task_list else ""
        return {
            "answer": f"❌ 未找到匹配的任务。关键词：「{title_keyword}」{task_hint}",
            "mode": "command",
            "action": "update_task",
            "result": None,
        }

    # 取第一个匹配项
    task = matched[0]
    task_id = task["id"]

    # 构建更新 payload
    updates: dict = {}
    if "done" in params and isinstance(params["done"], bool):
        updates["done"] = params["done"]
    if "tag" in params and params["tag"]:
        updates["tag"] = params["tag"]
    if "due_time" in params:
        due_time = params.get("due_time") or None
        if due_time and not isinstance(due_time, str):
            due_time = None
        updates["due_time"] = due_time

    if not updates:
        updates["done"] = True  # 默认行为：标记完成

    updated = store.update_task(task_id, updates)
    if updated is None:
        return {"answer": f"❌ 更新任务失败，任务可能已被删除。", "mode": "command", "action": "update_task", "result": None}

    response = reply or (
        f"已将任务「{updated['title']}」标记为完成 ✓"
        if updates.get("done") else
        f"已更新任务「{updated['title']}」"
    )
    return {"answer": response, "mode": "command", "action": "update_task", "result": updated}


def _handle_delete_task(params: dict, reply: str) -> dict:
    title_keyword = str(params.get("title") or "").strip()
    task_id_val = params.get("id") or params.get("task_id")
    task_id_str = str(task_id_val).strip() if task_id_val is not None else ""

    if not title_keyword and not task_id_str:
        return {"answer": "❌ 请提供要删除的任务标题或 ID。", "mode": "command", "action": "delete_task", "result": None}

    tasks_data = store.list_tasks()
    all_tasks: list[dict] = tasks_data.get("items", [])

    # 策略 0：如果 title 看起来像纯数字，当做 ID 精确查找
    matched: list[dict] = []
    if title_keyword.isdigit():
        task_id = int(title_keyword)
        matched = [t for t in all_tasks if t.get("id") == task_id]
    elif task_id_str.isdigit():
        task_id = int(task_id_str)
        matched = [t for t in all_tasks if t.get("id") == task_id]

    # 策略 1：标题精确匹配
    if not matched and title_keyword:
        matched = [t for t in all_tasks if t.get("title") == title_keyword]

    # 策略 2：标题包含匹配
    if not matched and title_keyword:
        matched = [t for t in all_tasks if title_keyword in (t.get("title") or "")]

    if not matched:
        task_list = "、".join(f"「{t['title']}」(ID:{t['id']})" for t in all_tasks[:10])
        task_hint = f"\n当前任务：{task_list}" if task_list else ""
        return {
            "answer": f"❌ 未找到匹配的任务。关键词：「{title_keyword}」{task_hint}",
            "mode": "command",
            "action": "delete_task",
            "result": None,
        }

    task = matched[0]
    task_title = task["title"]
    deleted = store.delete_task(task["id"])

    if not deleted:
        return {"answer": f"❌ 删除任务「{task_title}」失败。", "mode": "command", "action": "delete_task", "result": None}

    response = reply or f"🗑️ 已删除任务「{task_title}」"
    return {"answer": response, "mode": "command", "action": "delete_task", "result": None}


def _handle_create_event(params: dict, reply: str) -> dict:
    title = str(params.get("title") or "").strip()
    if not title:
        return {"answer": "❌ 请提供日程标题。例如：「下周三下午开会」", "mode": "command", "action": "create_event", "result": None}
    # 截断超长标题，防止 DB 截断丢失语义
    if len(title) > 255:
        title = title[:255]

    event_date = (params.get("date") or "").strip()
    if not event_date:
        # 默认使用今天
        event_date = date.today().isoformat()
    else:
        # 校验日期格式 YYYY-MM-DD，非法日期回退到今天
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            logger.warning("create_event received invalid date %r, falling back to today", event_date)
            event_date = date.today().isoformat()

    tone = params.get("tone") or "blue"
    if tone not in ("blue", "green", "orange"):
        tone = "blue"

    event = store.create_event({"title": title, "date": event_date, "tone": tone})

    response = reply or f"📅 已添加日程「{title}」（{event_date}）"
    return {"answer": response, "mode": "command", "action": "create_event", "result": event}
