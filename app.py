import uvicorn
from fastapi import FastAPI, Form, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
import os, json
from starlette.middleware.sessions import SessionMiddleware

# =======================
# Database Configuration
# =======================
DATABASE_URL = "postgresql+psycopg2://postgres:root@localhost:5432/postgres"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# =======================
# Database Models
# =======================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone_number = Column(String(15))
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now())

    products = relationship("Product", back_populates="user", cascade="all, delete")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    unit_type = Column(String(50))
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="products")


# Create Tables (auto-run)
Base.metadata.create_all(bind=engine)

# =======================
# FastAPI App
# =======================
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey123")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
HISTORY_FILE = "quotation_history.json"

# Dependency for DB Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ========== HOME PAGE ==========
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
        # Check login status
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/products", response_class=HTMLResponse)
async def get_products(request: Request, db: Session = Depends(get_db)):
    # ✅ Ensure user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # ✅ Fetch only logged-in user's products
    products = db.query(Product).filter(Product.user_id == user_id).all()

    # ✅ Render the page
    return templates.TemplateResponse(
        "products.html",
        {"request": request, "products": products}
    )


@app.post("/add_product")
async def add_product(
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    unit_type: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    # ✅ Ensure user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # ✅ Create product linked to logged-in user
    new_product = Product(
        name=name,
        price=price,
        unit_type=unit_type,
        description=description,
        user_id=user_id
    )

    db.add(new_product)
    db.commit()

    return RedirectResponse(url="/products", status_code=303)


@app.post("/update_product")
async def update_product(
    request: Request,
    old_name: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    unit_type: str = Form(...),
    db: Session = Depends(get_db)
):
    # ✅ Ensure user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # ✅ Update only this user's product
    product = db.query(Product).filter(Product.name == old_name, Product.user_id == user_id).first()
    if product:
        product.name = name
        product.description = description
        product.price = price
        product.unit_type = unit_type
        db.commit()

    return RedirectResponse(url="/products", status_code=303)


@app.post("/delete_product")
async def delete_product(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    # ✅ Ensure user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # ✅ Delete only this user's product
    product = db.query(Product).filter(Product.name == name, Product.user_id == user_id).first()
    if product:
        db.delete(product)
        db.commit()

    return RedirectResponse(url="/products", status_code=303)

@app.get("/quotation", response_class=HTMLResponse)
async def get_form(request: Request, db: Session = Depends(get_db)):
    # ✅ Check if user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # ✅ Load only this user's products
    products = db.query(Product).filter(Product.user_id == user_id).all()

    return templates.TemplateResponse(
        "quotation_form.html",
        {"request": request, "products": products}
    )

# ========== LOGIN / USER CREATION ==========
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_user(
    username: str = Form(...),
    email: str = Form(...),
    phone_number: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {"request": {}, "error": "Email already registered!"})
    new_user = User(username=username, email=email, phone_number=phone_number, password_hash=password)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Authenticate user and start a session"""
    user = db.query(User).filter(User.email == email, User.password_hash == password).first()

    if not user:
        # Invalid credentials → show error message
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid email or password!"}
        )

    # ✅ Store login session
    request.session["logged_in"] = True
    request.session["user_id"] = user.id
    request.session["username"] = user.username

    # ✅ Redirect to home after login
    response = RedirectResponse(url="/", status_code=303)
    return response

@app.get("/logout")
async def logout(request: Request):
    """Log the user out and redirect to login page"""
    request.session.clear()
    response = RedirectResponse(url="/login", status_code=303)
    # If you add session cookies later, you can clear them here:
    # response.delete_cookie("session")
    return response


# ###################################### ********************************************************************#########################
@app.get("/edit_quotation/{index}", response_class=HTMLResponse)
async def edit_quotation(request: Request, index: int, db: Session = Depends(get_db)):
    """Load historical quotation data into editable form (robust + DB-backed catalog)."""

    # --- load history safely ---
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    # protect against corrupted file that contains a dict etc.
                    history = []
        except Exception:
            history = []

    # protect against negative indexes and out-of-range
    try:
        idx = int(index)
    except Exception:
        return RedirectResponse(url="/history", status_code=303)

    if idx < 0 or idx >= len(history):
        return RedirectResponse(url="/history", status_code=303)

    entry = history[idx]
    quotation_data = entry.get("data", {}) if isinstance(entry, dict) else {}

    # --- Load product catalog: prefer DB for the logged-in user, fallback to products.json ---
    products = []
    user_id = request.session.get("user_id")
    if user_id:
        try:
            products_db = db.query(Product).filter(Product.user_id == user_id).all()
            products = [
                {
                    "name": p.name,
                    "unit_type": (p.unit_type or "").strip().upper(),
                    "description": p.description or "",
                    "price": p.price
                }
                for p in products_db
            ]
        except Exception:
            products = []

    # fallback: try products.json if DB returned no items
    if not products and os.path.exists("products.json"):
        try:
            with open("products.json", "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    products = loaded
        except Exception:
            products = []

    # Render template with prefill data
    return templates.TemplateResponse(
        "quotation_form.html",
        {"request": request, "products": products, "prefill": quotation_data}
    )

@app.get("/edit_pdf/{index}", response_class=HTMLResponse)
async def edit_pdf(request: Request, index: int):
    """View existing quotation and open editable form"""
    if not os.path.exists(HISTORY_FILE):
        return RedirectResponse(url="/history", status_code=303)

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try:
            history = json.load(f)
        except Exception:
            history = []

    if index >= len(history):
        return RedirectResponse(url="/history", status_code=303)

    entry = history[index]
    pdf_name = entry.get("file")
    pdf_path = os.path.join("static", pdf_name)

    if not os.path.exists(pdf_path):
        return HTMLResponse(f"<h3 style='color:red;text-align:center;'>❌ PDF not found: {pdf_name}</h3>")

    # Show preview + re-edit option
    html_content = f"""
    <html>
    <head>
    <title>Edit Quotation | {entry.get('customer_name')}</title>
    <style>
      body {{ font-family: 'Segoe UI'; background:#f4f7fb; text-align:center; padding:40px; }}
      .btn {{
        background:#0b5394; color:white; border:none; padding:12px 24px; 
        border-radius:8px; margin:10px; cursor:pointer; font-weight:bold; text-decoration:none;
      }}
      .btn:hover {{ background:#073763; }}
      iframe {{ width:80%; height:600px; border:2px solid #ccc; border-radius:8px; margin-bottom:20px; }}
    </style>
    </head>
    <body>
      <h2 style='color:#0b5394;'>Edit Quotation - {entry.get('customer_name')}</h2>
      <iframe src="/static/{pdf_name}"></iframe><br>
      <a href="/edit_quotation/{index}" class="btn">✏ Open in Form (Edit)</a>
      <a href="/history" class="btn">⬅ Back to History</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/generate_pdf", response_class=HTMLResponse)
async def generate_pdf(
    request: Request,
    customer_name: str = Form(...),
    customer_address: str = Form(...),
    customer_city: str = Form(...),
    shipping_name: str = Form(...),
    shipping_address: str = Form(...),
    shipping_city: str = Form(...),
    company_name: str = Form(...),
    company_address: str = Form(...),
    company_email: str = Form(...),
    company_phone: str = Form(...),
    company_gst: str = Form(...),
    bank_name: str = Form(...),
    account_name: str = Form(...),
    account_number: str = Form(...),
    ifsc_code: str = Form(...),
    valid_till: str = Form(...),
    product_name: List[str] = Form(...),
    description: Optional[List[str]] = Form(None),
    quantity: List[float] = Form(...),
    unit_price: List[float] = Form(...),
    loading_charge: Optional[float] = Form(0.0),
    transportation_charge: Optional[float] = Form(0.0),   # <<< new input
    note: Optional[str] = Form(""),  # ✅ new manual note field
    quotation_number: str = Form(...),  # <<< new required input
    db: Session = Depends(get_db),
):
    """Generate quotation PDF and preview"""
    if description is None:
        description = ["" for _ in product_name]

    # ===== Calculations =====
    total_amount = sum(q * p for q, p in zip(quantity, unit_price))
    loading_charge = float(loading_charge or 0.0)
    transportation_charge = float(transportation_charge or 0.0)
    sub_total = total_amount + loading_charge + transportation_charge
    gst_amount = sub_total * 0.18
    grand_total = sub_total + gst_amount
    round_off = round(grand_total) - grand_total
    final_total = round(grand_total)

    # quotation_no = f"LSY/{datetime.now().strftime('%m-%d-%y')}/001"
    # quotation_date = datetime.now().strftime("%d-%m-%Y")
    # Format as DD-MM-YYYY everywhere
    qn = (str(quotation_number or "").strip())
    if not qn:
        # fallback format: LSY/DD-MM-YYYY/001
        qn = f"LSY/001"
    quotation_no = qn
    quotation_date = datetime.now().strftime("%d-%m-%Y")

    # ===== PDF Path =====
    safe_name = customer_name.replace(" ", "_")
    #pdf_file = f"static/quotation_{safe_name}_{datetime.now().strftime('%H%M%S')}.pdf"
    pdf_file = f"static/quotation_{safe_name}_{datetime.now().strftime('%d-%m-%Y_%H%M%S')}.pdf"

    c = canvas.Canvas(pdf_file, pagesize=A4)
    width, height = A4

    # ===== HEADER =====
    c.setFillColor(colors.HexColor("#0b5394"))
    c.rect(0, height - 80, width, 70, fill=True, stroke=False)
    if os.path.exists("static/logo.png"):
        c.drawImage("static/logo.png", 56, height - 76, width=45, height=50, mask='auto')

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(110, height - 40, company_name)
    c.setFont("Helvetica", 9)
    c.drawString(110, height - 52, company_address)
    c.drawString(110, height - 64, f"Email: {company_email} | Ph: {company_phone}")
    c.drawString(110, height - 76, f"GSTIN: {company_gst}")

    # ===== TITLE =====
    c.setFillColor(colors.HexColor("#d11a2a"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 95, "QUOTATION")

    # ===== BILL TO / SHIP TO =====
    c.setFillColor(colors.HexColor("#f4f4f4"))
    c.roundRect(30, height - 220, 250, 90, 6, fill=True, stroke=False)
    c.roundRect(290, height - 220, 250, 90, 6, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    c.drawString(40, height - 140, "Bill To:")
    c.drawString(300, height - 140, "Ship To:")

    c.setFont("Helvetica", 9)
    c.drawString(40, height - 155, customer_name)
    c.drawString(40, height - 167, customer_address)
    c.drawString(40, height - 179, customer_city)
    c.drawString(300, height - 155, shipping_name)
    c.drawString(300, height - 167, shipping_address)
    c.drawString(300, height - 179, shipping_city)

    # ===== DETAILS =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, height - 200, "Quotation Details:")
    c.setFont("Helvetica", 9)
    c.drawString(40, height - 212, f"Quotation No: {quotation_no}")
    c.drawString(200, height - 212, f"Date: {quotation_date}")
    # c.drawString(380, height - 212, f"Valid Till: {valid_till}")
    # Reformat valid_till safely (if user input is YYYY-MM-DD)
    try:
        valid_till_fmt = datetime.strptime(valid_till, "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        valid_till_fmt = valid_till  # fallback if already formatted
    c.drawString(380, height - 212, f"Valid Till: {valid_till_fmt}")
    # ===== PRODUCT TABLE =====
    y = height - 250
    c.setFillColor(colors.HexColor("#0b5394"))
    c.rect(30, y, width - 60, 18, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y + 4, "No")
    c.drawString(70, y + 4, "Product")
    c.drawString(130, y + 4, "Description")
    c.drawString(370, y + 4, "Qty")
    c.drawString(420, y + 4, "Rate (₹)")
    c.drawString(500, y + 4, "Amount (₹)")

    y -= 18
    c.setFont("Helvetica", 9)

    # Load product catalog from DB for the logged-in user (same dict shape as products.json)
    catalog = []
    user_id = request.session.get("user_id")
    if user_id:
        products_db = db.query(Product).filter(Product.user_id == user_id).all()
        catalog = [
            {
                "name": p.name,
                "unit_type": (p.unit_type or "").strip().upper(),
                "description": p.description or ""
            }
            for p in products_db
        ]
       
    # ✅ Initialize totals
    # ✅ Calculate totals
    total_weight = 0.0
    total_nos = 0.0
    total_pieces = 0.0

    for i, (p, d, q, u) in enumerate(zip(product_name, description, quantity, unit_price), start=1):
        unit = ""
        for prod in catalog:
            if prod["name"].lower() == p.lower():
                unit = prod.get("unit_type", "").upper()
                break

        # ✅ Categorize quantities
        if unit == "KG":
            total_weight += q
        elif unit in ["NOS", "NO", "NOS."]:
            total_nos += q
        elif unit in ["PCS", "PIECE", "PIECES"]:
            total_pieces += q
        # Draw product rows (your working logic)
        c.setFillColor(colors.whitesmoke if i % 2 == 0 else colors.lightgrey)
        c.rect(30, y - 20, width - 60, 20, fill=True, stroke=False)
        c.setFillColor(colors.black)
        c.drawString(40, y - 11, str(i))
        c.drawString(70, y - 11, p[:18])
        c.drawString(130, y - 11, d[:30])
        qty_display = f"{q:,.3f} {unit}" if unit else f"{q:,.3f}"
        c.drawRightString(400, y - 11, qty_display)
        c.drawRightString(460, y - 11, f"{u:,.2f}")
        c.drawRightString(540, y - 11, f"{q * u:,.2f}")
        y -= 20

    #✅ After product loop ends
    summary_parts = []
    if total_weight > 0:
        summary_parts.append(f"Total Weight: {total_weight:,.3f} KG")
    if total_nos > 0:
        summary_parts.append(f"Total Nos: {total_nos:,.0f}")
    if total_pieces > 0:
        summary_parts.append(f"Total Pieces: {total_pieces:,.0f}")

    if summary_parts:
        summary_text = " | ".join(summary_parts)
        print(summary_text)

        box_y = y - 8
        c.setFillColor(colors.HexColor("#0b5394"))
        c.roundRect(30, box_y - 8, width - 60, 20, 5, fill=True, stroke=False)

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.black)
        #c.drawString(40, box_y, summary_text)
        c.drawRightString(width - 40, box_y, summary_text)
        y -= 25

    # ===== TOTALS =====
    y -= 25
    c.setFillColor(colors.HexColor("#f4f4f4"))
    c.roundRect(280, y - 85, 260, 85, 8, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.black)
    c.drawRightString(420, y - 10, "Sub Total:")
    c.drawRightString(520, y - 10, f"{total_amount:,.2f}")
    c.drawRightString(420, y - 25, "Loading Charges:")
    c.drawRightString(520, y - 25, f"{loading_charge:,.2f}")
    c.drawRightString(420, y - 40, "Transportation Charges:")
    c.drawRightString(520, y - 40, f"{transportation_charge:,.2f}")
    c.drawRightString(420, y - 55, "GST (18%):")
    c.drawRightString(520, y - 55, f"{gst_amount:,.2f}")
    c.drawRightString(420, y - 70, "Round Off:")
    c.drawRightString(520, y - 70, f"{round_off:+.2f}")
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(420, y - 85, "Grand Total:")
    c.drawRightString(520, y - 85, f"{final_total:,.2f} ₹")

    # ===== BANK INFO =====
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y - 100, f"Account Name : {account_name}")
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 113, f"Account No : {account_number}")
    c.drawString(40, y - 126, f"IFSC : {ifsc_code}")
    c.drawString(40, y - 139, f"Bank : {bank_name}")
        # ===== MANUAL NOTE BELOW BANK INFO =====
    # ===== OPTIONAL NOTE SECTION =====
    if note and note.strip():
        note_y = y - 160
        c.setFont("Helvetica-Oblique", 9)
        c.setFillColor(colors.HexColor("#0b5394"))  # subtle blue color
        c.drawString(40, note_y, f"Note: {note.strip()}")
        y = note_y - 15  # move Y down for spacing below note

    # ===== FOOTER =====
    c.setFillColor(colors.HexColor("#0b5394"))
    c.rect(0, 0, width, 60, fill=True, stroke=False)
    logos = ["tata.png", "tata_pipes.png", "amns.png", "jindal.png", "vizag.png", "jsw.png"]
    logo_y = 12
    logo_w = 40
    logo_h = 25
    gap = 10
    total_w = len(logos) * (logo_w + gap)
    start_x = (width - total_w) / 2
    for logo in logos:
        path = os.path.join("static", logo)
        if os.path.exists(path):
            c.drawImage(path, start_x, logo_y, width=logo_w, height=logo_h, preserveAspectRatio=True)
        start_x += logo_w + gap

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(width / 2, 5, "One Stop Solution for Variety of Branded Steel")

    c.save()

    # ===== Save to History =====
    # quotation_no = f"LSY/{datetime.now().strftime('%m-%d-%y')}/001"
    user_id = request.session.get("user_id")
    history_entry = {
        "quotation_no": quotation_no,
        "customer_name": customer_name,
        "date": quotation_date,
        "file": os.path.basename(pdf_file),
        "total": final_total,
        "user_id": user_id, 
        "data": {
            "company_name": company_name,
            "company_address": company_address,
            "company_email": company_email,
            "company_phone": company_phone,
            "company_gst": company_gst,
            "customer_name": customer_name,
            "customer_address": customer_address,
            "customer_city": customer_city,
            "shipping_name": shipping_name,
            "shipping_address": shipping_address,
            "shipping_city": shipping_city,
            "account_name": account_name,
            "account_number": account_number,
            "ifsc_code": ifsc_code,
            "bank_name": bank_name,
            "valid_till": valid_till,
            "note": note,  # ✅ store it
            "loading_charge": loading_charge,
            "transportation_charge": transportation_charge,
            "product_name": product_name,
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price
        }
}
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            try:
                history = json.load(f)
            except Exception:
                history = []
    history.insert(0, history_entry)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    # ===== Show Preview Page =====
    pdf_name = os.path.basename(pdf_file)
    return templates.TemplateResponse("pdf_preview.html", {"request": request, "pdf_name": pdf_name})

@app.get("/history", response_class=HTMLResponse)
async def view_history(request: Request):
    # ✅ Ensure user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                all_history = json.load(f)
            except Exception:
                all_history = []

        # ✅ Filter quotations that belong to the logged-in user
        history = [h for h in all_history if h.get("user_id") == user_id]

    return templates.TemplateResponse(
        "quotation_history.html",
        {"request": request, "history": history}
    )

@app.post("/delete_history/{index}")
async def delete_history(index: int):
    """Delete a quotation PDF and its record"""
    if not os.path.exists(HISTORY_FILE):
        return RedirectResponse(url="/history", status_code=303)

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try:
            history = json.load(f)
        except Exception:
            history = []

    if index >= len(history):
        return RedirectResponse(url="/history", status_code=303)

    entry = history[index]
    pdf_path = os.path.join("static", entry.get("file", ""))

    if os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
        except Exception:
            pass

    del history[index]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    return RedirectResponse(url="/history", status_code=303)
# ========== DOWNLOAD ==========
@app.get("/download/{pdf_name}")
async def download_pdf(pdf_name: str):
    pdf_path = os.path.join("static", pdf_name)
    if not os.path.exists(pdf_path):
        return {"error": "File not found"}

    # update last_downloaded
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except Exception:
                history = []

        updated = False
        for h in history:
            if h.get("file") == pdf_name:
                h["last_downloaded"] = datetime.now().strftime("%d-%m-%Y %H:%M")
                updated = True
                break
        if updated:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_name)


# ========== RUN ==========
if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8002, reload=True)
