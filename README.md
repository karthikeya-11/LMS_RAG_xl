# 💼 tech.at.core – LMS & HR Services Bot

A smart, AI-powered HR assistant built for **tech.at.core**, designed to simplify and automate the leave management system using state-of-the-art LLMs and LangGraph workflows.

---

## 📌 Overview

The **tech.at.core LMS Bot** is a conversational AI assistant that integrates directly into your team’s workflow (via Microsoft Teams), enabling employees to handle their leave-related needs seamlessly. Leveraging **LangChain + LangGraph**, the bot offers stateful conversations, policy-aware answers, and intelligent task automation.

This project is crafted using **Python, Flask, LangGraph, FAISS, and OpenAI’s GPT-4o**, delivering a complete end-to-end system combining intelligent routing, retrieval-augmented generation (RAG), and real-time task execution.

---

## 🚀 Key Features

### 🔄 Integrated & Intelligent
- **LangGraph-powered state machine** enables memory across multi-turn conversations.
- **RAG-based answers** sourced directly from the company's official policy document.

### 💬 HR Tasks Made Conversational
- ✅ **Check Leave Balance** – Instantly view your remaining leave.
- 📆 **View Leave History** – Track your past leave records.
- 📝 **Submit Leave Request** – Guided, step-by-step leave application flow.
- 📖 **Ask HR Policy Questions** – Natural language Q&A with grounded answers.
- 📅 **View Company Holidays** – Get a calendar overview of all holidays.

### ⚙️ Productivity-Boosting
- ⚡ **Instant Responses** – No delays or HR wait time.
- 🧩 **Built into Microsoft Teams** – Use where your team already works.
- 🌐 **Accessible 24/7** – Anytime access, even outside office hours.
- 🔐 **Secure Auth** – JWT-based authentication and role validation.

---

## 📸 Screenshots

> *(Add application demo screenshots here)*  
> E.g., Chat UI, Leave Balance Card, Leave Flow Walkthrough, Policy Q&A

---

## 🛠️ Tech Stack

| Layer          | Technologies Used                                     |
|----------------|--------------------------------------------------------|
| **Backend**    | Python, Flask                                          |
| **Frontend**   | HTML, Tailwind CSS, JavaScript                         |
| **AI/Logic**   | OpenAI GPT-4o, LangChain, LangGraph                    |
| **RAG/Memory** | FAISS (Vector Store), Pandas (Excel data management)   |
| **Storage**    | Excel (employee_leave_data.xlsx)                       |
| **Auth**       | JWT Token-based authentication                         |

---

Tech at Core - Employee Leave Management System
🧱 Project Structure
tech-at-core/
├── agent/
│   ├── agent_graph.py      # LangGraph logic (nodes, routing, memory)
│   ├── prompts.py          # System prompts for tools and agent personality
│   └── tools.py            # Tool functions: RAG, Excel data ops, etc.
├── api/
│   ├── main.py             # Main Flask app and routes
│   └── auth.py             # JWT login/authentication handling
├── data/
│   ├── employee_leave_data.xlsx  # Excel file acting as employee database
│   └── faiss_index/       # Vector store index from leave policy PDF
├── docs/
│   └── Leave Policy-2.pdf  # Source PDF used for RAG Q&A
├── services/
│   ├── excel_handler.py    # Read/write operations for Excel DB
│   └── policy_rag.py       # RAG pipeline setup using LangChain + FAISS
├── tech_at_core_chatbot.html  # Simple web UI (or Teams-compatible frontend)
├── .env                    # Environment variables (OpenAI API key, etc.)
├── requirements.txt        # Python dependencies
└── README.md              # You're reading this file
⚙️ Setup & Installation
1. Clone the Repository
bashgit clone <your-repository-url>
cd <your-repository-name>
2. Create a Virtual Environment
bash# For Windows
python -m venv venv
venv\Scripts\activate

# For macOS/Linux
python3 -m venv venv
source venv/bin/activate
3. Install Dependencies
bashpip install -r requirements.txt
4. Set Environment Variables
Create a .env file in the root directory and add:
envOPENAI_API_KEY="your-openai-api-key"
▶️ Running the Application
Step 1: Start the Backend Server
bashflask --app api.main run --port 5001
The Flask server will start at:
📍 http://127.0.0.1:5001
Step 2: Open the Frontend
Open the file tech_at_core_chatbot.html in your browser.
Use the following test credentials:
yamlEmployee ID: E002  
Password: pass456
🧠 How It Works: Agent Architecture
The core logic is powered by a LangGraph state machine, built to handle stateful, intelligent conversations using nodes and edges:
🟢 Initializer Node
Loads conversation memory and determines the current "bookmark" (e.g., mid-process location) for that user.
🔁 Router Node
Detects user intent and routes the request to the correct tool or flow (e.g., leave process or policy Q&A).
📥 Leave Flow Nodes
A structured 3-step process:

leave_gather: Gathers leave details
leave_confirm: Confirms user request
leave_submit: Final submission and update

🛠️ Tool Executor Node
Executes single-turn utilities:

Check leave balance
View leave history
Search policy document (RAG)
View holiday calendar

💾 Stateful Memory
LangGraph maintains persistent context (e.g., employee ID) across steps to avoid re-asking redundant questions.