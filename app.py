from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    StreamingResponse,
    JSONResponse,
    FileResponse,
)

from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel

import os
import shutil
import traceback
import re

from datetime import datetime

from sqlalchemy.orm import Session

from database import (
    SessionLocal,
    engine,
    Base,
)

from models import (
    Review,
    User,
)

from auth import (
    hash_password,
    verify_password,
)

from docx import Document

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
)

from langchain_openai import (
    OpenAIEmbeddings,
    ChatOpenAI,
)

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)

from langchain_community.document_loaders import (
    PyPDFLoader,
)

from langchain_community.vectorstores import (
    FAISS,
)

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://ai-chat-frontend-one.vercel.app",
        "https://ai-chat-frontend-h92larnka-jrolandomxs-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

llm = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
)

vectorstore = None
uploaded_documents = []
last_article_review = ""

conversation_history = [
    {
        "role": "system",
        "content": (
            "Eres un asistente académico y técnico. "
            "Respondes de forma clara, precisa y profesional."
        ),
    }
]


class ChatRequest(BaseModel):
    prompt: str


class TextRequest(BaseModel):
    text: str


class PDFQuestionRequest(BaseModel):
    question: str


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


def detect_ai_probability(text: str):
    generic_patterns = [
        "en conclusión",
        "es importante destacar",
        "en la actualidad",
        "cabe mencionar",
        "de manera significativa",
        "en este sentido",
        "por otro lado",
    ]

    matches = 0

    text_lower = text.lower()

    for pattern in generic_patterns:
        if pattern in text_lower:
            matches += 1

    if matches >= 5:
        return "Alta"

    if matches >= 3:
        return "Media"

    return "Baja"


def blind_review_text(text: str):
    patterns = [
        r"(?i)autor[a-z]*:.*",
        r"(?i)authors?:.*",
        r"(?i)afiliaci[oó]n:.*",
        r"(?i)universidad.*",
        r"(?i)correo.*",
        r"(?i)e-mail.*",
        r"(?i)email.*",
        r"(?i)orcid.*",
        r"(?i)agradecimientos.*",
    ]

    for pattern in patterns:
        text = re.sub(
            pattern,
            "[DATOS OCULTOS PARA REVISIÓN CIEGA]",
            text,
        )

    return text


@app.get("/")
def home():
    return {
        "message": "AI Academic Reviewer API funcionando"
    }


@app.post("/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()

    existing_user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing_user:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Usuario ya existe"
            },
        )

    new_user = User(
        username=username,
        password=hash_password(password),
    )

    db.add(new_user)

    db.commit()

    return {
        "message": "Usuario registrado"
    }


@app.post("/login")
def login(
    username: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()

    user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if not user:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Usuario no encontrado"
            },
        )

    if not verify_password(
        password,
        user.password,
    ):
        return JSONResponse(
            status_code=401,
            content={
                "error": "Contraseña incorrecta"
            },
        )

    return {
        "message": "Login correcto",
        "username": user.username,
    }


@app.post("/chat")
def chat(request: ChatRequest):
    conversation_history.append({
        "role": "user",
        "content": request.prompt,
    })

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=conversation_history,
    )

    assistant_response = (
        response.choices[0].message.content
    )

    conversation_history.append({
        "role": "assistant",
        "content": assistant_response,
    })

    return {
        "response": assistant_response,
        "history": conversation_history,
    }


@app.post("/chat-stream")
async def chat_stream(request: ChatRequest):
    conversation_history.append({
        "role": "user",
        "content": request.prompt,
    })

    stream = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=conversation_history,
        stream=True,
    )

    async def generate():
        full_response = ""

        for chunk in stream:
            content = chunk.choices[0].delta.content

            if content:
                full_response += content
                yield content

        conversation_history.append({
            "role": "assistant",
            "content": full_response,
        })

    return StreamingResponse(
        generate(),
        media_type="text/plain",
    )


@app.post("/summarize")
def summarize(request: TextRequest):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Resume el texto en máximo 5 líneas."
                ),
            },
            {
                "role": "user",
                "content": request.text,
            },
        ],
    )

    return {
        "summary": response.choices[0].message.content
    }


@app.post("/translate")
def translate(request: TextRequest):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Traduce el texto al inglés."
                ),
            },
            {
                "role": "user",
                "content": request.text,
            },
        ],
    )

    return {
        "translation": response.choices[0].message.content
    }


