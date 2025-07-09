# tech.at.core - LMS & HR Services Bot

## 1. Overview

This project is a sophisticated, AI-powered HR Assistant for **tech.at.core**, designed to streamline the leave management process for our employees. Built with Python, Flask, and the powerful LangChain/LangGraph framework, this chatbot provides a conversational interface for handling a variety of leave-related tasks.

The agent is designed to be intelligent and stateful. It can answer questions about company leave policies by searching a PDF document (RAG), manage a multi-step leave application process with memory, and apply common-sense rules to user requests.

## 2. Features

- **Integrated, Intelligent & Always Available**
- **🧩 Built into Microsoft Teams** – Works where your team already communicates
- **⚡ Instant Responses** – No more waiting on HR for basic queries
- **🕐 Available 24/7** – Accessible anytime, even outside office hours
- **📚 Policy-Aware** – Answers backed by the official leave policy document

### What Can It Do?
- Check Leave Balance
- View Leave History
- Submit Leave Request
- Ask Policy Questions
- View Company Holidays

## 3. Screenshots

<img src="https://github.com/karthikeya-11/LMS_RAG_xl/blob/new-v3/image.png?raw=true" />


<img src="https://github.com/karthikeya-11/LMS_RAG_xl/blob/new-v3/image_png.png?raw=true" />





## 4. Tech Stack

- **Backend:** Python, Flask
- **AI & Orchestration:** LangChain, LangGraph
- **LLM:** OpenAI (gpt-4o)
- **Vector Store:** FAISS (for RAG)
- **Data Storage:** Pandas (for reading/writing to Excel)
- **Frontend:** HTML, Tailwind CSS, JavaScript

## 5. Project Structure

```
.
├── agent/
│   ├── agent_graph.py      # Core logic for the LangGraph state machine.
│   ├── prompts.py          # System prompts that define the agent's personality and rules.
│   └── tools.py            # Defines all the functions the agent can call (RAG, Excel checks, etc.).
├── api/
│   ├── main.py             # The main Flask application, defines API endpoints.
│   └── auth.py             # Handles JWT token creation and validation.
├── data/
│   ├── employee_leave_data.xlsx # The "database" for employee and leave information.
│   └── faiss_index/        # The vector store created from the policy PDF.
├── docs/
│   └── Leave Policy-2.pdf  # The source document for the RAG system.
├── services/
│   ├── excel_handler.py    # Functions for reading from and writing to the Excel file.
│   └── policy_rag.py       # Manages the RAG chain for answering policy questions.
├── .env                    # Stores environment variables (e.g., API keys).
├── requirements.txt        # Lists all Python dependencies.
└── tech_at_core_chatbot.html # The frontend user interface.
```

## 6. Setup and Installation

Follow these steps to get the application running on your local machine.

### Step 1: Clone the Repository

```bash
git clone <your-repository-url>
cd <your-repository-name>
```

### Step 2: Create a Virtual Environment

It's highly recommended to use a virtual environment to manage dependencies.

```bash
# For Windows
python -m venv venv
venv\Scripts\activate

# For macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

Install all the required Python libraries from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### Step 4: Set Up Environment Variables

Create a file named `.env` in the root directory of the project and add your OpenAI API key:

```
OPENAI_API_KEY="your-openai-api-key-here"
```

## 7. Running the Application

### Step 1: Start the Backend Server

Run the Flask application from the root directory.

```bash
flask --app api.main run --port 5001
```

The server will start, and you will see the running URL in your terminal (usually `http://127.0.0.1:5001`).

### Step 2: Open the Frontend

Open the `tech_at_core_chatbot.html` file in your web browser. You can simply double-click the file.

You can now log in using the dummy credentials (e.g., Employee ID: `E002`, Password: `pass456`) and start interacting with the chatbot.

## 8. How It Works: The Agent Architecture

The core of this application is the **LangGraph State Machine** defined in `agent/agent_graph.py`. Unlike a simple chain, this graph allows the agent to have a robust, multi-step memory and make intelligent decisions.

- **Initializer (`initialize_node`):** This is the entry point for every message. It loads the conversation's memory and ensures the agent knows which user it's talking to. It then reads a "bookmark" to see if it's in the middle of a process.

- **Router (`router_node`):** This is the agent's main brain. For new topics, it analyzes the user's intent and decides whether to answer a question with a tool or to start the leave application process.

- **Leave Flow Nodes (`leave_gather`, `leave_confirm`, `leave_submit`):** These nodes form a sub-process. Each node is responsible for one step of the leave application. After each step, the graph **stops and waits** for the user's reply, ensuring the conversation doesn't get stuck in a loop.

- **Tool Executor (`tool_executor_node`):** This node is responsible for running simple, one-shot tools like checking a leave balance or performing a RAG search on the policy document.
