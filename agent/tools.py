import subprocess
from pathlib import Path
from typing import Any

# Agent 允许操作的根目录。
# 这里默认是项目根目录下的 workspace 文件夹。
WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"

def initialize_workspace() -> None:
    """创建工作目录。"""
    WORKSPACE.mkdir(parents=True, exist_ok=True)

def safe_path(relative_path: str) -> Path:
    """
    将用户提供的相对路径转换为工作区内的安全路径。

    禁止访问 workspace 之外的文件，
    防止使用 .. 跳出工作目录。
    """
    initialize_workspace()

    candidate = (WORKSPACE / relative_path).resolve()
    workspace_root = WORKSPACE.resolve()

    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        raise ValueError("非法路径：只能访问 workspace 目录内的文件")

    return candidate

def list_files(path: str = ".") -> dict[str, Any]:
    """列出工作区内的文件和目录。"""
    try:
        directory = safe_path(path)

        if not directory.exists():
            return {
                "success": False,
                "error": f"目录不存在：{path}",
            }

        if not directory.is_dir():
            return {
                "success": False,
                "error": f"目标不是目录：{path}",
            }

        items = []

        for item in sorted(directory.rglob("*")):
            relative = item.relative_to(WORKSPACE)

            # 避免把缓存和虚拟环境交给模型
            if any(
                part in {".git", ".venv", "__pycache__", "node_modules"}
                for part in relative.parts
            ):
                continue

            items.append(
                {
                    "path": str(relative),
                    "type": "directory" if item.is_dir() else "file",
                }
            )

            # 防止大型项目一次返回过多内容
            if len(items) >= 300:
                break

        return {
            "success": True,
            "path": path,
            "items": items,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"列出文件失败：{exc}",
        }

def search_files(
    query: str,
    path: str = ".",
    max_results: int = 50,
) -> dict[str, Any]:
    """在工作区文本文件中搜索字符串。"""
    try:
        if not query:
            return {
                "success": False,
                "error": "搜索内容不能为空",
            }

        root = safe_path(path)

        if not root.exists():
            return {
                "success": False,
                "error": f"搜索路径不存在：{path}",
            }

        results = []

        files = [root] if root.is_file() else root.rglob("*")

        for file_path in files:
            if not file_path.is_file():
                continue

            relative = file_path.relative_to(WORKSPACE)

            if any(
                part in {".git", ".venv", "__pycache__", "node_modules"}
                for part in relative.parts
            ):
                continue

            try:
                lines = file_path.read_text(
                    encoding="utf-8",
                ).splitlines()
            except (UnicodeDecodeError, OSError):
                continue

            for line_number, line in enumerate(lines, start=1):
                if query.lower() in line.lower():
                    results.append(
                        {
                            "path": str(relative),
                            "line": line_number,
                            "content": line[:500],
                        }
                    )

                    if len(results) >= max_results:
                        return {
                            "success": True,
                            "query": query,
                            "results": results,
                            "truncated": True,
                        }

        return {
            "success": True,
            "query": query,
            "results": results,
            "truncated": False,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"搜索文件失败：{exc}",
        }

def read_file(path: str) -> dict[str, Any]:
    """读取工作区内的文本文件。"""
    try:
        file_path = safe_path(path)

        if not file_path.exists():
            return {
                "success": False,
                "error": f"文件不存在：{path}",
            }

        if not file_path.is_file():
            return {
                "success": False,
                "error": f"目标不是文件：{path}",
            }

        content = file_path.read_text(encoding="utf-8")

        return {
            "success": True,
            "path": path,
            "content": content,
        }

    except UnicodeDecodeError:
        return {
            "success": False,
            "error": "文件不是 UTF-8 文本文件，暂不支持读取。",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"读取文件失败：{exc}",
        }

def create_file(path: str, content: str) -> dict[str, Any]:
    """
    在 workspace 中创建新文件。

    如果目标文件已经存在，则拒绝操作，避免误覆盖已有代码。
    """
    try:
        file_path = safe_path(path)

        if file_path.exists():
            return {
                "success": False,
                "error": (
                    f"文件已经存在：{path}。"
                    "如需修改已有文件，请先读取文件，再使用 apply_patch。"
                ),
            }

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": path,
            "message": "新文件创建成功",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"创建文件失败：{exc}",
        }

def write_file(path: str, content: str) -> dict[str, Any]:
    """写入工作区内的文本文件。"""
    try:
        file_path = safe_path(path)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": path,
            "message": "文件写入成功",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"写入文件失败：{exc}",
        }

def run_command(command: str, timeout: int = 30) -> dict[str, Any]:
    """
    在 workspace 目录中执行 Windows 命令。

    当前只允许执行预先定义的安全命令，
    不允许直接执行任意高风险系统命令。
    """
    forbidden_keywords = [
        "format ",
        "del ",
        "rd ",
        "rmdir ",
        "shutdown",
        "restart-computer",
        "remove-item",
        "reg ",
        "diskpart",
        "taskkill",
        "curl ",
        "wget ",
        "invoke-webrequest",
    ]

    normalized_command = command.lower().strip()

    for keyword in forbidden_keywords:
        if keyword in normalized_command:
            return {
                "success": False,
                "error": f"命令包含禁止使用的内容：{keyword}",
            }

    try:
        result = subprocess.run(
            command,
            cwd=WORKSPACE,
            shell=True,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )


        return {
            "success": result.returncode == 0,
            "command": command,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"命令执行超时，限制时间为 {timeout} 秒",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"命令执行失败：{exc}",
        }

