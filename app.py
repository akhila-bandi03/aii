
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_file, session, jsonify
)
from io import BytesIO

from database import init_db, get_db_connection
from gnani.stt import GnaniSTTClient
from gnani.tts import GnaniTTSClient

import os
import re
import json
import tempfile
import requests as http_requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dukaansaathi-persistent-auth-key-2026")

_db_initialized = False

@app.before_request
def ensure_db():
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
        except Exception as e:
            print("[WARN] DB init failed:", e)
        _db_initialized = True

    # Re-insert any user-added custom products from session into new container DB
    custom_products = session.get("custom_products", [])
    if custom_products:
        try:
            conn = get_db_connection()
            for cp in custom_products:
                exists = conn.execute("SELECT id FROM products WHERE name = ? AND price = ?", (cp["name"], cp["price"])).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO products (name, price, stock, unit, is_deleted) VALUES (?, ?, ?, ?, 0)",
                        (cp["name"], cp["price"], cp["stock"], cp["unit"])
                    )
            conn.commit()
            conn.close()
        except Exception as e:
            print("[SYNC CUSTOM PRODUCTS ERROR]", e)


def get_stt_client():
    key = os.getenv("GNANI_API_KEY") or session.get("gnani_api_key")
    if not key:
        return None
    try:
        return GnaniSTTClient(api_key=key)
    except Exception as e:
        print("[STT Init Error]", e)
        return None


def get_tts_client():
    key = os.getenv("GNANI_API_KEY") or session.get("gnani_api_key")
    if not key:
        return None
    try:
        return GnaniTTSClient(api_key=key)
    except Exception as e:
        print("[TTS Init Error]", e)
        return None


# ── Helper: Get product names from DB (for STT keywords) ──

def get_product_keywords():
    """Return all active product names from the database as a list."""
    deleted_ids = set(session.get("deleted_ids", []))
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT id, name FROM products WHERE is_deleted = 0").fetchall()
        return [row["name"] for row in rows if row["id"] not in deleted_ids]
    finally:
        conn.close()


# ── Helper: Use Evon LLM for smart parsing ──