@app.post("/keywords")
def keywords(request: TextRequest):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extrae de 5 a 10 palabras clave."
                ),
            },
            {
                "role": "user",
                "content": request.text,
            },
        ],
    )

    return {
        "keywords": response.choices[0].message.content
    }


@app.post("/upload-pdf")
def upload_pdf(
    file: UploadFile = File(...),
):
    global vectorstore
    global uploaded_documents
    global last_article_review

    try:
        os.makedirs(
            "uploaded_files",
            exist_ok=True,
        )

        file_path = (
            f"uploaded_files/{file.filename}"
        )

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer,
            )

        loader = PyPDFLoader(file_path)

        documents = loader.load()

        uploaded_documents = documents

        last_article_review = ""

        text_splitter = (
            RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
            )
        )

        chunks = text_splitter.split_documents(
            documents
        )

        embeddings = OpenAIEmbeddings(
            api_key=os.getenv(
                "OPENAI_API_KEY"
            ),
        )

        vectorstore = FAISS.from_documents(
            documents=chunks,
            embedding=embeddings,
        )

        return {
            "message": "PDF cargado correctamente",
            "filename": file.filename,
            "pages": len(documents),
            "chunks": len(chunks),
        }

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            },
        )


@app.post("/ask-pdf")
def ask_pdf(request: PDFQuestionRequest):
    global vectorstore

    try:
        if vectorstore is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "Primero debes subir un PDF"
                    )
                },
            )

        results = vectorstore.similarity_search(
            request.question,
            k=3,
        )

        context = "\n\n".join([
            doc.page_content
            for doc in results
        ])

        prompt = f"""
Responde usando únicamente la información del contexto.

Contexto:
{context}

Pregunta:
{request.question}
"""

        response = llm.invoke(prompt)

        return {
            "answer": response.content,
            "sources": [
                {
                    "page": doc.metadata.get("page"),
                    "content": (
                        doc.page_content[:300]
                    ),
                }
                for doc in results
            ],
        }

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            },
        )


@app.post("/review-article")
def review_article(
    review_type: str = Form("Scopus"),
    blind_review: bool = Form(True),
):
    global uploaded_documents
    global last_article_review

    try:
        if not uploaded_documents:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "Primero debes subir un artículo PDF"
                    )
                },
            )

        full_text = "\n\n".join([
            doc.page_content
            for doc in uploaded_documents
        ])

        if blind_review:
            full_text = blind_review_text(
                full_text
            )

        max_chars = 30000

        if len(full_text) > max_chars:
            full_text = full_text[:max_chars]

        review_prompt = f"""
Eres un sistema multiagente de arbitraje académico especializado en evaluación científica.

Tipo de evaluación:
{review_type}

Debes actuar simultáneamente como:

1. Revisor metodológico
2. Revisor teórico
3. Revisor editorial
4. Revisor APA
5. Editor en jefe

Analiza el siguiente artículo científico:

{full_text}

Genera un dictamen PROFUNDO, EXTENSO, CRÍTICO y CONSTRUCTIVO.

Usa EXACTAMENTE esta estructura:

# Dictamen académico multiagente

# Badge de dictamen editorial

# Score general del artículo

# Revisión metodológica

# Revisión teórica

# Revisión editorial y de redacción

# Revisión APA y formato

# Tabla sintética de observaciones

# Fortalezas

# Debilidades

# Recomendaciones concretas

# Dictamen final del editor en jefe
"""

        response = llm.invoke(review_prompt)

        last_article_review = response.content

        ai_probability = detect_ai_probability(
            response.content
        )

        badge = (
            "Requiere cambios mayores"
        )

        review_lower = (
            response.content.lower()
        )

        if (
            "aceptado sin cambios"
            in review_lower
        ):
            badge = (
                "Aceptado sin cambios"
            )

        elif (
            "aceptado con cambios menores"
            in review_lower
        ):
            badge = (
                "Aceptado con cambios menores"
            )

        elif "rechazado" in review_lower:
            badge = "Rechazado"

        db = SessionLocal()

        auto_score = str(
            min(
                100,
                max(
                    55,
                    len(response.content)
                    // 120
                ),
            )
        )

        new_review = Review(
            filename="uploaded_article.pdf",
            review_type=review_type,
            badge=badge,
            score=auto_score,
            review=response.content,
            ai_probability=ai_probability,
        )

        db.add(new_review)

        db.commit()

        return {
            "review": response.content,
            "badge": badge,
            "ai_probability": ai_probability,
            "score": auto_score,
        }

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            },
        )


