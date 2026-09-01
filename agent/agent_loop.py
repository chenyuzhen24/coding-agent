import json
from typing import Any
from openai import OpenAI
from agent.prompts import SYSTEM_PROMPT
from agent.tool_definitions import TOOLS
from agent.tools import execute_tool
from collections.abc import Callable


class CodingAgent:
    """一个基于 DeepSeek 工具调用的简易编程智能体。"""
    def __init__(
        self,
        client: OpenAI,
        model: str,
        max_rounds: int = 10,
        on_event: Callable[[str], None] | None = None,
        on_confirm: Callable[[str, dict[str, Any]], bool] | None = None,
        messages: list[dict[str, Any]] | None = None,  # ✅支持外部传入历史会话
    ):
        self.client = client
        self.model = model
        self.max_rounds = max_rounds
        self.on_event = on_event
        self.on_confirm = on_confirm
        if messages is not None:
            self.messages = messages
        else:
            self.messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                }
            ]

    def reset_messages(self):
        """重置为仅system prompt，新建会话"""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def emit(self, message: str) -> None:
        """向界面发送运行状态。"""
        if self.on_event:
            self.on_event(message)

    def run(self, user_task: str) -> str:
        """
        执行用户任务。
        Agent 每一轮都会：
        1. 请求 DeepSeek
        2. 判断模型是否要求调用工具
        3. 本地执行工具
        4. 将工具结果加入对话历史
        5. 继续下一轮
        """
        self.messages.append(
            {
                "role": "user",
                "content": user_task,
            }
        )
        for round_number in range(1, self.max_rounds + 1):
            self.emit(f"========== 第 {round_number} 轮 ==========")
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
            except Exception as exc:
                return f"调用 DeepSeek API 失败：{exc}"
            message = response.choices[0].message
            # 将模型消息转换为普通字典，加入历史。
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
            }
            if message.tool_calls:
                assistant_message["tool_calls"] = []
                for tool_call in message.tool_calls:
                    assistant_message["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                    )
            self.messages.append(assistant_message)
            # 没有工具调用，说明模型认为任务已经完成。
            if not message.tool_calls:
                self.emit("模型未请求工具，任务结束。")
                return message.content or "模型没有返回文本内容。"
            # 处理本轮所有工具调用。
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                raw_arguments = tool_call.function.arguments
                self.emit(f"模型请求工具：{tool_name}")
                pretty_args = json.dumps(json.loads(raw_arguments), ensure_ascii=False, indent=2)
                self.emit(f"工具参数：\n{pretty_args}")

                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    result = {
                        "success": False,
                        "error": f"工具参数不是合法 JSON：{exc}",
                    }
                else:
                    if tool_name == "delete_file":
                        if self.on_confirm is not None:
                            approved = self.on_confirm(
                                tool_name,
                                arguments,
                            )
                            if not approved:
                                result = {
                                    "success": False,
                                    "error": "用户拒绝了删除操作",
                                }
                            else:
                                result = execute_tool(
                                    tool_name,
                                    arguments,
                                )
                        else:
                            result = {
                                "success": False,
                                "error": "删除文件需要用户确认",
                            }
                    else:
                        result = execute_tool(
                            tool_name,
                            arguments,
                        )
                self.emit(f"工具执行结果：{result}")
                # tool 消息必须携带对应的 tool_call_id。
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                        ),
                    }
                )
        return (
            f"达到最大循环次数 {self.max_rounds}，"
            "程序已停止，请检查当前执行结果。"
        )
