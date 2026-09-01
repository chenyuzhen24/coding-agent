TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "删除 workspace 目录中的一个已有文件。"
                "只能删除普通文件，不能删除目录或 workspace 外部的路径。"
                "这是一个高风险操作，执行前必须获得用户明确同意。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "要删除的文件相对于 workspace 的路径，"
                            "例如 temporary.txt"
                        ),
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": (
                "在 workspace 目录中创建一个全新的文本文件。"
                "如果文件已存在，工具会拒绝操作，不能用于覆盖已有文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "新文件相对于 workspace 的路径，"
                            "例如 src/main.py 或 README.md"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "新文件的完整文本内容",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出 workspace 中的项目文件和目录，用于了解项目结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于 workspace 的目录路径，默认为 .",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "在 workspace 的文本文件中搜索代码或文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的字符串",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索范围，默认为 .",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回多少条结果，默认 50",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": (
                "对已有文本文件进行局部修改。"
                "old_text 必须在文件中唯一匹配，new_text 是替换后的代码。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件相对于 workspace 的路径",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "需要被替换的原始代码片段",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "替换后的新代码片段",
                    },
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取 workspace 目录中的文本文件。"
                "只能使用相对于 workspace 的路径。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件相对于 workspace 的路径，例如 calculator.py",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "向 workspace 目录中的文本文件写入完整内容。"
                "如果文件不存在则创建，如果存在则覆盖。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件相对于 workspace 的路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入文件的完整文本内容",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "在 workspace 目录中执行 Windows 命令。"
                "适合运行 Python 程序、测试和检查命令。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "要执行的 Windows 命令，例如 "
                            "python calculator.py"
                        ),
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "命令最大执行时间，单位为秒，默认 30 秒",
                        "minimum": 1,
                        "maximum": 60,
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
]