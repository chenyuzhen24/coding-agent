# Coding‑Agent 编程智能体
> 基于 DeepSeek Function‑calling 从零实现的本地编程智能体，不使用 LangChain、AutoGen 等第三方 Agent 框架。

## 项目目录结构
```
coding-agent/
├── .venv/                  # Python虚拟环境（Git忽略）
├── agent/                  # Agent核心代码模块
│   ├── __init__.py
│   ├── agent_loop.py       # Agent主思考循环，处理模型与工具调用流转
│   ├── prompts.py          # 系统提示词，定义Agent行为约束
│   ├── tool_definitions.py # Function‑Call工具Schema定义
│   ├── tools.py            # 文件操作、命令执行工具实现
│   ├── session_manager.py  # 会话持久化管理
│   ├── gui.py              # Tkinter图形界面启动入口
│   ├── main.py             # 命令行交互启动入口
│   └── __pycache__/        # Python编译缓存，Git忽略
├── sessions/               # 会话存储目录，保存对话历史JSON
├── workspace/              # Agent沙箱工作目录，所有文件操作限制于此
├── .env                    # 本地密钥配置，禁止提交到仓库
├── .env.example            # 环境变量模板文件
├── .gitignore              # Git忽略规则
└── requirements.txt        # 项目依赖列表
```

## 项目简介
本项目手写实现完整的AI编程Agent调度逻辑。大模型接收用户编程需求后，可以自主调用本地工具完成文件读写、代码修改、文本检索、运行命令测试代码等任务。

- 沙箱安全隔离：强制限制全部文件操作仅在`workspace`目录，抵御路径穿越攻击，拦截高危系统命令
- 会话持久化：完整保存多轮对话，支持新建、加载、删除历史会话
- 双运行入口：Tkinter图形GUI界面 + 控制台命令行模式
- 无Agent框架依赖：Function‑call解析、Agent思考循环全部自主实现

## 环境依赖
依赖已写入 requirements.txt，主要依赖：
- openai>=1.0.0
- python-dotenv

### 环境准备
```cmd
# 创建虚拟环境
python -m venv .venv
# 激活虚拟环境 Windows
.venv\Scripts\activate
# 安装项目依赖
pip install -r requirements.txt
```

## 配置API密钥
复制 `.env.example` 文件，重命名为 `.env`，填入自己的 DeepSeek API 密钥。
```env
DEEPSEEK_API_KEY=sk-xxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```
> 注意：不要将 `.env` 文件提交至代码仓库，防止密钥泄露。

## 启动运行
> 需要进入 agent 目录再执行启动命令

### 图形界面（推荐）
```cmd
cd agent
python gui.py
```
GUI功能说明：
- 左侧：workspace文件树与会话列表，支持新建、删除、加载会话
- 中间：简易文本编辑器，可以打开、编辑工作区内文件
- 右侧：聊天交互面板，输入编程任务，查看Agent思考与工具调用过程；删除文件操作会弹出确认弹窗。

### 命令行模式
```cmd
cd agent
python main.py
```

## 内置工具能力
|工具|功能说明|
|---|---|
|list_files|列出workspace内目录文件|
|read_file|读取指定文件内容|
|create_file / write_file|新建、覆写文件内容|
|apply_patch|增量补丁方式修改代码，避免完整重写文件|
|search_files|在工作区内检索文本内容|
|delete_file|删除文件，GUI模式需要二次确认|
|run_command|执行受限Shell命令，拦截危险命令，增加超时保护|

## 安全说明
1. Agent所有文件读写、创建操作强制限制在 `./workspace`，无法访问项目外部系统文件，防御`../`路径逃逸。
2. run_command 内置命令黑名单，拦截破坏性高危指令。
3. delete_file 删除操作在GUI界面增加手动确认步骤，避免AI误删。
4. API密钥仅保存在本地.env，不会上传至任何外部服务。

## 使用示例流程
1. 进入agent目录，启动程序
2. 输入任务，例如：编写一个python冒泡排序，并编写单元测试运行验证
3. Agent自动创建源码文件、测试用例，执行命令运行单元测试，根据报错迭代修改代码
4. 所有输出文件保存在 workspace 目录

## License
MIT