def delete_file(path: str) -> dict[str, Any]:
    """
    删除 workspace 内的单个文件。

    安全限制：
    - 只能删除 workspace 内的文件
    - 不允许删除目录
    - 不允许删除受保护文件
    """
    try:
        file_path = safe_path(path)

        if not file_path.exists():
            return {
                "success": False,
                "error": f"文件不存在：{path}",
            }

        if not file_path.is_file():
            return {
                "success": False,
                "error": f"目标不是普通文件，不允许删除：{path}",
            }

        protected_names = {
            ".env",
            ".gitignore",
            "README.md",
            "README.txt",
        }

        if file_path.name in protected_names:
            return {
                "success": False,
                "error": f"文件受到保护，不允许删除：{path}",
            }

        file_path.unlink()

        return {
            "success": True,
            "path": path,
            "message": "文件删除成功",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"删除文件失败：{exc}",
        }

def apply_patch(
    path: str,
    old_text: str,
    new_text: str,
) -> dict[str, Any]:
    """
    将文件中唯一匹配的 old_text 替换为 new_text。

    要求 old_text 只能匹配一次，避免误修改多个位置。
    """
    try:
        file_path = safe_path(path)

        if not file_path.exists():
            return {
                "success": False,
                "error": f"文件不存在：{path}",
            }

        content = file_path.read_text(encoding="utf-8")
        match_count = content.count(old_text)

        if match_count == 0:
            return {
                "success": False,
                "error": "没有找到需要替换的原始代码",
            }

        if match_count > 1:
            return {
                "success": False,
                "error": (
                    f"原始代码匹配了 {match_count} 次，"
                    "请提供包含更多上下文的代码片段"
                ),
            }

        updated_content = content.replace(
            old_text,
            new_text,
            1,
        )

        file_path.write_text(
            updated_content,
            encoding="utf-8",
        )

        return {
            "success": True,
            "path": path,
            "message": "局部补丁应用成功",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"应用补丁失败：{exc}",
        }

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """根据工具名称分发并执行工具，并处理参数错误。"""
    try:
        if tool_name == "read_file":
            path = arguments.get("path")

            if not isinstance(path, str) or not path:
                return {
                    "success": False,
                    "error": "read_file 缺少有效的 path 参数",
                }

            return read_file(path)

        if tool_name == "write_file":
            path = arguments.get("path")
            content = arguments.get("content")

            if not isinstance(path, str) or not path:
                return {
                    "success": False,
                    "error": "write_file 缺少有效的 path 参数",
                }

            if not isinstance(content, str):
                return {
                    "success": False,
                    "error": "write_file 的 content 必须是字符串",
                }

            return write_file(path, content)

        if tool_name == "run_command":
            command = arguments.get("command")
            timeout = arguments.get("timeout", 30)

            if not isinstance(command, str) or not command:
                return {
                    "success": False,
                    "error": "run_command 缺少有效的 command 参数",
                }

            if not isinstance(timeout, int):
                timeout = 30

            timeout = max(1, min(timeout, 60))

            return run_command(command, timeout)
        
        if tool_name == "delete_file":
            path = arguments.get("path")

            if not isinstance(path, str) or not path:
                return {
                    "success": False,
                    "error": "delete_file 缺少有效的 path 参数",
                }

            return delete_file(path)

        if tool_name == "list_files":
            path = arguments.get("path", ".")

            if not isinstance(path, str):
                return {
                    "success": False,
                    "error": "list_files 的 path 必须是字符串",
                }

            return list_files(path)

        if tool_name == "search_files":
            query = arguments.get("query")
            path = arguments.get("path", ".")
            max_results = arguments.get("max_results", 50)

            if not isinstance(query, str) or not query:
                return {
                    "success": False,
                    "error": "search_files 缺少有效的 query 参数",
                }

            if not isinstance(path, str):
                path = "."

            if not isinstance(max_results, int):
                max_results = 50

            max_results = max(1, min(max_results, 100))

            return search_files(query, path, max_results)

        if tool_name == "create_file":
            path = arguments.get("path")
            content = arguments.get("content")

            if not isinstance(path, str) or not path:
                return {
                    "success": False,
                    "error": "create_file 缺少有效的 path 参数",
                }

            if not isinstance(content, str):
                return {
                    "success": False,
                    "error": "create_file 的 content 必须是字符串",
                }

            return create_file(path, content)
        if tool_name == "apply_patch":
            path = arguments.get("path")
            old_text = arguments.get("old_text")
            new_text = arguments.get("new_text")

            if not isinstance(path, str) or not path:
                return {
                    "success": False,
                    "error": "apply_patch 缺少有效的 path 参数",
                }

            if not isinstance(old_text, str):
                return {
                    "success": False,
                    "error": "apply_patch 的 old_text 必须是字符串",
                }

            if not isinstance(new_text, str):
                return {
                    "success": False,
                    "error": "apply_patch 的 new_text 必须是字符串",
                }

            return apply_patch(path, old_text, new_text)
        
        return {
            "success": False,
            "error": f"未知工具：{tool_name}",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"工具执行异常：{exc}",
        }

        