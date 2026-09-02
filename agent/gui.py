import json
import os
import shutil
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk, simpledialog
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
    rename_session,
    new_session_id
)

INVALID_FILENAME_CHARS = r'\/:*?"<>|'


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

        # ========== 文件树右键菜单 ==========
        self.file_tree_menu = tk.Menu(self.root, tearoff=0)
        self.file_tree_menu.add_command(label="新建文件", command=self.create_new_file_dialog)
        self.file_tree_menu.add_command(label="新建文件夹", command=self.create_new_folder_dialog)
        self.file_tree_menu.add_separator()
        self.file_tree_menu.add_command(label="重命名", command=self.rename_file_or_folder)
        self.file_tree_menu.add_separator()
        self.file_tree_menu.add_command(label="刷新文件列表", command=self.refresh_files)
        self.file_tree_menu.add_separator()
        self.file_tree_menu.add_command(label="删除选中文件", command=self.delete_current_file)
        self.file_tree_menu.add_command(label="删除选中文件夹", command=self.delete_selected_folder)
        self.file_tree.bind("<Button-3>", self.on_file_tree_right_click)

        # ========== 会话列表右键菜单 ==========
        self.session_tree_menu = tk.Menu(self.root, tearoff=0)
        self.session_tree_menu.add_command(label="新建会话", command=self.new_session)
        self.session_tree_menu.add_command(label="重命名会话", command=self.rename_selected_session)
        self.session_tree_menu.add_command(label="刷新会话列表", command=self.refresh_session_list)
        self.session_tree_menu.add_separator()
        self.session_tree_menu.add_command(label="删除选中会话", command=self.remove_selected_session)
        self.session_tree.bind("<Button-3>", self.on_session_tree_right_click)

        self._context_click_folder: str | None = None  # 右键点击的文件夹路径
        self.refresh_files()
        self.refresh_session_list()
        self.poll_events()

    def on_file_tree_right_click(self, event):
        """文件树鼠标右键弹出菜单；记录点击的文件夹路径给新建文件/文件夹使用"""
        self._context_click_folder = None
        row_id = self.file_tree.identify_row(event.y)
        if row_id:
            self.file_tree.selection_set(row_id)
            rel_path = self.file_tree.item(row_id)["values"][0]
            candidate = WORKSPACE / rel_path
            if candidate.is_dir():
                self._context_click_folder = rel_path
        try:
            self.file_tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.file_tree_menu.grab_release()

    def on_session_tree_right_click(self, event):
        """会话列表鼠标右键：先选中点击行，再弹出菜单"""
        row_id = self.session_tree.identify_row(event.y)
        if row_id:
            self.session_tree.selection_set(row_id)
        try:
            self.session_tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.session_tree_menu.grab_release()

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
        style = ttk.Style()
        style.configure("Treeview", rowheight=22, font=("Consolas", 9))
        style.configure("Treeview.Item", padding=(2, 2))
        self.file_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_selected)
        # ---【已移除文件操作按钮frame，全部改用右键】---

        # ============ ✅会话面板【移到下方】 ============
        ttk.Label(left, text="会话列表").pack(anchor=tk.W, pady=(12, 0))
        self.session_tree = ttk.Treeview(left, show="tree")
        self.session_tree.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self.session_tree.bind("<<TreeviewSelect>>", self.on_session_selected)
        # ---【已移除会话操作按钮frame，全部改用右键】---

        center_toolbar = ttk.Frame(center)
        center_toolbar.pack(fill=tk.X)
        self.file_label = ttk.Label(
            center_toolbar,
            text="未选择文件",
        )
        self.file_label.pack(side=tk.LEFT)
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

    def rename_file_or_folder(self):
        """重命名选中文件/文件夹"""
        sel = self.file_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中文件或文件夹")
            return
        item_id = sel[0]
        rel_path = self.file_tree.item(item_id)["values"][0]
        abs_src = WORKSPACE / rel_path
        old_name = abs_src.name
        new_name = simpledialog.askstring("重命名", "输入新名称：", initialvalue=old_name)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            messagebox.showwarning("提示", "名称不能为空")
            return
        # 校验windows非法字符
        for c in INVALID_FILENAME_CHARS:
            if c in new_name:
                messagebox.showerror("错误", f"名称不能包含字符 {repr(c)}")
                return
        abs_dst = abs_src.parent / new_name
        # 沙箱校验
        try:
            abs_dst.resolve().relative_to(WORKSPACE.resolve())
        except ValueError:
            messagebox.showerror("错误", "非法路径，禁止跳出workspace")
            return
        if abs_dst.exists():
            messagebox.showerror("错误", f"名称已存在：{new_name}")
            return
        try:
            abs_src.rename(abs_dst)
            self.append_chat(f"[界面] 重命名 {rel_path} → {abs_dst.relative_to(WORKSPACE)}")
            # 如果当前打开的就是该文件，更新current_file
            if self.current_file is not None:
                curr_abs = WORKSPACE / self.current_file
                if curr_abs.resolve() == abs_src.resolve():
                    self.current_file = str(abs_dst.relative_to(WORKSPACE))
                    self.file_label.configure(text=self.current_file)
            self.refresh_files()
        except OSError as e:
            messagebox.showerror("重命名失败", str(e))

    def rename_selected_session(self):
        """重命名选中会话"""
        sel = self.session_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中会话")
            return
        item_id = sel[0]
        sid = self.session_tree.item(item_id)["values"][0]
        old_title = self.session_tree.item(item_id)["text"]
        new_title = simpledialog.askstring("重命名会话", "输入会话新标题：", initialvalue=old_title)
        if new_title is None:
            return
        new_title = new_title.strip()
        if not new_title:
            messagebox.showwarning("提示", "标题不能为空")
            return
        ok = rename_session(sid, new_title)
        if not ok:
            messagebox.showerror("错误", "重命名会话失败")
            return
        self.append_chat(f"[系统] 会话重命名：{old_title} → {new_title}")
        self.refresh_session_list()
        # 重命名后保持选中当前会话
        self._select_session_by_id(sid)

    def delete_selected_folder(self):
        """GUI手动删除选中文件夹（递归删除全部内容，仅右键可用，AI工具不开放）"""
        sel = self.file_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一个文件夹")
            return
        item_id = sel[0]
        rel_path = self.file_tree.item(item_id)["values"][0]
        target_path = WORKSPACE / rel_path
        # 校验：必须是文件夹，不能删除workspace根目录，不能越界
        if not target_path.is_dir():
            messagebox.showerror("错误", "选中项不是文件夹，请选中文件夹再执行")
            return
        if target_path.resolve() == WORKSPACE.resolve():
            messagebox.showerror("禁止操作", "不允许删除 workspace 根目录")
            return
        try:
            target_path.resolve().relative_to(WORKSPACE.resolve())
        except ValueError:
            messagebox.showerror("错误", "非法路径，禁止访问workspace外部")
            return

        ok = messagebox.askyesno(
            "⚠️ 确认删除文件夹",
            f"即将递归删除文件夹：workspace\\{rel_path}\n\n"
            "文件夹内部所有文件、子文件夹都会被永久删除，无法恢复！\n确定继续吗？"
        )
        if not ok:
            return
        try:
            shutil.rmtree(target_path)
            self.append_chat(f"[界面] 手动删除文件夹 {rel_path}")
            # 如果当前打开的文件属于被删除目录，清空编辑器
            if self.current_file is not None:
                curr_abs = (WORKSPACE / self.current_file).resolve()
                if str(curr_abs).startswith(str(target_path.resolve())):
                    self.current_file = None
                    self.file_label.configure(text="未选择文件")
                    self.code_editor.delete("1.0", tk.END)
            self.refresh_files()
        except OSError as e:
            messagebox.showerror("删除文件夹失败", str(e))

    def create_new_folder_dialog(self):
        """手动新建文件夹弹窗，若右键选中文件夹，默认路径为该目录"""
        initial_val = ""
        if self._context_click_folder is not None:
            initial_val = f"{self._context_click_folder}/"
        rel_path = simpledialog.askstring(
            "新建文件夹",
            "输入相对于 workspace 的文件夹路径：\n示例：src 或者 utils/common",
            initialvalue=initial_val
        )
        if rel_path is None:
            return
        rel_path = rel_path.strip()
        if not rel_path:
            messagebox.showwarning("提示", "文件夹路径不能为空")
            return
        # 安全路径校验，防止跳出workspace
        try:
            candidate = (WORKSPACE / rel_path).resolve()
            workspace_root = WORKSPACE.resolve()
            candidate.relative_to(workspace_root)
        except ValueError:
            messagebox.showerror("错误", "非法路径，不允许访问workspace外部")
            return

        if candidate.exists():
            messagebox.showerror("错误", f"路径已存在：{rel_path}")
            return
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            self.append_chat(f"[界面] 手动新建文件夹 {rel_path}")
            self.refresh_files()
        except OSError as e:
            messagebox.showerror("创建文件夹失败", str(e))

    def create_new_file_dialog(self):
        """手动新建文件弹窗；右键选中文件夹时，输入框默认填充该文件夹路径"""
        initial_val = ""
        if self._context_click_folder is not None:
            initial_val = f"{self._context_click_folder}/"
        rel_path = simpledialog.askstring(
            "新建文件",
            "输入相对于 workspace 的文件路径：\n示例：main.py 或者 utils/helper.py",
            initialvalue=initial_val
        )
        if rel_path is None:
            return
        rel_path = rel_path.strip()
        if not rel_path:
            messagebox.showwarning("提示", "文件路径不能为空")
            return
        # 安全路径校验，防止跳出workspace
        try:
            candidate = (WORKSPACE / rel_path).resolve()
            workspace_root = WORKSPACE.resolve()
            candidate.relative_to(workspace_root)
        except ValueError:
            messagebox.showerror("错误", "非法路径，不允许访问workspace外部")
            return

        if candidate.exists():
            messagebox.showerror("错误", f"文件已存在：{rel_path}")
            return
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text("", encoding="utf-8")
            self.append_chat(f"[界面] 手动新建文件 {rel_path}")
            self.refresh_files()
            # 创建完成自动打开该文件到编辑器
            self.current_file = rel_path
            self.file_label.configure(text=rel_path)
            self.code_editor.delete("1.0", tk.END)
        except OSError as e:
            messagebox.showerror("创建失败", str(e))

    def _select_session_by_id(self, session_id: str):
        """内部工具：根据session_id在treeview中定位并选中条目"""
        for item in self.session_tree.get_children():
            vals = self.session_tree.item(item, "values")
            if vals and vals[0] == session_id:
                self.session_tree.selection_set(item)
                self.session_tree.focus(item)
                return

    # ==================== ✅会话相关函数 ====================
    def refresh_session_list(self):
        """刷新会话列表UI，展示会话标题，刷新后保留当前会话选中"""
        old_current = self.current_session_id
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
        # 刷新完，重新选中当前正在使用的会话
        if old_current is not None:
            self._select_session_by_id(old_current)

    def new_session(self):
        """新建会话：立刻写入磁盘，列表马上可见，自动选中"""
        self.current_session_id = new_session_id()
        self.chat_view.configure(state=tk.NORMAL)
        self.chat_view.delete("1.0", tk.END)
        self.chat_view.configure(state=tk.DISABLED)
        self.append_chat(f"[系统] 创建新会话")
        # 关键点：新建会话立刻写入磁盘，空messages，临时标题，不用等到第一次交互
        save_session(self.current_session_id, messages=[], title="新会话")
        self.refresh_session_list()
        # 新建完成，高亮选中刚创建的会话
        self._select_session_by_id(self.current_session_id)

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
        # 如果删除的是当前正在使用的会话，清空标记
        if self.current_session_id == sid:
            self.current_session_id = None
            self.chat_view.configure(state=tk.NORMAL)
            self.chat_view.delete("1.0", tk.END)
            self.chat_view.configure(state=tk.DISABLED)
        self.refresh_session_list()
        self.append_chat(f"[系统] 删除会话 {sid}")

    # ==================== 文件操作 ====================
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
        node_map = {}
        root_id = ""
        for path in sorted(WORKSPACE.rglob("*")):
            relative = path.relative_to(WORKSPACE)
            if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in relative.parts):
                continue
            parts = list(relative.parts)
            parent_id = root_id
            current_rel = Path()
            for idx, part in enumerate(parts):
                current_rel = current_rel / part
                node_key = str(current_rel)
                if node_key not in node_map:
                    if idx == len(parts) - 1 and path.is_file():
                        iid = self.file_tree.insert(parent_id, tk.END, iid=node_key, text=f"📄 {part}", values=(str(current_rel),))
                    else:
                        iid = self.file_tree.insert(parent_id, tk.END, iid=node_key, text=f"📁 {part}", values=(str(current_rel),))
                        node_map[node_key] = iid
                parent_id = node_map[node_key] if node_key in node_map else parent_id

    def on_file_selected(self, _event=None):
        selection = self.file_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        # 如果点击的是文件夹，直接返回，不打开
        text_display = self.file_tree.item(item_id, "text")
        if text_display.startswith("📁"):
            return
        relative_path = self.file_tree.item(item_id)["values"][0]
        file_path = WORKSPACE / relative_path
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            messagebox.showerror("无法打开", "该文件不是 UTF‑8 文本文件。")
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
            # 运行交互之后，更新会话标题，用第一条用户消息替换临时的“新会话”
            if self.current_session_id is not None:
                title = self.make_title_from_messages(agent.messages)
                save_session(self.current_session_id, agent.messages, title=title)
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
                    self.refresh_session_list()
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
