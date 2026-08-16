# -*- coding: utf-8 -*-
"""
滴答清单（TickTick / Dida365）客户端
使用官方 Open API：https://api.dida365.com/open/v1（中国版）

提醒逻辑：
  - 任务：只提醒"当天"到期（dueDate 是今天）的未完成任务，当天提醒一次
  - 习惯：按每个习惯规定的提醒时间点（reminders 数组，如 "07:00"）到点提醒，
    每个时间点当天只提醒一次（错过的时间点在当天内补提醒）
"""
import os
import json
import time
import threading
from datetime import datetime, timezone
import requests

API_BASE = "https://api.dida365.com/open/v1"
TOKEN = os.environ.get("TICKTICK_TOKEN", "dp_cd390e58e4c74119bc195792edc7ed90")

# 持久化的"已提醒"状态（避免重启后重复轰炸）
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminder_state.json")

_cache = {"tasks": [], "habits": [], "updated": 0.0}
_lock = threading.Lock()


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _headers():
    return {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}


def fetch_projects():
    r = requests.get(f"{API_BASE}/project", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_project_data(project_id):
    r = requests.get(f"{API_BASE}/project/{project_id}/data", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_habits():
    r = requests.get(f"{API_BASE}/habit", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def _to_local_date(utc_str):
    """UTC ISO 字符串 → 本地日期字符串 YYYY-MM-DD"""
    if not utc_str:
        return None
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d")
    except Exception:
        return None


def _to_local_time(utc_str):
    """UTC ISO 字符串 → 本地时间字符串 HH:MM"""
    if not utc_str:
        return None
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%H:%M")
    except Exception:
        return None


def refresh(force=False):
    """刷新缓存：未完成的任务 + 习惯列表"""
    global _cache
    if not force and time.time() - _cache["updated"] < 120:
        return _cache
    tasks, habits = [], []
    try:
        projects = fetch_projects()
        for p in projects:
            try:
                data = fetch_project_data(p["id"])
            except Exception:
                continue
            pname = data.get("project", {}).get("name", p.get("name", ""))
            for t in data.get("tasks", []):
                if t.get("status") != 0:
                    continue
                tasks.append({
                    "id": t.get("id"),
                    "title": t.get("title", ""),
                    "project": pname,
                    "startDate": t.get("startDate", ""),
                    "dueDate": t.get("dueDate", ""),
                    "isAllDay": t.get("isAllDay", False),
                    "priority": t.get("priority", 0),
                })
        habits = fetch_habits()
    except Exception as e:
        print(f"[ticktick] refresh failed: {e}", flush=True)
        if _cache["tasks"] or _cache["habits"]:
            return _cache
        raise
    with _lock:
        _cache = {"tasks": tasks, "habits": habits, "updated": time.time()}
    return _cache


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _now_hm():
    return datetime.now().strftime("%H:%M")


def get_reminders():
    """
    返回本次需要提醒的内容（带去重）：
      {
        "count": N,            # 本次新提醒条数
        "text": "...",         # 播报文本
        "items": [...],
        "due_today": N,        # 当天到期任务数（供参考）
      }
    去重规则：
      - 任务：key = task:{id}:{日期}，到期日当天只提醒一次
      - 习惯：key = habit:{id}:{HH:MM}:{日期}，每个时间点当天只提醒一次；
        当前时间 >= 提醒时间点才触发（当天内补提醒错过的点）
    """
    global _cache
    try:
        refresh(force=(time.time() - _cache["updated"] > 120))
    except Exception:
        pass

    tasks = _cache.get("tasks", [])
    habits = _cache.get("habits", [])
    today = _today()
    now = _now_hm()

    state = _load_state()
    # 清理过期状态（只保留今天的条目）
    state = {k: v for k, v in state.items() if k.endswith(today)}

    new_items = []  # 本次新提醒

    # ---- 1) 当天到期任务 ----
    for t in tasks:
        due_date = _to_local_date(t.get("dueDate"))
        if due_date != today:
            continue
        key = f"task:{t['id']}:{today}"
        if state.get(key) == today:
            continue  # 今天已提醒过
        due_time = _to_local_time(t.get("dueDate")) or "00:00"
        state[key] = today
        new_items.append({
            "kind": "task",
            "key": key,
            "text": f"{t['title']}" + (f"（{due_time} 到期）" if not t.get("isAllDay") else ""),
        })

    # ---- 2) 习惯按时间点 ----
    for h in habits:
        if h.get("status") != 0:
            continue
        name = h.get("name", "习惯")
        encouragement = h.get("encouragement", "")
        goal = h.get("goal", 1)
        unit = h.get("unit", "")
        for hm in h.get("reminders", []):
            hm = str(hm).strip()
            if len(hm) == 5 and hm[2] == ":":
                pass
            elif len(hm) == 4 and hm.isdigit():
                hm = f"{hm[:2]}:{hm[2:]}"
            else:
                continue
            if hm > now:
                continue  # 还没到点
            key = f"habit:{h['id']}:{hm}:{today}"
            if state.get(key) == today:
                continue
            state[key] = today
            # 打卡次数类习惯（如喝水 goal=4杯）用数量表达；布尔类用名称
            if h.get("type") == "Real" and goal and goal > 1:
                text = f"{name}打卡啦，今天目标 {int(goal)} {unit or '次'}哦"
            else:
                text = name
            if encouragement:
                text += f"～{encouragement}"
            new_items.append({
                "kind": "habit",
                "key": key,
                "text": text,
            })

    _save_state(state)

    if not new_items:
        return {
            "count": 0,
            "text": "",
            "items": [],
            "due_today": len([t for t in tasks if _to_local_date(t.get('dueDate')) == today]),
        }

    task_lines = [it["text"] for it in new_items if it["kind"] == "task"]
    habit_lines = [it["text"] for it in new_items if it["kind"] == "habit"]

    lines = []
    if task_lines:
        lines.append("今天有 " + str(len(task_lines)) + " 个任务到期：" + "、".join(task_lines[:5]))
    if habit_lines:
        lines.append("该去做啦：" + "、".join(habit_lines[:6]))
    text = "露娜提醒你～" + "\n".join(lines)

    return {
        "count": len(new_items),
        "text": text,
        "items": new_items,
        "due_today": len([t for t in tasks if _to_local_date(t.get('dueDate')) == today]),
    }


def reminder_loop(interval=60):
    """后台线程：定期刷新缓存（真正的提醒判断在 get_reminders 里做）"""
    while True:
        try:
            refresh(force=True)
        except Exception as e:
            print(f"[ticktick] loop error: {e}", flush=True)
        time.sleep(interval)


def start_reminder_loop(interval=60):
    th = threading.Thread(target=reminder_loop, args=(interval,), daemon=True)
    th.start()
    return th


if __name__ == "__main__":
    r = get_reminders()
    print(f"count={r['count']}")
    print(r["text"])