@app.get("/reviews")
def get_reviews():
    db = SessionLocal()

    reviews = (
        db.query(Review)
        .order_by(
            Review.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": review.id,
            "filename": review.filename,
            "review_type": review.review_type,
            "badge": review.badge,
            "score": review.score,
            "ai_probability": (
                review.ai_probability
            ),
            "created_at": (
                review.created_at
            ),
        }
        for review in reviews
    ]


@app.get("/dashboard")
def dashboard():
    db = SessionLocal()

    reviews = db.query(Review).all()

    total = len(reviews)

    accepted = len([
        r
        for r in reviews
        if r.badge
        == "Aceptado sin cambios"
    ])

    minor = len([
        r
        for r in reviews
        if r.badge
        == "Aceptado con cambios menores"
    ])

    major = len([
        r
        for r in reviews
        if r.badge
        == "Requiere cambios mayores"
    ])

    rejected = len([
        r
        for r in reviews
        if r.badge
        == "Rechazado"
    ])

    return {
        "total_reviews": total,
        "accepted": accepted,
        "minor_changes": minor,
        "major_changes": major,
        "rejected": rejected,
    }


@app.get("/review/{review_id}")
def get_review(review_id: int):
    db = SessionLocal()

    review = (
        db.query(Review)
        .filter(
            Review.id == review_id
        )
        .first()
    )

    if not review:
        return JSONResponse(
            status_code=404,
            content={
                "error": (
                    "Revisión no encontrada"
                )
            },
        )

    return {
        "id": review.id,
        "filename": review.filename,
        "review_type": review.review_type,
        "badge": review.badge,
        "score": review.score,
        "review": review.review,
        "ai_probability": (
            review.ai_probability
        ),
        "created_at": review.created_at,
    }


@app.post("/compare-reviews")
def compare_reviews(
    original_text: str = Form(...),
    corrected_text: str = Form(...),
):
    prompt = f"""
Compara ambas versiones de un artículo académico.

VERSIÓN ORIGINAL:
{original_text}

VERSIÓN CORREGIDA:
{corrected_text}

Evalúa:

1. Qué observaciones fueron atendidas
2. Qué problemas persisten
3. Qué mejoró
4. Qué sigue faltando
5. Nivel de mejora general

Redacta en formato académico.
"""

    response = llm.invoke(prompt)

    return {
        "comparison": response.content
    }


@app.post("/export-review")
def export_review():
    return export_review_word()


@app.post("/export-review-word")
def export_review_word():
    global last_article_review

    try:
        if not last_article_review:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "Primero debes generar un dictamen"
                    )
                },
            )

        document = Document()

        document.add_heading(
            "Dictamen académico",
            level=1,
        )

        document.add_paragraph(
            (
                "Fecha: "
                f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
        )

        for line in (
            last_article_review.split("\n")
        ):
            clean = line.strip()

            if not clean:
                continue

            if clean.startswith("# "):
                document.add_heading(
                    clean.replace(
                        "# ",
                        "",
                    ),
                    level=1,
                )

            elif clean.startswith("## "):
                document.add_heading(
                    clean.replace(
                        "## ",
                        "",
                    ),
                    level=2,
                )

            else:
                document.add_paragraph(
                    clean
                )

        file_path = (
            "dictamen_academico.docx"
        )

        document.save(file_path)

        return FileResponse(
            path=file_path,
            filename=(
                "dictamen_academico.docx"
            ),
            media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            },
        )


@app.post("/export-review-pdf")
def export_review_pdf():
    global last_article_review

    try:
        if not last_article_review:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "Primero debes generar un dictamen"
                    )
                },
            )

        file_path = (
            "dictamen_academico.pdf"
        )

        doc = SimpleDocTemplate(
            file_path
        )

        styles = (
            getSampleStyleSheet()
        )

        elements = []

        elements.append(
            Paragraph(
                "Dictamen académico",
                styles["Heading1"],
            )
        )

        elements.append(
            Spacer(1, 12)
        )

        elements.append(
            Paragraph(
                (
                    "Fecha: "
                    f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
                ),
                styles["BodyText"],
            )
        )

        elements.append(
            Spacer(1, 12)
        )

        for line in (
            last_article_review.split("\n")
        ):
            clean = line.strip()

            if not clean:
                continue

            elements.append(
                Paragraph(
                    clean,
                    styles["BodyText"],
                )
            )

            elements.append(
                Spacer(1, 8)
            )

        doc.build(elements)

        return FileResponse(
            path=file_path,
            filename=(
                "dictamen_academico.pdf"
            ),
            media_type="application/pdf",
        )

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            },
        )