def parse_with_evon(transcript, product_names):
    """
    Use Gnani Evon LLM via api.vachana.ai to intelligently extract
    sale details from a voice transcript.
    Falls back to rule-based parsing if Evon is unavailable.
    """
    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        return None

    product_list = ", ".join(product_names) if product_names else "none"

    prompt = f"""You are a smart assistant for a small Indian shop (kirana store).
Extract sale details from this voice command spoken by a shopkeeper.
The shopkeeper may speak in Telugu, Hindi, English, or a mix.

Available products in the shop: {product_list}

Voice command: "{transcript}"

Extract the following and return ONLY valid JSON (no explanation):
{{
  "customer_name": "customer name or null if not mentioned",
  "product_name": "matched product name from the available list or null",
  "quantity": number or null,
  "unit": "kg/g/litre/ml/piece/packet or null"
}}

Rules:
- Match the product name to the closest match from the available products list
- If the shopkeeper says a Telugu word for a product, map it to the English name in inventory
- Common Telugu: బియ్యం/రైస్=rice, పప్పు=pappu, షుగర్/పంచదార=sugar, రవ్వ=ravva, నూనె=oil
- Extract numbers even if spoken as words (రెండు=2, మూడు=3, etc.)
- Default unit is "kg" if not specified
- Return ONLY the JSON object, nothing else"""

    try:
        # Try Gnani's hosted Evon endpoint
        response = http_requests.post(
            "https://api.vachana.ai/v1/chat/completions",
            headers={
                "X-API-Key-ID": api_key,
                "Content-Type": "application/json"
            },
            json={
                "model": "evon-30b",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 200
            },
            timeout=3
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                print(f"[EVON LLM] Successfully parsed: {parsed}")
                return parsed

        print(f"[EVON LLM] API returned status {response.status_code}")

    except Exception as e:
        print(f"[EVON LLM] Not available ({type(e).__name__}: {e}), using rule-based parsing")

    return None


# ── Rule-based extraction (fallback if Evon unavailable) ──

def extract_sale_details(transcript):
    text = transcript.lower().strip()

    print(f"[DEBUG] Transcript for parsing: '{text}'")

    # Try Evon LLM first
    product_names = get_product_keywords()
    evon_result = parse_with_evon(transcript, product_names)

    if evon_result and evon_result.get("product_name") and evon_result.get("quantity"):
        # Evon successfully parsed — use its result
        if evon_result.get("unit") is None:
            evon_result["unit"] = "kg"
        print(f"[DEBUG] Using Evon LLM result: {evon_result}")
        return evon_result

    print("[DEBUG] Falling back to rule-based parsing")

    # Telugu and English number words
    number_words = {
        "ఒకటి": 1, "ఒక": 1, "వన్": 1, "one": 1,
        "రెండు": 2, "టూ": 2, "two": 2,
        "మూడు": 3, "త్రీ": 3, "three": 3,
        "నాలుగు": 4, "ఫోర్": 4, "four": 4,
        "ఐదు": 5, "ఫైవ్": 5, "five": 5,
        "ఆరు": 6, "సిక్స్": 6, "six": 6,
        "ఏడు": 7, "సెవెన్": 7, "seven": 7,
        "ఎనిమిది": 8, "ఎయిట్": 8, "eight": 8,
        "తొమ్మిది": 9, "నైన్": 9, "nine": 9,
        "పది": 10, "టెన్": 10, "ten": 10,
        "half": 0.5, "అర": 0.5, "అరా": 0.5,
        "quarter": 0.25, "పావు": 0.25,
        "twenty": 20, "ఇరవై": 20,
        "thirty": 30, "ముప్పై": 30,
        "forty": 40, "నలభై": 40,
        "fifty": 50, "యాభై": 50,
        "hundred": 100, "వంద": 100, "నూరు": 100
    }

    # Identify quantity
    quantity = None
    numeric_match = re.search(r'(\d+(?:\.\d+)?)', text)

    if numeric_match:
        quantity = float(numeric_match.group(1))
    else:
        for word, value in sorted(
            number_words.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if word in text:
                quantity = float(value)
                break

    # Identify unit
    unit = None
    unit_aliases = {
        "kg": ["kg", "కేజీ", "కిలో", "కిలోలు", "kilo", "kilos", "kilogram"],
        "g": ["grams", "gram", "గ్రాములు", "గ్రాము"],
        "litre": ["litres", "litre", "liter", "liters", "లీటర్లు", "లీటర్"],
        "ml": ["ml", "మిల్లీలీటర్లు", "మిల్లీ"],
        "piece": ["pieces", "piece", "పీసులు", "పీస్"],
        "packet": ["packets", "packet", "ప్యాకెట్లు", "ప్యాకెట్"]
    }

    for standard_unit, aliases in unit_aliases.items():
        if any(alias in text for alias in aliases):
            unit = standard_unit
            break

    # Identify product — dynamically match against ALL products in the database
    product_name = None

    # Telugu aliases for common products
    telugu_product_aliases = {
        "షుగర్": "sugar", "సుగర్": "sugar", "పంచదార": "sugar",
        "రైస్": "rice", "బియ్యం": "rice",
        "ఆయిల్": "oil", "నూనె": "oil",
        "పప్పు": "pappu", "కందిపప్పు": "pappu", "పెసరపప్పు": "pappu",
        "రవ్వ": "ravva", "రవ్వా": "ravva",
        "ఆటా": "atta", "గోధుమపిండి": "atta",
        "ఉప్పు": "salt", "సాల్ట్": "salt",
        "టీ": "tea", "చాయ్": "tea",
    }

    # First check Telugu aliases
    for telugu_word, english_name in telugu_product_aliases.items():
        if telugu_word in text:
            product_name = english_name
            break

    # If no Telugu match, try matching against database product names directly
    if not product_name:
        conn = get_db_connection()
        try:
            db_products = conn.execute("SELECT name FROM products").fetchall()
            for row in db_products:
                db_name = row["name"].lower().strip()
                if db_name in text:
                    product_name = row["name"]
                    break
        finally:
            conn.close()

    print(f"[DEBUG] Matched product: '{product_name}'")

    # Identify customer name
    customer_name = None
    customer_match = re.search(r'^(.+?)\s+కి', text)

    if customer_match:
        customer_name = customer_match.group(1).strip()

    result = {
        "customer_name": customer_name,
        "product_name": product_name,
        "quantity": quantity,
        "unit": unit
    }

    print(f"[DEBUG] Extracted details: {result}")
    return result


# ── Routes ──

@app.route("/debug-headers", methods=["GET", "POST"])
def debug_headers():
    """Temporary debug endpoint to see what headers Vercel sends."""
    env_data = {k: v for k, v in request.environ.items() if isinstance(v, str)}
    headers_data = dict(request.headers)
    return jsonify({
        "method": request.method,
        "path_info": request.environ.get("PATH_INFO"),
        "headers": headers_data,
        "environ_str_keys": env_data,
    })


@app.route("/", methods=["GET", "POST"])
@app.route("/api/index", methods=["GET", "POST"])
def dashboard():
    if request.method == "POST":
        if request.form.get("set_gnani_key"):
            key = request.form.get("set_gnani_key").strip()
            if key:
                session["gnani_api_key"] = key
                session.modified = True
                flash("Gnani API Key connected successfully!")
            return redirect(url_for("dashboard"))
        if "audio" in request.files:
            return transcribe_audio()
        if request.form.get("delete_product_id"):
            try:
                return delete_product(int(request.form.get("delete_product_id")))
            except Exception:
                pass
        if request.form.get("action") == "confirm_voice_sale":
            return confirm_voice_sale()
        if request.form.get("action") == "cancel_voice_sale":
            return cancel_voice_sale()
        if request.form.get("name") and request.form.get("price"):
            return add_product()
        if request.form.get("product_id") and request.form.get("quantity"):
            return sell_product()

    deleted_ids = set(session.get("deleted_ids", []))

    conn = get_db_connection()

    # Sync DB with session deleted_ids in case it's a new container
    if deleted_ids:
        try:
            placeholders = ",".join("?" for _ in deleted_ids)
            conn.execute(f"UPDATE products SET is_deleted = 1 WHERE id IN ({placeholders})", list(deleted_ids))
            conn.commit()
        except Exception as e:
            print("[SYNC ERROR]", e)

    all_products = conn.execute(
        "SELECT * FROM products WHERE is_deleted = 0 ORDER BY id DESC"
    ).fetchall()

    # Filter out any deleted IDs
    products = [p for p in all_products if p["id"] not in deleted_ids]
    total_products = len(products)

    total_sales = conn.execute(
        "SELECT COALESCE(SUM(total), 0) FROM sales"
    ).fetchone()[0]

    low_stock = sum(1 for p in products if p["stock"] <= 5)

    # Recent sales with product names
    recent_sales = conn.execute("""
        SELECT s.*, p.name as product_name
        FROM sales s
        LEFT JOIN products p ON s.product_id = p.id
        ORDER BY s.sale_date DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    has_api_key = bool(os.getenv("GNANI_API_KEY") or session.get("gnani_api_key"))

    return render_template(
        "index.html",
        products=products,
        total_products=total_products,
        total_sales=total_sales,
        low_stock=low_stock,
        recent_sales=recent_sales,
        pending_sale=session.get("pending_sale"),
        has_api_key=has_api_key
    )


@app.route("/add_product", methods=["GET", "POST"])
def add_product():
    if request.method == "GET":
        return redirect(url_for("dashboard"))
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "kg").strip()

    try:
        price = float(request.form.get("price", 0))
        stock = float(request.form.get("stock", 0))
    except (ValueError, TypeError):
        flash("Please enter valid price and stock.")
        return redirect(url_for("dashboard"))

    if not name or price <= 0 or stock < 0:
        flash("Please enter valid product details.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO products (name, price, stock, unit, is_deleted)
           VALUES (?, ?, ?, ?, 0)""",
        (name, price, stock, unit)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Save to session custom products so cold starts remember it
    custom_products = session.get("custom_products", [])
    custom_products.append({"name": name, "price": price, "stock": stock, "unit": unit})
    session["custom_products"] = custom_products
    session.modified = True

    flash("Product added successfully!")
    return redirect(url_for("dashboard"))


@app.route("/delete_product/<int:product_id>", methods=["GET", "POST"])
def delete_product(product_id):
    # Store in session list of deleted IDs
    deleted_ids = list(session.get("deleted_ids", []))
    if product_id not in deleted_ids:
        deleted_ids.append(product_id)
    session["deleted_ids"] = deleted_ids
    session.modified = True

    conn = get_db_connection()

    try:
        # 1. Unlink sales records from this product so foreign keys stay clean
        conn.execute("UPDATE sales SET product_id = NULL WHERE product_id = ?", (product_id,))
        # 2. Mark product as deleted (soft delete)
        conn.execute("UPDATE products SET is_deleted = 1 WHERE id = ?", (product_id,))
        # 3. Also physically delete from current db
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        flash("Product deleted successfully!")
    except Exception as e:
        conn.rollback()
        print("[DELETE ERROR]", repr(e))
        flash("Unable to delete product.")
    finally:
        conn.close()

    return redirect(url_for("dashboard"))


@app.route("/sell_product", methods=["GET", "POST"])
def sell_product():
    if request.method == "GET":
        return redirect(url_for("dashboard"))
    customer_name = request.form.get("customer_name", "").strip()

    try:
        product_id = int(request.form.get("product_id"))
        quantity = float(request.form.get("quantity"))
    except (ValueError, TypeError):
        flash("Please select a product and enter a valid quantity.")
        return redirect(url_for("dashboard"))

    if quantity <= 0:
        flash("Quantity must be greater than zero.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ? AND is_deleted = 0", (product_id,)
        ).fetchone()

        if product is None:
            flash("Product not found.")

        elif product["stock"] < quantity:
            flash("Not enough stock available.")

        else:
            unit_price = product["price"]
            unit = product["unit"]
            total = unit_price * quantity

            conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (quantity, product_id)
            )

            conn.execute(
                """INSERT INTO sales
                (product_id, customer_name, quantity, unit_price, total, unit)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (product_id, customer_name, quantity,
                 unit_price, total, unit)
            )

            conn.commit()
            flash(f"Sale recorded! Total: Rs. {total:.2f}")

    except Exception:
        conn.rollback()
        flash("Unable to record sale. Please try again.")
        raise

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


@app.route("/transcribe", methods=["GET", "POST"])
def transcribe_audio():
    if request.method == "GET":
        return redirect(url_for("dashboard"))

    if "audio" not in request.files:
        flash("Please record your voice first.")
        return redirect(url_for("dashboard"))

    audio = request.files["audio"]

    if audio.filename == "":
        flash("No audio selected.")
        return redirect(url_for("dashboard"))

    try:
        audio_bytes = audio.read()
        if not audio_bytes or len(audio_bytes) < 100:
            flash("Audio recording was empty or too short. Please speak clearly.")
            return redirect(url_for("dashboard"))

        # Get product names for STT keyword boosting
        product_keywords = get_product_keywords()

        client = get_stt_client()
        if not client:
            flash("Gnani API Key is missing or invalid. Please check settings.")
            return redirect(url_for("dashboard"))

        # Send audio bytes directly to Gnani STT (Prisma) with keyword boosting
        result = client.transcribe_bytes(
            audio_bytes,
            filename="recording.wav",
            language_code="te-IN",
            keywords=product_keywords if product_keywords else None,
            topic="kirana shop sales inventory"
        )

        transcript = result.get("transcript", "")

        if transcript:
            print("Recognized Voice:", transcript)

            details = extract_sale_details(transcript)
            print("Extracted Sale Details:", details)

            customer_name = details["customer_name"]
            product_name = details["product_name"]
            quantity = details["quantity"]

            if not product_name or quantity is None:
                flash(
                    f'Voice recognized: "{transcript}" — '
                    "but product or quantity was not identified. "
                    "Please try again clearly."
                )
                return redirect(url_for("dashboard"))

            if quantity <= 0:
                flash("Please speak a valid quantity.")
                return redirect(url_for("dashboard"))

            conn = get_db_connection()

            try:
                product = conn.execute(
                    "SELECT * FROM products WHERE LOWER(name) = LOWER(?) AND is_deleted = 0",
                    (product_name,)
                ).fetchone()

                if product is None:
                    flash(
                        f'"{product_name}" is not available in your inventory. '
                        "Please add the product first."
                    )
                    return redirect(url_for("dashboard"))

                if product["stock"] < quantity:
                    flash(
                        f"Not enough stock. Available stock: "
                        f"{product['stock']} {product['unit']}"
                    )
                    return redirect(url_for("dashboard"))

                unit_price = product["price"]
                unit = product["unit"]
                total = unit_price * quantity

                # Store pending sale in session.
                # Database will NOT be updated here.
                session["pending_sale"] = {
                    "transcript": transcript,
                    "customer_name": customer_name or "Not provided",
                    "product_name": product["name"],
                    "product_id": product["id"],
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "total": total
                }

                flash("Please review the voice sale and confirm it.")

            finally:
                conn.close()

        else:
            flash("No speech detected. Please try again.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print("STT Error:", repr(e))
        flash(f"Voice processing failed: {str(e)}")

    return redirect(url_for("dashboard"))


# Confirm Voice Sale
@app.route("/confirm_voice_sale", methods=["GET", "POST"])
def confirm_voice_sale():
    if request.method == "GET":
        return redirect(url_for("dashboard"))

    pending_sale = session.get("pending_sale")

    if not pending_sale:
        flash("No pending voice sale found.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?",
            (pending_sale["product_id"],)
        ).fetchone()

        if product is None:
            flash("Product no longer exists. Sale was not recorded.")
            session.pop("pending_sale", None)
            return redirect(url_for("dashboard"))

        quantity = float(pending_sale["quantity"])

        # Recheck stock before saving
        if product["stock"] < quantity:
            flash(
                f"Not enough stock available. Current stock: "
                f"{product['stock']} {product['unit']}. "
                "Sale was not recorded."
            )
            session.pop("pending_sale", None)
            return redirect(url_for("dashboard"))

        # Use current database price
        unit_price = product["price"]
        unit = product["unit"]
        total = unit_price * quantity

        # Reduce stock only after confirmation
        update_result = conn.execute(
            """UPDATE products
               SET stock = stock - ?
               WHERE id = ? AND stock >= ?""",
            (quantity, product["id"], quantity)
        )

        if update_result.rowcount != 1:
            conn.rollback()
            flash("Stock changed. Please try the sale again.")
            session.pop("pending_sale", None)
            return redirect(url_for("dashboard"))

        # Save confirmed sale
        conn.execute(
            """INSERT INTO sales
               (product_id, customer_name, quantity, unit_price, total, unit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                product["id"],
                pending_sale["customer_name"],
                quantity,
                unit_price,
                total,
                unit
            )
        )

        conn.commit()

        session.pop("pending_sale", None)

        # Generate TTS confirmation message
        confirm_msg = (
            f"{pending_sale['customer_name']} కి "
            f"{int(quantity) if quantity == int(quantity) else quantity} "
            f"{unit} {product['name']} అమ్మారు. "
            f"Total {int(total) if total == int(total) else total} రూపాయలు."
        )
        session["tts_confirm"] = confirm_msg

        flash(
            f"Voice sale confirmed successfully! "
            f"Total amount: Rs. {total:.2f}"
        )

    except Exception as e:
        conn.rollback()
        print("Voice Sale Confirmation Error:", repr(e))
        flash("Unable to confirm sale. Please try again.")

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


# Cancel Voice Sale
@app.route("/cancel_voice_sale", methods=["GET", "POST"])
def cancel_voice_sale():
    session.pop("pending_sale", None)
    flash("Voice sale cancelled. No changes were made to inventory.")
    return redirect(url_for("dashboard"))


# Text to Speech
@app.route("/speak", methods=["GET", "POST"])
def speak_text():
    if request.method == "GET":
        text = request.args.get("text", "").strip()
    else:
        text = request.form.get("text", "").strip()

    if not text:
        flash("Please enter text for voice response.")
        return redirect(url_for("dashboard"))

    try:
        client = get_tts_client()
        if not client:
            flash("Gnani API Key is missing.")
            return redirect(url_for("dashboard"))

        audio = client.synthesize(
            text,
            voice="Shivani",
            model="timbre-v3.0",
            language="te-IN"
        )

        return send_file(
            BytesIO(audio),
            mimetype="audio/wav",
            as_attachment=False,
            download_name="dukaansaathi_response.wav"
        )

    except Exception as e:
        print("TTS Error:", repr(e))
        flash("Voice generation failed. Please try again.")
        return redirect(url_for("dashboard"))


# TTS Confirmation endpoint (auto-speak after sale confirmation)
@app.route("/speak_confirm", methods=["GET", "POST"])
def speak_confirm():
    confirm_text = session.pop("tts_confirm", None)

    if not confirm_text:
        return jsonify({"status": "idle"}), 200

    try:
        client = get_tts_client()
        if not client:
            return jsonify({"error": "TTS client not configured"}), 500

        audio = client.synthesize(
            confirm_text,
            voice="Shivani",
            model="timbre-v3.0",
            language="te-IN"
        )

        return send_file(
            BytesIO(audio),
            mimetype="audio/wav",
            as_attachment=False,
            download_name="dukaansaathi_confirm.wav"
        )

    except Exception as e:
        print("TTS Confirm Error:", repr(e))
        return jsonify({"error": "TTS failed"}), 500


if __name__ == "__main__":
    app.run(debug=True)
