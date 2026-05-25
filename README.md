# AI Chat API with PDF RAG

AI-powered backend built with FastAPI, OpenAI API, LangChain and ChromaDB.

This project allows:
- conversational AI,
- PDF uploads,
- semantic document search,
- Retrieval-Augmented Generation (RAG),
- streaming responses,
- summarization and translation tools.

---

# Features
- Academic review export to Word (.docx)
- AI conversational chat
- Streaming AI responses
- PDF upload endpoint
- Semantic PDF search
- Retrieval-Augmented Generation (RAG)
- OpenAI embeddings
- ChromaDB vector database
- Text summarization
- Translation
- Keyword extraction

---

# Tech Stack

- Python
- FastAPI
- OpenAI API
- LangChain
- ChromaDB
- Pydantic
- Uvicorn

---

# Project Structure

```bash
ai-chat-api/
│
├── app.py
├── rag.py
├── requirements.txt
├── runtime.txt
├── .gitignore
├── README.md
└── .env

## Live Demo

Frontend:
https://ai-chat-frontend-one.vercel.app

Backend API:
https://ai-chat-api-rag.onrender.com

## Architecture

- Frontend: Next.js + Vercel
- Backend: FastAPI + Render
- LLM: OpenAI GPT-4.1-mini
- Embeddings: OpenAI Embeddings
- Vector Store: FAISS
- Retrieval: LangChain RAG Pipeline

### Academic Article Review
POST /review-article

### Export Academic Review
POST /export-review