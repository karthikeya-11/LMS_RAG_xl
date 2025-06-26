# Script to create the FAISS index 

import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv()

PDF_PATH = os.path.join(os.path.dirname(__file__), 'docs', 'Leave Policy-2.pdf')
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'faiss_index')

def create_vector_store():
    print("Loading PDF...")
    if not os.path.exists(PDF_PATH):
        print(f"ERROR: PDF not found at {PDF_PATH}")
        print("Please create 'LeavePolicy.pdf' from 'LeavePolicy.md' and place it in the /docs folder.")
        return

    loader = PyPDFLoader(PDF_PATH)
    documents = loader.load()
    
    print("Splitting text...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    texts = text_splitter.split_documents(documents)
    
    print("Generating embeddings and creating FAISS store...")
    embeddings = OpenAIEmbeddings()
    db = FAISS.from_documents(texts, embeddings)
    
    print(f"Saving FAISS index to {DB_PATH}...")
    db.save_local(DB_PATH)
    print("Vector store created successfully.")

if __name__ == "__main__":
    create_vector_store()