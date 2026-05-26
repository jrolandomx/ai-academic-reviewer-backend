from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from docx import Document
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

import os
import shutil
import traceback
import re

from database import SessionLocal, engine, Base
from models import User, Review, Article
from auth import hash_password, verify_password, create_access_token
from security import get_current_user, admin_required

from langchain_community.document_loaders import PyPDFLoader

load_dotenv()

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Academic Reviewer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://ai-academic-reviewer-frontend.vercel.app",
        "https://ai-chat-frontend-one.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

uploaded_pdf_text = ""
uploaded_filename = ""
last_article_review = ""


class AuthRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str | None = None
    prompt: str | None = None


class CompareRequest(BaseModel):
    original_text: str
    corrected_text: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        text = re.sub(pattern, "[DATOS OCULTOS PARA REVISIÓN CIEGA]", text)

    return text


def detect_ai_probability(text: str):
    patterns = [
        "en conclusión",
        "es importante destacar",
        "en la actualidad",
        "cabe mencionar",
        "en este sentido",
        "por otro lado",
        "de manera significativa",
    ]

    count = 0
    lower = text.lower()

    for pattern in patterns:
        if pattern in lower:
            count += 1

    if count >= 5:
        return "Alta"

    if count >= 3:
        return "Media"

    return "Baja"


def calculate_score(text: str):
    return str(
        min(
            100,
            max(
                55,
                len(text) // 120,
            ),
        )
    )


def detect_badge(text: str):
    lower = text.lower()

    if "rechazado" in lower:
        return "Rechazado"

    if "aceptado sin cambios" in lower:
        return "Aceptado sin cambios"

    if "aceptado con cambios menores" in lower:
        return "Aceptado con cambios menores"

    return "Requiere cambios mayores"


def status_from_badge(badge: str):
    if badge == "Aceptado sin cambios":
        return "accepted"

    if badge == "Aceptado con cambios menores":
        return "minor_revision"

    if badge == "Rechazado":
        return "rejected"

    return "major_revision"


@app.get("/")
def root():
    return {"message": "AI Academic Reviewer API funcionando correctamente"}


@app.post("/register")
def register(auth: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == auth.username).first()

    if user:
        raise HTTPException(status_code=400, detail="Usuario ya existe")

    new_user = User(
        username=auth.username,
        password=hash_password(auth.password),
        role="reviewer",
    )

    db.add(new_user)
    db.commit()

    return {"message": "Usuario registrado"}


