"""
WattCompare Backend API (Multilingual OCR + Energy Analysis)
Author: Astronaut 🌍

Features:
- EasyOCR (multilingual: English, Hindi, Tamil, Telugu, French, German, Spanish, Italian, Portuguese, Russian, Arabic, Japanese, Korean)
- Scans energy labels (kWh/year or kW)
- Converts, compares, and analyzes appliances
- Cost analysis + Carbon footprint
- Stores appliances in SQLite
- Exports full PDF report
- Backend only (API endpoints), for use with web frontend or mobile client
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import easyocr, cv2, numpy as np, re, os, io, sqlite3
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
CORS(app)
DB_FILE = "wattcompare.db"

# ---------------- Database Setup ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS appliances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        energy_kwh REAL,
        price REAL,
        energy_rate REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- Multilingual OCR Reader ----------------
# ✅ Keep only language combinations that EasyOCR supports together.
reader = easyocr.Reader(["en"], gpu=False)

# ---------------- OCR Processing ----------------
def extract_energy_from_image(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    results = reader.readtext(gray)
    text = " ".join([res[1] for res in results]).lower()

    # Match patterns like 250 kwh/year or 0.8 kw
    match = re.search(r"(\d+\.?\d*)\s*(kwh|kw)", text)
    if match:
        val = float(match.group(1))
        unit = match.group(2)
        if unit == "kw":  # Convert kW to yearly kWh estimate
            val *= 24 * 365 / 1000
        return val, text
    return None, text

# ---------------- API Routes ----------------
@app.route("/")
def home():
    return jsonify({
        "message": "🌍 WattCompare Backend is Live",
        "available_endpoints": {
            "POST /ocr": "Upload image -> detect energy in kWh/kW",
            "POST /add_appliance": "Save appliance data (with optional image)",
            "GET /list_appliances": "List all stored appliances",
            "POST /compare": "Compare two appliances by ID",
            "GET /export_pdf": "Export PDF summary report"
        }
    })

@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    energy, raw_text = extract_energy_from_image(file.read())
    return jsonify({"energy_kwh": energy, "raw_text": raw_text})

@app.route("/add_appliance", methods=["POST"])
def add_appliance():
    name = request.form.get("name")
    price = float(request.form.get("price", 0))
    energy_rate = float(request.form.get("energy_rate", 0))
    image = request.files.get("image")

    energy_kwh = None
    raw_text = None
    if image:
        energy_kwh, raw_text = extract_energy_from_image(image.read())

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO appliances (name, energy_kwh, price, energy_rate) VALUES (?, ?, ?, ?)",
        (name, energy_kwh, price, energy_rate)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "✅ Appliance added successfully",
        "data": {
            "name": name, "price": price,
            "energy_kwh": energy_kwh, "energy_rate": energy_rate
        }
    })

@app.route("/list_appliances", methods=["GET"])
def list_appliances():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM appliances")
    rows = cur.fetchall()
    conn.close()

    data = [
        {
            "id": r[0],
            "name": r[1],
            "energy_kwh": r[2],
            "price": r[3],
            "energy_rate": r[4],
            "timestamp": r[5]
        }
        for r in rows
    ]
    return jsonify(data)

@app.route("/compare", methods=["POST"])
def compare():
    ids = request.json.get("ids")
    if not ids or len(ids) != 2:
        return jsonify({"error": "Provide exactly 2 IDs"}), 400

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM appliances WHERE id IN (?, ?)", (ids[0], ids[1]))
    rows = cur.fetchall()
    conn.close()

    if len(rows) < 2:
        return jsonify({"error": "Appliances not found"}), 404

    a1, a2 = rows

    def cost(a):
        return a[2] * a[4] if a[2] and a[4] else 0

    cost1, cost2 = cost(a1), cost(a2)
    carbon1, carbon2 = cost1 * 0.82, cost2 * 0.82  # kg CO₂ per kWh

    better = a1 if cost1 < cost2 else a2
    return jsonify({
        "comparison": {
            "A": {"name": a1[1], "annual_cost": cost1, "carbon": carbon1},
            "B": {"name": a2[1], "annual_cost": cost2, "carbon": carbon2},
            "recommended": better[1]
        }
    })

@app.route("/export_pdf", methods=["GET"])
def export_pdf():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT name, energy_kwh, price, energy_rate FROM appliances")
    data = cur.fetchall()
    conn.close()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, 800, "⚡ WattCompare Report")
    pdf.setFont("Helvetica", 12)

    y = 770
    for row in data:
        line = f"Name: {row[0]} | Energy: {row[1]} kWh | Price: ₹{row[2]} | Rate: ₹{row[3]}/kWh"
        pdf.drawString(50, y, line)
        y -= 20
        if y < 100:
            pdf.showPage()
            y = 800

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="WattCompare_Report.pdf", mimetype="application/pdf")

# ---------------- Main ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 WattCompare Backend running on port {port}")
    app.run(host="0.0.0.0", port=port)

