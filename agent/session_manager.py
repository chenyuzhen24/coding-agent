import json
from pathlib import Path
from typing import List, Dict, Any, Optional
# 会话存储目录：项目根目录/sessions
SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"

def init_sessions_dir() -> None:
    """初始化会话文件夹"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

def list_sessions() -> List[Dict[str, Any]]:
    """列出全部会话，返回 [{"session_id":"xxx","title":"xxx","modified":时间戳}]"""
    init_sessions_dir()
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        sid = f.stem
        title: str | None = None
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
                title = d.get("title")
        except Exception:
            pass
        sessions.append({
            "session_id": sid,
            "title": title if title else "未命名会话",
            "file_path": str(f),
            "modified": f.stat().st_mtime
        })
    return sessions

def save_session(session_id: str, messages: List[Dict[str, Any]], title: str | None = None) -> None:
    """保存会话消息列表到json，可以附带标题"""
    init_sessions_dir()
    file = SESSIONS_DIR / f"{session_id}.json"
    data: dict[str, Any] = {"messages": messages}
    if title is not None:
        data["title"] = title
    with open(file, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

def load_session(session_id: str) -> Optional[List[Dict[str, Any]]]:
    init_sessions_dir()
    file = SESSIONS_DIR / f"{session_id}.json"
    if not file.exists():
        return None
    with open(file, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    return data.get("messages", [])

def delete_session(session_id: str) -> bool:
    """删除会话文件"""
    init_sessions_dir()
    file = SESSIONS_DIR / f"{session_id}.json"
    if file.exists():
        file.unlink()
        return True
    return False

def rename_session(session_id: str, new_title: str) -> bool:
    """重命名会话，修改json内title字段"""
    init_sessions_dir()
    file = SESSIONS_DIR / f"{session_id}.json"
    if not file.exists():
        return False
    try:
        with open(file, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        data["title"] = new_title.strip()
        with open(file, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def new_session_id() -> str:
    """生成简单唯一会话ID"""
    import time
    return f"session_{int(time.time() * 1000)}"
