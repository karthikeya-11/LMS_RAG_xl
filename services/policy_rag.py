# /services/policy_rag.py

import os
import json
import logging
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

# --- Configuration ---
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'faiss_index')
LLM = ChatOpenAI(model_name="gpt-4o", temperature=0)

# --- RAG Chain Initialization ---
def _create_rag_chain(prompt_template):
    """Helper function to create a RetrievalQA chain with a given prompt."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"FAISS index not found at {DB_PATH}. Run 'run_create_vector_store.py' first.")
    
    embeddings = OpenAIEmbeddings()
    db = FAISS.load_local(DB_PATH, embeddings, allow_dangerous_deserialization=True)
    retriever = db.as_retriever(search_kwargs={'k': 3})
    
    prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
    return RetrievalQA.from_chain_type(
        llm=LLM, chain_type="stuff", retriever=retriever, chain_type_kwargs={"prompt": prompt}
    )

# --- Specific Chains for Different Tasks ---

# Chain for policy compliance checks (returns JSON)
compliance_prompt = """
You are an expert HR policy analyst. Use the provided context to answer the question.
Your answer MUST be a single JSON object with two keys: "compliant" (boolean) and "reason" (string explaining your decision based on the context).
Context: {context}
Question: {question}
Answer (JSON only):
"""
compliance_chain = _create_rag_chain(compliance_prompt)

# Chain for general Q&A (returns natural language text)
qa_prompt = """
You are a helpful HR assistant. Use the provided context from the company policy document to answer the user's question accurately and concisely.
If the context doesn't contain the answer, state that the information is not available in the policy document.
Context: {context}
Question: {question}
Helpful Answer:
"""
qa_chain = _create_rag_chain(qa_prompt)


# --- Public Functions ---

def check_policy_compliance(leave_type: str, num_days: int, reason: str = "") -> dict:
    """Checks if a leave request is compliant with company policy using RAG."""
    query = (
        f"An employee is requesting a '{leave_type}' leave for {num_days} day(s). "
        f"The reason given is: '{reason}'. "
        f"Based *only* on the provided policy context, is this request compliant? "
        f"Check rules on duration, advance notice, and documentation like the 'Leave Application & Approval Process'."
    )
    
    try:
        result = compliance_chain.invoke({"query": query})
        response_text = result['result'].strip().replace("```json", "").replace("```", "")
        json_response = json.loads(response_text)
        
        if "compliant" not in json_response or "reason" not in json_response:
            raise ValueError("Malformed JSON response from LLM.")
            
        logging.info(f"Policy check successful. Compliant: {json_response['compliant']}.")
        return json_response
        
    except Exception as e:
        logging.error(f"RAG policy check failed: {e}")
        return {"compliant": False, "reason": "An unexpected error occurred during policy analysis."}

def answer_general_question(question: str) -> str:
    """Answers a general question using the policy document."""
    try:
        result = qa_chain.invoke({"query": question})
        return result['result']
    except Exception as e:
        logging.error(f"RAG general question failed: {e}")
        return "I'm sorry, I encountered an error trying to find an answer in the policy document."