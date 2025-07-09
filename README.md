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

## 🧱 Project Structure

tech-at-core/
├── agent/
│ ├── agent_graph.py # LangGraph logic (nodes, state machine)
│ ├── prompts.py # System prompts for various tasks
│ └── tools.py # Tools like RAG, leave balance, etc.
├── api/
│ ├── main.py # Flask API server
│ └── auth.py # JWT-based login logic
├── data/
│ ├── employee_leave_data.xlsx # Excel-based employee data
│ └── faiss_index/ # Vector DB index from policy PDF
├── docs/
│ └── Leave Policy-2.pdf # Leave policy PDF for RAG search
├── services/
│ ├── excel_handler.py # Read/write leave data from Excel
│ └── policy_rag.py # RAG system with FAISS + LangChain
├── tech_at_core_chatbot.html # Frontend (MS Teams-compatible)
├── .env # Environment config (e.g., API keys)
├── requirements.txt # Python dependencies
└── README.md # You're reading this file
---

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone <your-repository-url>
cd <your-repository-name>
2. Create Virtual Environment
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate

3. Install Dependencies
pip install -r requirements.txt

4. Set Environment Variables
Create a .env file in the root directory:

OPENAI_API_KEY="your-openai-api-key"

▶️ Running the Application
Start the Flask Backend
flask --app api.main run --port 5001
The server will start on:
📍 http://127.0.0.1:5001

Open the Frontend
Open tech_at_core_chatbot.html in your browser.
Log in using test credentials:

Employee ID: E002
Password: pass456


🧠 How It Works: Agent Architecture

🧩 LangGraph-Based Flow
🟢 Initializer Node: Sets user context and reads state "bookmark."

🔁 Router Node: Detects user intent, routes to relevant tool or flow.

📥 Leave Application Nodes: Step-by-step flow: Gather → Confirm → Submit.

🛠️ Tool Executor: Executes stateless tools like leave balance check or RAG Q&A.

📚 Memory: Employee ID and leave status persist across messages using LangGraph memory.