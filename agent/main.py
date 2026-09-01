import os

from dotenv import load_dotenv
from openai import OpenAI

from agent.agent_loop import CodingAgent
from agent.prompts import SYSTEM_PROMPT

def create_client_and_model() -> tuple[OpenAI, str]:
    """创建 DeepSeek 客户端。"""
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
        raise RuntimeError(
            "没有找到 DEEPSEEK_API_KEY，请检查 .env 文件"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    return client, model

def main():
    client, model = create_client_and_model()

    agent = CodingAgent(
        client=client,
        model=model,
        max_rounds=20,
    )

    print("简易编程智能体已启动。")
    print("工作目录：workspace")
    print("输入 quit 或 exit 退出程序。")

    while True:
        try:
            task = input("\n请输入编程任务：").strip()
        except KeyboardInterrupt:
            print("\n程序已退出。")
            break

        if task.lower() in {"quit", "exit"}:
            print("程序已退出。")
            break

        if not task:
            print("任务不能为空。")
            continue

        result = agent.run(task)

        print("\n========== 最终结果 ==========")
        print(result)

        # 每次任务完成后保留 system prompt，
        # 避免不同任务之间的历史互相干扰。
        agent.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

if __name__ == "__main__":
    main()