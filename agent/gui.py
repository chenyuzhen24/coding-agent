import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from dotenv import load_dotenv
from openai import OpenAI
from agent.agent_loop import CodingAgent
from agent.prompts import SYSTEM_PROMPT
from agent.tools import WORKSPACE, list_files
# ✅导入会话管理器
from agent.session_manager import (
    list_sessions,
    save_session,
    load_session,
    delete_session,
    new_session_id
)


class CodingAgentApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DeepSeek Coding Agent")
        self.root.geometry("1400x850")
        self.root.minsize(1000, 600)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.current_file: str | None = None
        self.busy = False
        self.current_session_id: str | None = None  # ✅ 当前会话ID
        self.build_ui()
        # ---------------- 简易Markdown文本标签样式 ----------------
        self.chat_view.tag_configure("h2", font=("Consolas", 12, "bold"))
        self.chat_view.tag_configure("h3", font=("Consolas", 11, "bold"))
        self.chat_view.tag_configure("bold", font=("Consolas", 10, "bold"))
        self.chat_view.tag_configure("code", font=("Consolas", 9), background="#eeeeee")
        self.chat_view.tag_configure("normal", font=("Consolas", 10))

        self.refresh_files()
        self.refresh_session_list()
        self.poll_events()

    def make_title_from_messages(self, messages: list[dict]) -> str:
        """从消息列表取第一条用户提问，生成会话标题，最多22字符"""
        first_user_text = None
        for m in messages:
            if m.get("role") == "user":
                txt = m.get("content", "").strip()
                if txt:
                    first_user_text = txt
                    break
        if not first_user_text:
            return "未命名会话"
        # 去掉换行、空白
        short = first_user_text.replace("\n", " ").replace("\r", " ").strip()
        if len(short) > 22:
            short = short[:22] + "…"
        return short

    def build_ui(self):
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(main, padding=8)
        center = ttk.Frame(main, padding=8)
        right = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        main.add(center, weight=4)
        main.add(right, weight=3)

        # ============ Workspace 文件【放到上方】 ============
        ttk.Label(left, text="Workspace 文件").pack(anchor=tk.W)
        self.file_tree = ttk.Treeview(left, show="tree")
        self.file_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_selected)
        ttk.Button(
            left,
            text="刷新文件",
            command=self.refresh_files,
        ).pack(fill=tk.X, pady=(8, 0))

        # ============ ✅会话面板【移到下方】 ============
        ttk.Label(left, text="会话列表").pack(anchor=tk.W, pady=(12, 0))
        self.session_tree = ttk.Treeview(left, show="tree")
        self.session_tree.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self.session_tree.bind("<<TreeviewSelect>>", self.on_session_selected)
        session_btn_frame = ttk.Frame(left)
        session_btn_frame.pack(fill=tk.X, pady=(4, 8))
        ttk.Button(session_btn_frame, text="新建会话", command=self.new_session).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(session_btn_frame, text="刷新会话", command=self.refresh_session_list).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(session_btn_frame, text="删除会话", command=self.remove_selected_session).pack(side=tk.RIGHT, fill=tk.X, expand=True)
        # ============ 会话面板结束 ============

        center_toolbar = ttk.Frame(center)
        center_toolbar.pack(fill=tk.X)
        self.file_label = ttk.Label(
            center_toolbar,
            text="未选择文件",
        )
        self.file_label.pack(side=tk.LEFT)
        ttk.Button(
            center_toolbar,
            text="删除文件",
            command=self.delete_current_file,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Button(
            center_toolbar,
            text="保存文件",
            command=self.save_file,
        ).pack(side=tk.RIGHT)
        self.code_editor = ScrolledText(
            center,
            wrap=tk.NONE,
            undo=True,
            font=("Consolas", 11),
        )
        self.code_editor.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(right, text="AI Agent").pack(anchor=tk.W)
        self.chat_view = ScrolledText(
            right,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
        )
        self.chat_view.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(right, text="编程任务").pack(anchor=tk.W, pady=(8, 4))
        self.task_input = tk.Text(
            right,
            height=5,
            wrap=tk.WORD,
        )
        self.task_input.pack(fill=tk.X)
        self.run_button = ttk.Button(
            right,
            text="运行 Agent",
            command=self.start_agent,
        )
        self.run_button.pack(fill=tk.X, pady=(8, 0))

    # ==================== ✅会话相关函数【新增】 ====================
    def refresh_session_list(self):
        """刷新会话列表UI，展示会话标题"""
        self.session_tree.delete(*self.session_tree.get_children())
        sessions = list_sessions()
        for s in sessions:
            sid = s["session_id"]
            disp_title = s["title"]
            self.session_tree.insert(
                "",
                tk.END,
                text=disp_title,
                values=(sid,)
            )

    def new_session(self):
        """新建会话，清空聊天，此时不写入磁盘，第一条任务执行才持久化"""
        self.current_session_id = new_session_id()
        self.chat_view.configure(state=tk.NORMAL)
        self.chat_view.delete("1.0", tk.END)
        self.chat_view.configure(state=tk.DISABLED)
        self.append_chat(f"[系统] 创建新会话")
        self.refresh_session_list()

    def on_session_selected(self, event=None):
        """选中会话，加载历史消息，UI跳过system消息，底层消息完整保留给Agent"""
        sel = self.session_tree.selection()
        if not sel:
            return
        item_id = sel[0]
        sid = self.session_tree.item(item_id)["values"][0]  # 从values取出session_id
        msgs = load_session(sid)
        if msgs is None:
            messagebox.showerror("错误", "会话读取失败")
            return
        self.current_session_id = sid
        # 清空聊天框
        self.chat_view.configure(state=tk.NORMAL)
        self.chat_view.delete("1.0", tk.END)
        self.chat_view.configure(state=tk.DISABLED)
        self.append_chat(f"[系统] 加载会话 {sid}")
        # UI渲染：跳过 system消息，跳过tool工具返回，只展示 user / assistant
        for m in msgs:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if role in ("system", "tool"):
                continue
            if not content:
                continue
            if role == "user":
                self.append_chat(f"\n[用户] {content}")
            elif role == "assistant":
                self.append_chat(f"\n[AI]")
                self.append_markdown(content)

    def remove_selected_session(self):
        sel = self.session_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中会话")
            return
        item_id = sel[0]
        sid = self.session_tree.item(item_id)["values"][0]
        ok = messagebox.askyesno("确认删除会话", f"确定删除会话 {sid} ?")
        if not ok:
            return
        delete_session(sid)
        # 如果删除的是当前正在使用的会话，清空聊天界面
        if self.current_session_id == sid:
            self.current_session_id = None
            self.chat_view.configure(state=tk.NORMAL)
            self.chat_view.delete("1.0", tk.END)
            self.chat_view.configure(state=tk.DISABLED)
        self.refresh_session_list()
        self.append_chat(f"[系统] 删除会话 {sid}")

    # ==================== 原有函数，修改run_agent部分 ====================
    def delete_current_file(self):
        if not self.current_file:
            messagebox.showinfo("提示", "请先选择文件。")
            return
        approved = messagebox.askyesno(
            "确认删除",
            f"确定删除 workspace\\{self.current_file} 吗？",
        )
        if not approved:
            return
        file_path = WORKSPACE / self.current_file
        try:
            file_path.unlink()
            self.append_chat(
                f"[界面] 已删除 {self.current_file}"
            )
            self.current_file = None
            self.file_label.configure(text="未选择文件")
            self.code_editor.delete("1.0", tk.END)
            self.refresh_files()
        except OSError as exc:
            messagebox.showerror(
                "删除失败",
                str(exc),
            )

    def append_chat(self, text: str):
        """美化输出：如果是json字符串尝试格式化"""
        show_text = text
        # 处理：工具执行结果：{...} 这种裸字典字符串
        if text.startswith("工具执行结果："):
            prefix, raw = text.split("工具执行结果：", maxsplit=1)
            try:
                # 将python字典字符串转json美化
                import ast
                d = ast.literal_eval(raw.strip())
                pretty = json.dumps(d, ensure_ascii=False, indent=2)
                show_text = prefix + "工具执行结果：\n" + pretty
            except Exception:
                pass
        self.chat_view.configure(state=tk.NORMAL)
        self.chat_view.insert(tk.END, show_text + "\n")
        self.chat_view.see(tk.END)
        self.chat_view.configure(state=tk.DISABLED)

    def append_markdown(self, md_text: str):
        """简易Markdown解析写入chat_view，支持 h2/h3/**粗体**/代码块```"""
        self.chat_view.configure(state=tk.NORMAL)
        lines = md_text.splitlines()
        in_code_block = False
        for line in lines:
            stripped = line.rstrip()
            # 代码块切换
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                self.chat_view.insert(tk.END, stripped + "\n", "code")
                continue
            # 二级标题 ##
            if stripped.startswith("## "):
                self.chat_view.insert(tk.END, stripped.removeprefix("## ") + "\n", "h2")
            # 三级标题 ###
            elif stripped.startswith("### "):
                self.chat_view.insert(tk.END, stripped.removeprefix("### ") + "\n", "h3")
            else:
                # 简单处理 **xxx** 粗体
                parts = []
                import re
                # 拆分 **内容**
                tokens = re.split(r'(\*\*.*?\*\*)', stripped)
                for tok in tokens:
                    if tok.startswith("**") and tok.endswith("**"):
                        text = tok[2:-2]
                        self.chat_view.insert(tk.END, text, "bold")
                    else:
                        self.chat_view.insert(tk.END, tok, "normal")
                self.chat_view.insert(tk.END, "\n")
        self.chat_view.see(tk.END)
        self.chat_view.configure(state=tk.DISABLED)

    def refresh_files(self):
        self.file_tree.delete(*self.file_tree.get_children())
        if not WORKSPACE.exists():
            WORKSPACE.mkdir(parents=True)
        for path in sorted(WORKSPACE.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(WORKSPACE)
            if any(
                part in {".git", ".venv", "__pycache__", "node_modules"}
                for part in relative.parts
            ):
                continue
            self.file_tree.insert(
                "",
                tk.END,
                iid=str(relative),
                text=str(relative),
            )

    def on_file_selected(self, _event=None):
        selection = self.file_tree.selection()
        if not selection:
            return
        relative_path = selection[0]
        file_path = WORKSPACE / relative_path
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            messagebox.showerror("无法打开", "该文件不是 UTF-8 文本文件。")
            return
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))
            return
        self.current_file = relative_path
        self.file_label.configure(text=relative_path)
        self.code_editor.delete("1.0", tk.END)
        self.code_editor.insert("1.0", content)

    def save_file(self):
        if not self.current_file:
            messagebox.showinfo("提示", "请先选择文件。")
            return
        file_path = WORKSPACE / self.current_file
        content = self.code_editor.get("1.0", tk.END)
        try:
            file_path.write_text(content, encoding="utf-8")
            self.append_chat(f"[界面] 已保存 {self.current_file}")
            self.refresh_files()
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))

    def start_agent(self):
        if self.busy:
            return
        task = self.task_input.get("1.0", tk.END).strip()
        if not task:
            messagebox.showinfo("提示", "请输入编程任务。")
            return
        self.busy = True
        self.run_button.configure(state=tk.DISABLED)
        self.append_chat(f"\n[用户] {task}")
        thread = threading.Thread(
            target=self.run_agent,
            args=(task,),
            daemon=True,
        )
        thread.start()

    def run_agent(self, task: str):
        try:
            load_dotenv()
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            )
            model = os.getenv(
                "DEEPSEEK_MODEL",
                "deepseek-chat",
            )
            if not api_key:
                raise RuntimeError("没有找到 DEEPSEEK_API_KEY")
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            def confirm_tool(tool_name: str, arguments: dict) -> bool:
                if tool_name != "delete_file":
                    return True
                path = arguments.get("path", "")
                # Tkinter 弹窗必须通过主线程处理。
                confirmation_queue: queue.Queue[bool] = queue.Queue(maxsize=1)
                self.events.put(
                    (
                        "confirm_delete",
                        {
                            "path": path,
                            "queue": confirmation_queue,
                        },
                    )
                )
                return confirmation_queue.get()

            def on_event(message: str):
                self.events.put(("log", message))

            if self.current_session_id is not None:
                history_msgs = load_session(self.current_session_id)
            else:
                history_msgs = None
            agent = CodingAgent(
                client=client,
                model=model,
                max_rounds=10,
                on_event=on_event,
                on_confirm=confirm_tool,
                messages=history_msgs
            )
            result = agent.run(task)
            # ✅新增：新会话，生成标题保存
            if self.current_session_id is None:
                self.current_session_id = new_session_id()
                # 从messages提取标题
                title = self.make_title_from_messages(agent.messages)
                save_session(self.current_session_id, agent.messages, title=title)
            else:
                # 已有会话，沿用旧title
                save_session(self.current_session_id, agent.messages)
            self.events.put(("result", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("done", ""))

    def poll_events(self):
        try:
            while True:
                event_type, content = self.events.get_nowait()
                if event_type == "log":
                    content_text = content
                    # 完整需要屏蔽的调试文本前缀
                    debug_hide_prefix = [
                        "========== 第 ",
                        "工具参数：",
                        "工具执行结果：",
                        "模型未请求工具，任务结束。"
                    ]
                    # 需要保留展示的前缀
                    show_prefix = "模型请求工具："
                    if content_text.startswith(show_prefix):
                        # 保留：显示调用了哪个工具
                        self.append_chat(f"{content_text}")
                    elif any(content_text.startswith(p) for p in debug_hide_prefix):
                        # 直接丢弃，不输出UI
                        pass
                    else:
                        # 普通AI消息正常输出
                        self.append_chat(f"[AI] {content_text}")
                elif event_type == "result":
                    self.append_chat("\n[最终结果]")
                    self.append_markdown(content)
                    self.refresh_files()
                elif event_type == "error":
                    self.append_chat("[错误] " + content)
                    messagebox.showerror("Agent 错误", content)
                elif event_type == "done":
                    self.busy = False
                    self.run_button.configure(state=tk.NORMAL)
                    self.refresh_files()
                elif event_type == "confirm_delete":
                    data = content
                    path = data["path"]
                    confirmation_queue = data["queue"]
                    approved = messagebox.askyesno(
                        "确认删除文件",
                        (
                            f"Agent 请求删除以下文件：\n\n"
                            f"workspace\\{path}\n\n"
                            "删除后文件将无法通过本程序恢复，是否继续？"
                        ),
                    )
                    confirmation_queue.put(approved)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)


def main():
    root = tk.Tk()
    app = CodingAgentApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