@app.post("/login")
def login(auth: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == auth.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    if not verify_password(auth.password, user.password):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    token = create_access_token({"sub": user.username})

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    global uploaded_pdf_text, uploaded_filename, last_article_review

    try:
        os.makedirs("uploaded_files", exist_ok=True)

        file_path = f"uploaded_files/{file.filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        loader = PyPDFLoader(file_path)
        documents = loader.load()

        uploaded_pdf_text = "\n\n".join([doc.page_content for doc in documents])
        uploaded_filename = file.filename
        last_article_review = ""

        return {
            "message": "PDF cargado correctamente",
            "filename": file.filename,
            "pages": len(documents),
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/articles")
async def create_article(
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    os.makedirs("uploaded_files", exist_ok=True)

    file_path = f"uploaded_files/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    article = Article(
        title=title,
        filename=file.filename,
        status="submitted",
    )

    db.add(article)
    db.commit()
    db.refresh(article)

    return {
        "message": "Artículo creado",
        "article_id": article.id,
        "title": article.title,
        "filename": article.filename,
        "status": article.status,
    }


@app.get("/articles")
def get_articles(db: Session = Depends(get_db)):
    articles = db.query(Article).order_by(Article.created_at.desc()).all()

    return [
        {
            "id": article.id,
            "title": article.title,
            "filename": article.filename,
            "status": article.status,
            "created_at": article.created_at,
            "reviews_count": len(article.reviews),
        }
        for article in articles
    ]


@app.get("/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()

    if not article:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    return {
        "id": article.id,
        "title": article.title,
        "filename": article.filename,
        "status": article.status,
        "created_at": article.created_at,
        "reviews": [
            {
                "id": review.id,
                "reviewer_id": review.reviewer_id,
                "review_type": review.review_type,
                "score": review.score,
                "badge": review.badge,
                "ai_probability": review.ai_probability,
                "created_at": review.created_at,
            }
            for review in article.reviews
        ],
    }


@app.post("/articles/{article_id}/assign")
def assign_reviewer(
    article_id: int,
    reviewer_id: int = Form(...),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    reviewer = db.query(User).filter(User.id == reviewer_id).first()

    if not article:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    if not reviewer:
        raise HTTPException(status_code=404, detail="Revisor no encontrado")

    article.status = "under_review"

    db.commit()

    return {
        "message": "Revisor asignado",
        "article": article.title,
        "reviewer": reviewer.username,
        "status": article.status,
    }


@app.post("/articles/{article_id}/status")
def update_article_status(
    article_id: int,
    status: str = Form(...),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    allowed_statuses = [
        "submitted",
        "under_review",
        "minor_revision",
        "major_revision",
        "accepted",
        "rejected",
        "published",
    ]

    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Estado editorial no válido")

    article = db.query(Article).filter(Article.id == article_id).first()

    if not article:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    article.status = status
    db.commit()

    return {
        "message": "Estado actualizado",
        "article_id": article.id,
        "status": article.status,
    }


@app.post("/ask-pdf")
async def ask_pdf(question: str = Form(...)):
    global uploaded_pdf_text

    try:
        if not uploaded_pdf_text:
            raise HTTPException(status_code=400, detail="Primero debes subir un PDF")

        context = uploaded_pdf_text[:25000]

        prompt = f"""
Responde únicamente con base en el siguiente documento.

DOCUMENTO:
{context}

PREGUNTA:
{question}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente académico experto en análisis documental.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        answer = response.choices[0].message.content

        return {
            "answer": answer,
            "sources": [
                {
                    "page": 1,
                    "content": uploaded_pdf_text[:300],
                }
            ],
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/review-article")
async def review_article(
    review_type: str = Form(...),
    blind_review: bool = Form(...),
    article_id: int | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    global uploaded_pdf_text, uploaded_filename, last_article_review

    try:
        if not uploaded_pdf_text:
            raise HTTPException(
                status_code=400,
                detail="Primero debes subir un artículo PDF",
            )

        text = uploaded_pdf_text[:30000]

        if blind_review:
            text = blind_review_text(text)

        prompt = f"""
Eres un sistema multiagente de arbitraje académico especializado en evaluación científica.

Tipo de evaluación:
{review_type}

Revisión ciega:
{blind_review}

Actúa como:
1. Revisor metodológico
2. Revisor teórico
3. Revisor editorial
4. Revisor APA
5. Editor en jefe

ARTÍCULO:
{text}

Genera un dictamen PROFUNDO, CRÍTICO, CONSTRUCTIVO y ACADÉMICO.

Usa exactamente esta estructura:

# Dictamen académico multiagente

# Badge de dictamen editorial

Elige solo una opción:
- Aceptado sin cambios
- Aceptado con cambios menores
- Requiere cambios mayores
- Rechazado

# Score general del artículo

# Revisión metodológica

# Revisión teórica

# Revisión editorial y de redacción

# Revisión APA y formato

# Tabla sintética de observaciones

Usa tabla Markdown:
| Apartado | Problema | Recomendación | Prioridad |
|---|---|---|---|

# Fortalezas

# Debilidades

# Recomendaciones concretas

# Dictamen final del editor en jefe
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un árbitro científico riguroso, humano y constructivo.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        review_text = response.choices[0].message.content

        score = calculate_score(review_text)
        badge = detect_badge(review_text)
        ai_probability = detect_ai_probability(review_text)

        article = None

        if article_id:
            article = db.query(Article).filter(Article.id == article_id).first()

        if not article:
            article = Article(
                title=uploaded_filename or "Artículo sin título",
                filename=uploaded_filename or "uploaded_article.pdf",
                status="under_review",
            )
            db.add(article)
            db.commit()
            db.refresh(article)

        new_review = Review(
            article_id=article.id,
            reviewer_id=current_user.id,
            filename=uploaded_filename or "uploaded_article.pdf",
            review_type=review_type,
            review_content=review_text,
            score=int(score),
            ai_probability=ai_probability,
            badge=badge,
            created_at=datetime.utcnow(),
        )

        article.status = status_from_badge(badge)

        db.add(new_review)
        db.commit()
        db.refresh(new_review)

        last_article_review = review_text

        return {
            "review": review_text,
            "score": score,
            "badge": badge,
            "ai_probability": ai_probability,
            "review_id": new_review.id,
            "article_id": article.id,
            "article_status": article.status,
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/chat")
async def chat(chat: ChatRequest):
    user_message = chat.prompt or chat.message or ""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Eres un asistente académico claro y profesional.",
            },
            {"role": "user", "content": user_message},
        ],
    )

    return {"response": response.choices[0].message.content}


@app.post("/compare")
async def compare_versions_json(request: CompareRequest):
    return compare_logic(request.original_text, request.corrected_text)


@app.post("/compare-reviews")
async def compare_versions_form(
    original_text: str = Form(...),
    corrected_text: str = Form(...),
):
    return compare_logic(original_text, corrected_text)


def compare_logic(original_text: str, corrected_text: str):
    prompt = f"""
Compara ambas versiones de un artículo académico.

VERSIÓN ORIGINAL:
{original_text}

VERSIÓN CORREGIDA:
{corrected_text}

Evalúa:
1. Qué observaciones fueron atendidas.
2. Qué problemas persisten.
3. Qué mejoró.
4. Qué sigue faltando.
5. Nivel de mejora general.

Redacta en formato académico.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Eres un experto en evaluación académica y mejora de manuscritos.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    return {"comparison": response.choices[0].message.content}


@app.get("/reviews")
def get_reviews(db: Session = Depends(get_db)):
    reviews = db.query(Review).order_by(Review.created_at.desc()).all()

    return [
        {
            "id": review.id,
            "article_id": review.article_id,
            "reviewer_id": review.reviewer_id,
            "filename": review.filename,
            "review_type": review.review_type,
            "badge": review.badge,
            "score": str(review.score),
            "ai_probability": review.ai_probability,
            "created_at": review.created_at,
        }
        for review in reviews
    ]


@app.get("/review/{review_id}")
def get_review_alias(review_id: int, db: Session = Depends(get_db)):
    return get_review(review_id, db)


@app.get("/reviews/{review_id}")
def get_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Revisión no encontrada")

    return {
        "id": review.id,
        "article_id": review.article_id,
        "reviewer_id": review.reviewer_id,
        "filename": review.filename,
        "review_type": review.review_type,
        "badge": review.badge,
        "score": str(review.score),
        "review": review.review_content,
        "review_content": review.review_content,
        "ai_probability": review.ai_probability,
        "created_at": review.created_at,
    }


@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    reviews = db.query(Review).all()
    articles = db.query(Article).all()

    return {
        "total_reviews": len(reviews),
        "total_articles": len(articles),
        "accepted": len([r for r in reviews if r.badge == "Aceptado sin cambios"]),
        "minor_changes": len(
            [r for r in reviews if r.badge == "Aceptado con cambios menores"]
        ),
        "major_changes": len(
            [r for r in reviews if r.badge == "Requiere cambios mayores"]
        ),
        "rejected": len([r for r in reviews if r.badge == "Rechazado"]),
        "submitted_articles": len([a for a in articles if a.status == "submitted"]),
        "under_review_articles": len(
            [a for a in articles if a.status == "under_review"]
        ),
        "published_articles": len([a for a in articles if a.status == "published"]),
    }


@app.get("/users")
def get_users(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    users = db.query(User).all()

    return [
        {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        }
        for user in users
    ]


@app.post("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    role: str = Form(...),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    allowed_roles = ["admin", "editor", "reviewer", "author"]

    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Rol no válido")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.role = role
    db.commit()

    return {
        "message": "Rol actualizado",
        "username": user.username,
        "role": user.role,
    }


@app.post("/export-review")
def export_review():
    return export_review_word()


@app.post("/export-review-word")
def export_review_word():
    global last_article_review

    if not last_article_review:
        raise HTTPException(status_code=400, detail="Primero debes generar un dictamen")

    document = Document()
    document.add_heading("Dictamen académico", level=1)
    document.add_paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    for line in last_article_review.split("\n"):
        clean = line.strip()

        if not clean:
            continue

        if clean.startswith("# "):
            document.add_heading(clean.replace("# ", ""), level=1)
        elif clean.startswith("## "):
            document.add_heading(clean.replace("## ", ""), level=2)
        else:
            document.add_paragraph(clean)

    file_path = "dictamen_academico.docx"
    document.save(file_path)

    return FileResponse(
        path=file_path,
        filename="dictamen_academico.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.post("/export-review-pdf")
def export_review_pdf():
    global last_article_review

    if not last_article_review:
        raise HTTPException(status_code=400, detail="Primero debes generar un dictamen")

    file_path = "dictamen_academico.pdf"
    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Dictamen académico", styles["Heading1"]))
    elements.append(Spacer(1, 12))
    elements.append(
        Paragraph(
            f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles["BodyText"],
        )
    )
    elements.append(Spacer(1, 12))

    for line in last_article_review.split("\n"):
        clean = line.strip()

        if not clean:
            continue

        elements.append(Paragraph(clean, styles["BodyText"]))
        elements.append(Spacer(1, 8))

    doc.build(elements)

    return FileResponse(
        path=file_path,
        filename="dictamen_academico.pdf",
        media_type="application/pdf",
    )