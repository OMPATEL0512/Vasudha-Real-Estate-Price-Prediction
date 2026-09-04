"""
Vasudha Real Estate — Flask Web Application & REST API
Ahmedabad Property Valuation Platform (Ultra-Luxury Architecture)
"""

import os
import json
import secrets
from flask import Flask, request, jsonify, session, render_template_string, redirect, url_for, send_file
from datetime import timedelta

import database
import backend
from ml_model import ml_model

app = Flask(__name__)
# Cryptographically secure dynamic secret key fallback
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

# Session cookie security hardening
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7)
)

# Ensure database is initialized
database.init_db()


# ---------------------------------------------------------------------------
# HTTP Security Headers (OWASP Hardening)
# ---------------------------------------------------------------------------

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ---------------------------------------------------------------------------
# API Routes: Authentication
# ---------------------------------------------------------------------------

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    first_name = data.get("first_name", "")
    surname = data.get("surname", "")
    age = data.get("age", "")
    phone = data.get("phone", "")
    email = data.get("email", "")
    username = data.get("username", "")
    password = data.get("password", "")

    res = backend.start_registration(first_name, surname, age, phone, email, username, password)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/auth/verify-otp", methods=["POST"])
def api_verify_otp():
    data = request.get_json() or {}
    email = data.get("email", "")
    otp = data.get("otp", "")

    res = backend.verify_registration_otp(email, otp)
    if not res["success"]:
        return jsonify(res), 400

    # Log user in
    user = res["user"]
    session.permanent = True
    session["user_id"] = user["id"]
    session["user_name"] = f"{user['first_name']} {user['surname']}"
    session["email"] = user["email"]
    session["username"] = user["username"]

    return jsonify(res), 200


@app.route("/api/auth/resend-otp", methods=["POST"])
def api_resend_otp():
    data = request.get_json() or {}
    email = data.get("email", "")
    res = backend.resend_registration_otp(email)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    identifier = data.get("identifier", "")
    password = data.get("password", "")

    res = backend.authenticate_user(identifier, password)
    if not res["success"]:
        return jsonify(res), 401

    user = res["user"]
    session.permanent = True
    session["user_id"] = user["id"]
    session["user_name"] = f"{user['first_name']} {user['surname']}"
    session["email"] = user["email"]
    session["username"] = user["username"]

    return jsonify(res), 200


@app.route("/api/auth/logout", methods=["POST", "GET"])
def api_logout():
    session.clear()
    if request.headers.get("Accept") == "application/json" or request.is_json or request.method == "POST":
        return jsonify({"success": True, "message": "Logged out successfully."})
    return redirect("/")


@app.route("/logout", methods=["GET", "POST"])
def user_logout():
    session.clear()
    return redirect("/")


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    if "user_id" in session:
        return jsonify({
            "authenticated": True,
            "user": {
                "id": session.get("user_id"),
                "name": session.get("user_name"),
                "email": session.get("email"),
                "username": session.get("username")
            }
        })
    return jsonify({"authenticated": False, "user": None})


@app.route("/api/auth/forgot-password", methods=["POST"])
def api_forgot_password():
    data = request.get_json() or {}
    email = data.get("email", "")
    res = backend.start_password_reset(email)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/auth/reset-password", methods=["POST"])
def api_reset_password():
    data = request.get_json() or {}
    email = data.get("email", "")
    otp = data.get("otp", "")
    new_password = data.get("new_password", "")

    res = backend.verify_password_reset(email, otp, new_password)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


# ---------------------------------------------------------------------------
# API Routes: Admin Management Portal (Users & Price Editor)
# ---------------------------------------------------------------------------

@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json() or {}
    passcode = data.get("passcode", "")
    if backend.check_admin_passcode(passcode):
        session["is_admin"] = True
        session.permanent = True
        return jsonify({"success": True, "message": "Admin authorization granted."}), 200
    return jsonify({"success": False, "error": "Invalid Master Admin Passcode. Please try again."}), 401


@app.route("/api/admin/forgot-passcode", methods=["POST"])
def api_admin_forgot_passcode():
    res = backend.start_admin_password_reset()
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/admin/reset-passcode", methods=["POST"])
def api_admin_reset_passcode():
    data = request.get_json() or {}
    otp = data.get("otp", "")
    new_passcode = data.get("new_passcode", "")
    res = backend.verify_admin_password_reset(otp, new_passcode)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/admin/me", methods=["GET"])
def api_admin_me():
    return jsonify({"is_admin": bool(session.get("is_admin", False))})


@app.route("/api/admin/logout", methods=["POST", "GET"])
def api_admin_logout():
    session.pop("is_admin", None)
    return jsonify({"success": True, "message": "Admin session terminated."})


@app.route("/api/admin/users", methods=["GET"])
def api_admin_users():
    if not session.get("is_admin"):
        return jsonify({"success": False, "error": "Admin access required. Please authenticate."}), 403
    res = backend.admin_get_all_users()
    return jsonify(res), 200


@app.route("/api/admin/users/delete", methods=["POST"])
def api_admin_delete_user():
    if not session.get("is_admin"):
        return jsonify({"success": False, "error": "Admin access required. Please authenticate."}), 403
    data = request.get_json() or {}
    user_id = data.get("user_id")
    res = backend.admin_delete_user(user_id)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/admin/locality/update-price", methods=["POST"])
def api_admin_update_locality_price():
    if not session.get("is_admin"):
        return jsonify({"success": False, "error": "Admin access required. Please authenticate."}), 403
    data = request.get_json() or {}
    loc_name = data.get("name", "")
    rate_sqft = data.get("rate_per_sqft")
    yoy = data.get("yoy_percent")
    liv = data.get("livability_score")
    res = backend.admin_update_locality_price(loc_name, rate_sqft, yoy, liv)
    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


# ---------------------------------------------------------------------------
# API Routes: Localities & Valuation (Auth Gated)
# ---------------------------------------------------------------------------

@app.route("/api/localities", methods=["GET"])
def api_localities():
    zone = request.args.get("zone")
    locs = database.get_all_localities(zone)
    return jsonify({"success": True, "count": len(locs), "localities": locs})


@app.route("/api/locality/<name>", methods=["GET"])
def api_locality_detail(name):
    loc = database.get_locality_by_name(name)
    if not loc:
        return jsonify({"success": False, "error": "Locality not found"}), 404
    
    trends = database.get_historical_trends(name)
    loc_dict = dict(loc)
    loc_dict["historical_trends"] = trends
    return jsonify({"success": True, "locality": loc_dict})


@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    # Enforce login requirement for valuation calculations
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "requires_auth": True,
            "error": "Member verification required. Please sign in or create an account to view property valuations and 5-year projections."
        }), 401

    data = request.get_json() or {}
    locality = data.get("locality", "")
    area = data.get("area", 0)
    property_type = data.get("property_type", "Apartment / Flat")
    year = int(data.get("year", 2026))

    res = backend.calculate_property_valuation(
        locality_name=locality,
        area_value=area,
        unit="sqyd",  # Standardized to Sq. Yards (Gaj)
        property_type=property_type,
        year=year
    )

    if not res["success"]:
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/api/share-calculation", methods=["POST"])
def api_share_calculation():
    """
    Share valuation calculation directly to user-provided email address.
    Includes approximate price disclaimer, locality, size in sq. yards, price, and timestamp.
    """
    data = request.get_json() or {}
    recipient_email = data.get("email", "").strip()
    if not recipient_email:
        return jsonify({"success": False, "error": "Recipient email address is required."}), 400

    locality = data.get("locality", "").strip()
    area_sqyd = data.get("area_sqyd") or data.get("area", 0)

    # If full valuation attributes were not passed by client, compute them
    if not data.get("total_price") and locality and area_sqyd:
        calc_res = backend.calculate_property_valuation(
            locality_name=locality,
            area_value=area_sqyd,
            unit="sqyd",
            property_type=data.get("property_type", "Apartment / Flat")
        )
        if calc_res.get("success"):
            data.update(calc_res)

    res = backend.send_valuation_email(recipient_email=recipient_email, details=data)
    if not res.get("success"):
        return jsonify(res), 400
    return jsonify(res), 200


@app.route("/splash_skyline.jpg")
def serve_splash_skyline():
    img_path = os.path.join(os.path.dirname(__file__), "splash_skyline.jpg")
    if os.path.exists(img_path):
        return send_file(img_path, mimetype="image/jpeg")
    return "", 404


# ---------------------------------------------------------------------------
# Ultra-Luxury Frontend Web Interface
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vasudha Real Estate | Ahmedabad Property Valuation & Intelligence Platform</title>
  <meta name="description" content="AI & Machine Learning-driven property valuation, 5-year appreciation projections, and real historical price trends across 25+ Ahmedabad localities.">
  
  <!-- Premium Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800;900&family=Fraunces:ital,opsz,wght@0,9..144,300..900;1,9..144,300..900&family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">

  <style>
    :root {
      --bg-void: #03060C;
      --bg-deep: #060B14;
      --bg-surface: #0B1220;
      --bg-card: #0F182A;
      --bg-card-hover: #15223A;
      --border: #18263F;
      --border-focus: #C9922E;
      --gold: #C9922E;
      --gold-bright: #F5D77F;
      --gold-dark: #8F6010;
      --gold-gradient: linear-gradient(135deg, #FBF0B9 0%, #D4AF37 40%, #AA7C11 80%, #E5C158 100%);
      --gold-glow: 0 0 25px rgba(212, 175, 55, 0.4), 0 0 60px rgba(201, 146, 46, 0.15);
      --text-main: #F8FAFC;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
      --accent-cyan: #38BDF8;
      --accent-green: #10B981;
      --radius: 12px;
      --radius-lg: 20px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }

    body {
      background-color: var(--bg-void);
      color: var(--text-main);
      font-family: 'Outfit', -apple-system, sans-serif;
      line-height: 1.6;
      overflow-x: hidden;
      selection-background-color: var(--gold);
    }

    .cinzel { font-family: 'Cinzel', serif; letter-spacing: 0.05em; }
    .serif-display { font-family: 'Fraunces', serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .container { max-width: 1240px; margin: 0 auto; padding: 0 24px; }

    /* Custom Cursor & Ambient Glow */
    .glow-blob {
      position: fixed;
      width: 500px;
      height: 500px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(201, 146, 46, 0.08) 0%, transparent 70%);
      pointer-events: none;
      transform: translate(-50%, -50%);
      z-index: 1;
      transition: width 0.3s, height 0.3s;
    }

    /* Navigation Bar */
    .navbar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(3, 6, 12, 0.85);
      backdrop-filter: blur(20px);
      border-bottom: 1px solid var(--border);
      padding: 16px 0;
      transition: all 0.3s ease;
    }

    .nav-inner {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      text-decoration: none;
      color: var(--text-main);
    }

    .brand-vr-icon {
      width: 44px;
      height: 44px;
      background: linear-gradient(145deg, #131E33 0%, #080D18 100%);
      border: 1.5px solid var(--gold);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: var(--gold-glow);
    }

    .brand-title {
      font-size: 20px;
      font-weight: 800;
      letter-spacing: 2.5px;
      color: var(--text-main);
    }

    .brand-subtitle {
      font-size: 10px;
      color: var(--gold-bright);
      letter-spacing: 3px;
      text-transform: uppercase;
      font-weight: 700;
    }

    .nav-links { display: flex; align-items: center; gap: 32px; }
    .nav-link {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 14px;
      font-weight: 500;
      transition: color 0.2s;
    }
    .nav-link:hover { color: var(--gold-bright); }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 11px 24px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.25s ease;
      text-decoration: none;
      border: none;
    }

    .btn-gold {
      background: var(--gold-gradient);
      color: #04070D;
      box-shadow: 0 4px 20px rgba(201, 146, 46, 0.35);
      font-weight: 700;
    }
    .btn-gold:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 30px rgba(212, 175, 55, 0.55);
    }

    .btn-outline {
      background: rgba(201, 146, 46, 0.05);
      color: var(--gold-bright);
      border: 1px solid rgba(201, 146, 46, 0.4);
    }
    .btn-outline:hover {
      background: rgba(201, 146, 46, 0.15);
      border-color: var(--gold);
    }

    .btn-ghost { background: transparent; color: var(--text-muted); }
    .btn-ghost:hover { color: var(--text-main); background: rgba(255, 255, 255, 0.05); }

    /* ==========================================================================
       CINEMATIC 3D BREAK-OUT VAULT HERO (NEXT LEVEL)
       ========================================================================== */
    .vault-hero-section {
      position: relative;
      min-height: 94vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: radial-gradient(circle at 50% 30%, rgba(201, 146, 46, 0.14) 0%, rgba(6, 11, 20, 0.8) 60%, var(--bg-void) 100%);
      border-bottom: 1px solid var(--border);
      padding: 60px 24px;
      overflow: hidden;
      perspective: 1600px;
    }

    /* Ambient Gold Laser Grid */
    .ambient-grid {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image: 
        linear-gradient(rgba(201, 146, 46, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(201, 146, 46, 0.05) 1px, transparent 1px);
      background-size: 60px 60px;
      opacity: 0.4;
      pointer-events: none;
    }

    /* Hydraulic Vault Portal Container */
    .vault-portal {
      position: relative;
      width: 380px;
      height: 320px;
      margin: 0 auto 36px auto;
      cursor: pointer;
      transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .vault-portal:hover {
      transform: scale(1.03) translateZ(20px);
    }

    /* Laser Seam Line */
    .vault-seam-laser {
      position: absolute;
      top: -20px;
      bottom: -20px;
      left: 50%;
      width: 3px;
      background: linear-gradient(180deg, transparent, #FFFFFF 30%, #F5D77F 50%, #C9922E 80%, transparent);
      box-shadow: 0 0 20px #F5D77F, 0 0 40px #C9922E;
      transform: translateX(-50%);
      z-index: 40;
      transition: opacity 0.6s ease, transform 0.6s ease;
      animation: laserPulse 2s infinite alternate ease-in-out;
    }

    @keyframes laserPulse {
      0% { opacity: 0.6; filter: blur(0.5px); }
      100% { opacity: 1; filter: blur(1px); }
    }

    /* Left & Right Vault Door Wings */
    .vault-wing {
      position: absolute;
      top: 0; bottom: 0; width: 50%;
      overflow: hidden;
      transition: transform 1.2s cubic-bezier(0.2, 0.9, 0.3, 1), opacity 1.2s ease, filter 1.2s ease;
      z-index: 30;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8);
      background: linear-gradient(145deg, #0F1728 0%, #060B14 100%);
      border: 1px solid rgba(201, 146, 46, 0.3);
    }

    .vault-wing-left {
      left: 0;
      border-radius: 20px 0 0 20px;
      border-right: none;
      transform-origin: left center;
    }

    .vault-wing-right {
      right: 0;
      border-radius: 0 20px 20px 0;
      border-left: none;
      transform-origin: right center;
    }

    .vault-wing-left svg {
      position: absolute;
      left: 0; top: 15px;
      width: 380px; height: 290px;
    }

    .vault-wing-right svg {
      position: absolute;
      left: 0; top: 15px;
      width: 380px; height: 290px;
    }

    /* Holographic Core Unveiled Behind Vault */
    .vault-hologram-core {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      border-radius: 20px;
      background: radial-gradient(circle at center, rgba(56, 189, 248, 0.18) 0%, rgba(6, 11, 20, 0.95) 75%);
      border: 1px solid rgba(56, 189, 248, 0.4);
      box-shadow: 0 0 50px rgba(56, 189, 248, 0.25), inset 0 0 30px rgba(201, 146, 46, 0.2);
      z-index: 10;
      opacity: 0;
      transition: opacity 1s ease 0.3s;
      pointer-events: none;
    }

    .holo-glow-ring {
      position: absolute;
      width: 180px;
      height: 180px;
      border-radius: 50%;
      border: 2px dashed var(--gold-bright);
      animation: holoRingSpin 15s linear infinite;
    }

    .holo-badge {
      font-family: 'Cinzel', serif;
      font-size: 11px;
      letter-spacing: 3px;
      color: #F5D77F;
      text-transform: uppercase;
      font-weight: 700;
      background: rgba(10, 17, 30, 0.9);
      border: 1px solid var(--gold);
      padding: 6px 14px;
      border-radius: 20px;
      box-shadow: 0 0 15px rgba(201, 146, 46, 0.3);
      z-index: 2;
    }

    @keyframes holoRingSpin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    /* Vault Breakout Splitting Transformations */
    .vault-hero-section.is-unlocked .vault-wing-left {
      transform: translateX(-220px) rotateY(-42deg) scale(0.9);
      opacity: 0.15;
      filter: blur(2px);
    }

    .vault-hero-section.is-unlocked .vault-wing-right {
      transform: translateX(220px) rotateY(42deg) scale(0.9);
      opacity: 0.15;
      filter: blur(2px);
    }

    .vault-hero-section.is-unlocked .vault-seam-laser {
      opacity: 0;
      transform: scaleY(0);
    }

    .vault-hero-section.is-unlocked .vault-hologram-core {
      opacity: 1;
      pointer-events: auto;
      box-shadow: 0 0 70px rgba(56, 189, 248, 0.4), inset 0 0 40px rgba(201, 146, 46, 0.35);
    }

    /* ==========================================================================
       DEVELOPER PATEL OM BADGES, ANIMATIONS & GLOW EFFECTS
       ========================================================================== */
    .dev-badge-nav {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 20px;
      background: linear-gradient(135deg, rgba(201, 146, 46, 0.12) 0%, rgba(19, 30, 51, 0.6) 100%);
      border: 1px solid rgba(212, 175, 55, 0.35);
      font-size: 12px;
      font-weight: 500;
      color: var(--text-main);
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 0 15px rgba(201, 146, 46, 0.15);
      text-decoration: none;
    }

    .dev-badge-nav:hover {
      background: linear-gradient(135deg, rgba(201, 146, 46, 0.25) 0%, rgba(56, 189, 248, 0.15) 100%);
      border-color: var(--gold-bright);
      transform: translateY(-2px);
      box-shadow: 0 0 25px rgba(245, 215, 127, 0.4);
    }

    .dev-pulse-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10B981;
      box-shadow: 0 0 8px #10B981;
      animation: devDotPulse 1.8s infinite;
    }

    @keyframes devDotPulse {
      0%, 100% { transform: scale(1); opacity: 1; box-shadow: 0 0 6px #10B981; }
      50% { transform: scale(1.4); opacity: 0.7; box-shadow: 0 0 14px #10B981, 0 0 20px #38BDF8; }
    }

    .dev-sparkle-text {
      background: linear-gradient(90deg, #FDF0BD 0%, #D4AF37 40%, #FFFFFF 50%, #D4AF37 60%, #FDF0BD 100%);
      background-size: 200% auto;
      color: transparent;
      -webkit-background-clip: text;
      background-clip: text;
      font-weight: 700;
      animation: devShimmer 3s linear infinite;
    }

    @keyframes devShimmer {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }

    .hero-dev-badge {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 22px;
      margin-bottom: 22px;
      border-radius: 30px;
      background: rgba(11, 18, 32, 0.85);
      backdrop-filter: blur(12px);
      border: 1.5px solid rgba(212, 175, 55, 0.4);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), 0 0 20px rgba(201, 146, 46, 0.2);
      cursor: pointer;
      transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
      animation: heroDevFloat 4s ease-in-out infinite;
    }

    .hero-dev-badge:hover {
      transform: scale(1.04) translateY(-3px);
      border-color: var(--gold-bright);
      box-shadow: 0 15px 40px rgba(0, 0, 0, 0.8), 0 0 35px rgba(245, 215, 127, 0.45);
    }

    @keyframes heroDevFloat {
      0%, 100% { transform: translateY(0px); }
      50% { transform: translateY(-5px); }
    }

    .footer-dev-card {
      background: linear-gradient(145deg, #0D1626 0%, #060B14 100%);
      border: 1.5px solid rgba(212, 175, 55, 0.35);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 36px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      flex-wrap: wrap;
      box-shadow: 0 12px 35px rgba(0, 0, 0, 0.6);
      transition: all 0.3s ease;
      text-align: left;
    }

    .footer-dev-card:hover {
      border-color: var(--gold-bright);
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.8), 0 0 25px rgba(201, 146, 46, 0.25);
    }

    .footer-dev-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .dev-avatar-circle {
      width: 54px;
      height: 54px;
      border-radius: 50%;
      background: linear-gradient(135deg, #1A2942 0%, #080D17 100%);
      border: 2px solid var(--gold);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 19px;
      font-weight: 800;
      color: var(--gold-bright);
      position: relative;
      box-shadow: 0 0 20px rgba(201, 146, 46, 0.3);
      flex-shrink: 0;
    }

    .dev-avatar-circle::before {
      content: '';
      position: absolute;
      inset: -4px;
      border-radius: 50%;
      padding: 2px;
      background: conic-gradient(from 0deg, transparent 0%, #F5D77F 50%, transparent 100%);
      -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      animation: avatarSpin 4s linear infinite;
    }

    @keyframes avatarSpin {
      100% { transform: rotate(360deg); }
    }

    .tech-pill {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(201, 146, 46, 0.12);
      border: 1px solid rgba(201, 146, 46, 0.3);
      font-size: 11px;
      color: var(--gold-bright);
      font-family: 'JetBrains Mono', monospace;
      margin: 3px;
    }

    .dev-email-link {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--gold-bright);
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      transition: color 0.2s ease;
    }

    .dev-email-link:hover {
      color: #FFFFFF;
      text-decoration: underline;
    }

    /* Interactive Unlock Action Pill */
    .unlock-trigger-pill {
      margin-top: 14px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 18px;
      background: rgba(201, 146, 46, 0.15);
      border: 1px solid rgba(201, 146, 46, 0.4);
      border-radius: 30px;
      color: var(--gold-bright);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s;
    }
    .unlock-trigger-pill:hover {
      background: rgba(201, 146, 46, 0.3);
      border-color: var(--gold);
    }

    /* Typewriter Section */
    .hero-content {
      text-align: center;
      max-width: 900px;
      margin: 0 auto;
      position: relative;
      z-index: 20;
    }

    .typewriter-title {
      font-size: 54px;
      font-weight: 800;
      line-height: 1.15;
      margin-bottom: 20px;
      min-height: 64px;
    }

    .typewriter-cursor {
      display: inline-block;
      width: 4px;
      height: 0.9em;
      background: var(--gold-bright);
      vertical-align: -0.05em;
      margin-left: 6px;
      animation: cursorBlink 0.8s infinite;
      box-shadow: 0 0 10px var(--gold-bright);
    }

    @keyframes cursorBlink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0; }
    }

    .hero-subtitle {
      font-size: 18px;
      color: var(--text-muted);
      max-width: 720px;
      margin: 0 auto 36px auto;
      line-height: 1.7;
    }

    /* Procedural Ahmedabad Skyline */
    .skyline-frame {
      width: 100%;
      height: 200px;
      margin-top: 10px;
      position: relative;
      z-index: 2;
    }

    .skyline-svg {
      width: 100%;
      height: 100%;
      opacity: 0.7;
    }

    /* Facts Bar */
    .facts-strip {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border);
      padding: 24px 0;
    }

    .facts-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 20px;
    }

    .fact-item {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 14px 20px;
      background: rgba(15, 24, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }

    .fact-icon { font-size: 26px; }
    .fact-num { font-size: 20px; font-weight: 700; color: var(--text-main); }
    .fact-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }

    /* ==========================================================================
       VALUATION SUITE & STREAMLINED 2-WAY SELECTOR
       ========================================================================== */
    .valuation-section {
      padding: 80px 0;
      position: relative;
    }

    .section-header { text-align: center; margin-bottom: 48px; }
    .section-badge {
      color: var(--gold);
      text-transform: uppercase;
      letter-spacing: 2.5px;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
      display: block;
    }

    .section-title { font-size: 38px; margin-bottom: 12px; }
    .section-desc { color: var(--text-muted); font-size: 16px; max-width: 600px; margin: 0 auto; }

    .calc-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 42px;
      box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.7);
    }

    /* 2-Way Property Type Selector */
    .prop-type-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 32px;
    }

    .prop-type-card {
      background: var(--bg-surface);
      border: 2px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      cursor: pointer;
      transition: all 0.25s ease;
      display: flex;
      gap: 18px;
    }

    .prop-type-card:hover {
      border-color: rgba(201, 146, 46, 0.5);
      transform: translateY(-2px);
    }

    .prop-type-card.active {
      border-color: var(--gold);
      background: rgba(201, 146, 46, 0.08);
      box-shadow: var(--gold-glow);
    }

    .prop-type-icon { font-size: 32px; line-height: 1; }
    .prop-type-title { font-size: 18px; font-weight: 700; color: var(--text-main); margin-bottom: 4px; }
    .prop-type-desc { font-size: 13px; color: var(--text-muted); line-height: 1.4; }
    .prop-type-tag {
      display: inline-block;
      margin-top: 8px;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 4px;
      background: rgba(201, 146, 46, 0.2);
      color: var(--gold-bright);
    }

    /* Clean Streamlined Inputs (Location + Area in Sq. Yards only) */
    .inputs-grid-simple {
      display: grid;
      grid-template-columns: 2fr 1.5fr 200px;
      gap: 20px;
      align-items: flex-end;
    }

    .form-group { display: flex; flex-direction: column; gap: 8px; }
    .form-label {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .form-control {
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
      color: var(--text-main);
      font-size: 15px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
      width: 100%;
    }

    .form-control:focus {
      border-color: var(--gold);
      box-shadow: 0 0 0 3px rgba(201, 146, 46, 0.2);
    }

    /* Auth Gate Card (Shown when unauthenticated user tries to calculate) */
    .auth-gate-box {
      margin-top: 36px;
      background: linear-gradient(145deg, #152238 0%, #0A1120 100%);
      border: 1.5px dashed var(--gold);
      border-radius: var(--radius-lg);
      padding: 40px 30px;
      text-align: center;
      display: none;
      animation: fadeInUp 0.4s ease;
    }

    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(15px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .gate-icon {
      width: 64px;
      height: 64px;
      background: rgba(201, 146, 46, 0.15);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 30px;
      color: var(--gold-bright);
      margin: 0 auto 16px auto;
      border: 1.5px solid var(--gold);
      box-shadow: var(--gold-glow);
    }

    .gate-title { font-size: 24px; margin-bottom: 8px; color: var(--text-main); }
    .gate-desc { font-size: 14px; color: var(--text-muted); max-width: 540px; margin: 0 auto 24px auto; line-height: 1.6; }

    /* Results Showcase (Shown when authenticated) */
    .results-container {
      margin-top: 40px;
      display: none;
      animation: fadeInUp 0.5s ease;
    }

    .results-grid {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 28px;
    }

    .result-hero-card {
      background: linear-gradient(145deg, #121D33 0%, #0A101E 100%);
      border: 1px solid var(--border-focus);
      border-radius: var(--radius-lg);
      padding: 36px;
      position: relative;
      overflow: hidden;
      box-shadow: 0 15px 40px rgba(0, 0, 0, 0.6);
    }

    .result-badge {
      display: inline-block;
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 700;
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-green);
      margin-bottom: 16px;
    }

    .val-heading {
      font-size: 13px;
      color: var(--gold);
      letter-spacing: 1.5px;
      text-transform: uppercase;
      font-weight: 700;
    }

    .val-main-price {
      font-size: 48px;
      font-weight: 800;
      color: var(--gold-bright);
      margin: 8px 0 4px 0;
      letter-spacing: -1px;
    }

    .val-full-price {
      font-size: 14px;
      color: var(--text-muted);
      margin-bottom: 24px;
    }

    .metrics-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
    }

    .metric-box {
      background: rgba(6, 11, 20, 0.7);
      padding: 14px;
      border-radius: 10px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .metric-lbl { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-val { font-size: 18px; font-weight: 700; color: var(--text-main); margin-top: 4px; }

    .card-panel {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 28px;
      margin-top: 28px;
    }

    .panel-title {
      font-size: 20px;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .proj-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
    }

    .proj-table th {
      text-align: left;
      padding: 12px 14px;
      font-size: 12px;
      text-transform: uppercase;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
    }

    .proj-table td {
      padding: 14px;
      font-size: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }

    .proj-table tr:hover td { background: rgba(201, 146, 46, 0.05); }

    .chart-box {
      width: 100%;
      height: 240px;
      margin-top: 16px;
      background: var(--bg-surface);
      border-radius: var(--radius);
      padding: 16px;
      border: 1px solid var(--border);
    }

    /* Locality Intelligence */
    .intel-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-top: 16px;
    }

    .intel-block {
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
    }

    .intel-block-title {
      font-size: 12px;
      color: var(--gold);
      text-transform: uppercase;
      letter-spacing: 1px;
      font-weight: 700;
      margin-bottom: 10px;
    }

    .tag-cloud { display: flex; flex-wrap: wrap; gap: 6px; }
    .info-tag {
      font-size: 12px;
      background: rgba(255, 255, 255, 0.06);
      color: #E2E8F0;
      padding: 5px 12px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Locality Directory */
    .explorer-section {
      padding: 80px 0;
      background: var(--bg-surface);
      border-top: 1px solid var(--border);
    }

    .filters-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 32px;
      gap: 16px;
      flex-wrap: wrap;
    }

    .zone-pills { display: flex; gap: 8px; }
    .zone-pill {
      padding: 8px 20px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 30px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
    }

    .zone-pill:hover, .zone-pill.active {
      background: var(--gold-gradient);
      color: #04070D;
      border-color: var(--gold);
      font-weight: 700;
    }

    .locality-cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
    }

    .loc-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px;
      transition: all 0.25s ease;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .loc-card:hover {
      border-color: var(--gold);
      transform: translateY(-3px);
      box-shadow: 0 12px 30px -8px rgba(0, 0, 0, 0.7);
    }

    .loc-name { font-size: 18px; font-weight: 700; color: var(--text-main); }
    .loc-tier-badge {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 4px;
      background: rgba(201, 146, 46, 0.15);
      color: var(--gold-bright);
    }

    .loc-rate-highlight {
      font-size: 22px;
      font-weight: 700;
      color: var(--gold-bright);
      margin: 8px 0;
    }

    .loc-note-preview {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.4;
      margin-bottom: 16px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    /* Modal System */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(3, 6, 12, 0.9);
      backdrop-filter: blur(14px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 20px;
    }

    .modal-overlay.active { display: flex; }

    .modal-window {
      background: var(--bg-card);
      border: 1px solid var(--border-focus);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 480px;
      padding: 36px;
      box-shadow: 0 25px 60px rgba(0, 0, 0, 0.8);
      position: relative;
      animation: modalSlide 0.3s ease;
    }

    @keyframes modalSlide {
      from { transform: translateY(20px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }

    .modal-close {
      position: absolute;
      top: 20px; right: 20px;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 24px;
      cursor: pointer;
    }

    .modal-close:hover { color: var(--text-main); }
    .modal-title { font-size: 24px; margin-bottom: 8px; }
    .modal-subtitle { font-size: 13px; color: var(--text-muted); margin-bottom: 24px; }

    /* 6-box OTP input */
    .otp-input-row {
      display: flex;
      gap: 8px;
      justify-content: center;
      margin: 20px 0;
    }

    .otp-box-digit {
      width: 50px;
      height: 58px;
      text-align: center;
      font-size: 24px;
      font-weight: 700;
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--gold-bright);
      outline: none;
      transition: all 0.2s;
    }

    .otp-box-digit:focus {
      border-color: var(--gold);
      box-shadow: var(--gold-glow);
    }

    .demo-otp-banner {
      background: rgba(201, 146, 46, 0.15);
      border: 1px dashed var(--gold);
      border-radius: 8px;
      padding: 12px;
      text-align: center;
      font-size: 13px;
      color: var(--gold-bright);
      margin: 16px 0;
    }

    /* Password Unhide / Toggle Input Wrapper */
    .password-wrapper {
      position: relative;
      display: flex;
      align-items: center;
      width: 100%;
    }

    .password-wrapper .form-control {
      padding-right: 44px;
      width: 100%;
    }

    .btn-toggle-password {
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      z-index: 5;
    }

    .btn-toggle-password:hover {
      color: var(--gold-bright);
      transform: translateY(-50%) scale(1.15);
    }

    /* Footer */
    .footer {
      background: var(--bg-void);
      border-top: 1px solid var(--border);
      padding: 60px 0 30px 0;
    }

    .footer-grid {
      display: grid;
      grid-template-columns: 2fr 1fr 1fr 1fr;
      gap: 40px;
      margin-bottom: 40px;
    }

    .footer-bottom {
      border-top: 1px solid var(--border);
      padding-top: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 13px;
      color: var(--text-dim);
    }

    /* Admin Portal Styles */
    .admin-tab-nav {
      display: flex;
      gap: 12px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
      padding-bottom: 10px;
    }

    .admin-tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-family: 'Outfit', sans-serif;
      font-size: 14px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .admin-tab-btn.active {
      background: rgba(201, 146, 46, 0.15);
      color: var(--gold-bright);
      border: 1px solid rgba(201, 146, 46, 0.4);
    }

    .admin-table-container {
      max-height: 460px;
      overflow-y: auto;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(6, 11, 20, 0.7);
    }

    .admin-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }

    .admin-table th {
      position: sticky;
      top: 0;
      background: #0B1220;
      color: var(--gold-bright);
      padding: 12px 14px;
      font-weight: 600;
      border-bottom: 1px solid var(--border);
      z-index: 2;
    }

    .admin-table td {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(24, 38, 63, 0.5);
      color: var(--text-main);
    }

    .admin-table tr:hover td {
      background: rgba(201, 146, 46, 0.05);
    }

    .btn-danger-sm {
      background: rgba(239, 68, 68, 0.15);
      color: #EF4444;
      border: 1px solid rgba(239, 68, 68, 0.4);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }

    .btn-danger-sm:hover {
      background: #EF4444;
      color: #FFFFFF;
      box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);
    }

    .btn-edit-sm {
      background: rgba(201, 146, 46, 0.15);
      color: var(--gold-bright);
      border: 1px solid rgba(201, 146, 46, 0.4);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }

    .btn-edit-sm:hover {
      background: var(--gold);
      color: #000000;
    }

    /* Bilingual TTS & Price Context Intelligence Styles */
    .tts-toolbar {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      background: rgba(19, 30, 51, 0.85);
      border: 1px solid rgba(201, 146, 46, 0.3);
      padding: 4px 8px;
      border-radius: 30px;
    }

    .tts-lang-toggle {
      display: inline-flex;
      background: rgba(6, 11, 20, 0.9);
      border-radius: 20px;
      padding: 2px;
      border: 1px solid var(--border);
    }

    .tts-lang-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 16px;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .tts-lang-btn.active {
      background: var(--gold);
      color: #060B14;
      box-shadow: 0 0 10px rgba(201, 146, 46, 0.4);
    }

    .tts-speak-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: linear-gradient(135deg, rgba(201, 146, 46, 0.25) 0%, rgba(201, 146, 46, 0.1) 100%);
      border: 1px solid var(--gold);
      color: #F5D77F;
      font-size: 12px;
      font-weight: 700;
      padding: 5px 14px;
      border-radius: 20px;
      cursor: pointer;
      transition: all 0.25s ease;
    }

    .tts-speak-btn:hover {
      background: var(--gold);
      color: #060B14;
      box-shadow: 0 0 14px rgba(201, 146, 46, 0.5);
    }

    .tts-speak-btn.is-playing {
      background: rgba(16, 185, 129, 0.2);
      border-color: var(--accent-green);
      color: var(--accent-green);
    }

    .audio-wave-anim {
      display: inline-flex;
      align-items: flex-end;
      gap: 2px;
      height: 12px;
      margin-left: 4px;
    }

    .audio-wave-anim span {
      display: inline-block;
      width: 2.5px;
      background: currentColor;
      border-radius: 2px;
      animation: waveBar 0.8s ease-in-out infinite alternate;
    }
    .audio-wave-anim span:nth-child(1) { height: 4px; animation-delay: 0.1s; }
    .audio-wave-anim span:nth-child(2) { height: 12px; animation-delay: 0.3s; }
    .audio-wave-anim span:nth-child(3) { height: 7px; animation-delay: 0.2s; }
    .audio-wave-anim span:nth-child(4) { height: 10px; animation-delay: 0.4s; }

    @keyframes waveBar {
      0% { transform: scaleY(0.3); }
      100% { transform: scaleY(1.0); }
    }

    /* Floating Siri-Style Voice Assistant Orb */
    .siri-orb-widget {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999;
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      background: rgba(10, 17, 30, 0.9);
      border: 1px solid rgba(56, 189, 248, 0.4);
      padding: 7px 16px 7px 10px;
      border-radius: 30px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), 0 0 20px rgba(56, 189, 248, 0.25);
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .siri-orb-widget:hover {
      transform: translateY(-3px) scale(1.04);
      border-color: var(--gold);
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.8), 0 0 25px rgba(201, 146, 46, 0.35);
    }

    .siri-orb {
      width: 30px;
      height: 30px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #38BDF8 0%, #818CF8 50%, #C9922E 100%);
      box-shadow: 0 0 14px rgba(56, 189, 248, 0.6);
      position: relative;
      animation: siriOrbPulse 3s ease-in-out infinite alternate;
    }

    .siri-orb-widget.is-speaking .siri-orb {
      animation: siriOrbActive 0.8s ease-in-out infinite alternate;
      box-shadow: 0 0 25px #38BDF8, 0 0 35px #F5D77F;
    }

    @keyframes siriOrbPulse {
      0% { transform: scale(0.92); opacity: 0.85; filter: hue-rotate(0deg); }
      100% { transform: scale(1.08); opacity: 1; filter: hue-rotate(45deg); }
    }

    @keyframes siriOrbActive {
      0% { transform: scale(0.9); filter: hue-rotate(0deg); }
      50% { transform: scale(1.15); filter: hue-rotate(180deg); }
      100% { transform: scale(0.95); filter: hue-rotate(360deg); }
    }

    .siri-label {
      display: flex;
      flex-direction: column;
      text-align: left;
    }

    .siri-title {
      font-size: 12px;
      font-weight: 700;
      color: #F8FAFC;
      letter-spacing: 0.5px;
    }

    .siri-sub {
      font-size: 10px;
      color: #94A3B8;
    }

    /* ==========================================================================
       CINEMATIC 4-SECOND NETFLIX-STYLE INTRO SPLASH CSS
       ========================================================================== */
    .cinematic-splash {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      width: 100vw; height: 100vh;
      background: #02050A;
      z-index: 10000;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      transition: opacity 0.7s cubic-bezier(0.16, 1, 0.3, 1), visibility 0.7s ease;
    }

    .cinematic-splash.is-hidden {
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
    }

    .splash-logo-stage {
      position: absolute;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      z-index: 2;
      animation: splashLogoAnim 2s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
    }

    .splash-vr-icon {
      filter: drop-shadow(0 0 25px rgba(201, 146, 46, 0.8));
      animation: splashIconGlow 1.5s ease-out forwards;
    }

    .splash-title {
      font-size: 48px;
      letter-spacing: 12px;
      color: #F8FAFC;
      margin: 16px 0 6px 0;
      text-shadow: 0 0 30px rgba(245, 215, 127, 0.7), 0 0 60px rgba(201, 146, 46, 0.5);
      background: linear-gradient(135deg, #FFFFFF 0%, #F5D77F 50%, #C9922E 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .splash-subtitle {
      font-family: 'Outfit', sans-serif;
      font-size: 13px;
      letter-spacing: 6px;
      color: #38BDF8;
      font-weight: 600;
      text-transform: uppercase;
      opacity: 0.9;
    }

    .splash-flare {
      position: absolute;
      width: 140%;
      height: 2px;
      background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.8), #FFFFFF, rgba(245, 215, 127, 0.8), transparent);
      box-shadow: 0 0 20px #38BDF8, 0 0 30px #F5D77F;
      animation: flareSweep 1.8s ease-in-out forwards;
    }

    @keyframes splashLogoAnim {
      0% { opacity: 0; transform: scale(0.85); filter: blur(8px); }
      30% { opacity: 1; transform: scale(1); filter: blur(0px); }
      75% { opacity: 1; transform: scale(1.04); }
      100% { opacity: 0; transform: scale(1.18); filter: blur(6px); }
    }

    @keyframes splashIconGlow {
      0% { transform: scale(0.6); opacity: 0; }
      50% { transform: scale(1.08); opacity: 1; }
      100% { transform: scale(1); opacity: 1; }
    }

    @keyframes flareSweep {
      0% { transform: scaleX(0); opacity: 0; }
      40% { transform: scaleX(1); opacity: 1; }
      100% { transform: scaleX(1.4); opacity: 0; }
    }

    .splash-skyline-stage {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background-size: cover;
      background-position: center 30%;
      z-index: 1;
      opacity: 0;
      animation: skylineReveal 2.2s cubic-bezier(0.16, 1, 0.3, 1) 1.6s forwards;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      padding-bottom: 50px;
    }

    .skyline-overlay {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background: radial-gradient(circle at center, rgba(6, 11, 20, 0.3) 0%, rgba(2, 5, 10, 0.85) 100%);
    }

    .skyline-caption {
      position: relative;
      z-index: 2;
      font-size: 16px;
      letter-spacing: 5px;
      color: #F5D77F;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.9);
      font-weight: 700;
    }

    @keyframes skylineReveal {
      0% { opacity: 0; transform: scale(1.15); filter: blur(4px); }
      30% { opacity: 1; transform: scale(1.05); filter: blur(0px); }
      75% { opacity: 1; transform: scale(1.0); }
      100% { opacity: 0; transform: scale(0.98); }
    }

    .splash-skip-btn {
      position: absolute;
      bottom: 24px;
      right: 24px;
      z-index: 10;
      background: rgba(10, 17, 30, 0.7);
      border: 1px solid rgba(201, 146, 46, 0.4);
      color: #F5D77F;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 1px;
      padding: 6px 14px;
      border-radius: 20px;
      cursor: pointer;
      backdrop-filter: blur(8px);
      transition: all 0.2s ease;
    }
    .splash-skip-btn:hover {
      background: var(--gold);
      color: #060B14;
    }

    @media (max-width: 900px) {
      .typewriter-title { font-size: 36px; }
      .facts-grid { grid-template-columns: repeat(2, 1fr); }
      .inputs-grid-simple { grid-template-columns: 1fr; }
      .results-grid { grid-template-columns: 1fr; }
      .prop-type-grid { grid-template-columns: 1fr; }
      .intel-grid { grid-template-columns: 1fr; }
      .footer-grid { grid-template-columns: 1fr; }
      .vault-portal { width: 300px; height: 260px; }
    }
  </style>
</head>
<body>

  <!-- ==========================================================================
       CINEMATIC 4-SECOND NETFLIX-STYLE INTRO SPLASH
       ========================================================================== -->
  <div class="cinematic-splash" id="cinematicSplash">
    <!-- Stage 1: Golden Monogram & Logo Reveal -->
    <div class="splash-logo-stage" id="splashLogoStage">
      <div class="splash-vr-icon">
        <svg viewBox="0 0 100 90" width="80" height="72" fill="none">
          <polygon points="15,20 28,20 44,65 34,65" fill="#F5D77F"/>
          <polygon points="45,18 52,14 52,65 45,65" fill="#131E33"/>
          <polygon points="52,14 58,18 58,65 52,65" fill="#C9922E"/>
          <path d="M60,22 L72,22 C82,22 86,30 86,40 C86,50 78,56 68,56 L60,56" stroke="#38BDF8" stroke-width="7"/>
          <path d="M68,54 L84,72" stroke="#F5D77F" stroke-width="7" stroke-linecap="round"/>
          <path d="M10,75 Q 50,68 90,75" stroke="#C9922E" stroke-width="3" stroke-linecap="round"/>
        </svg>
      </div>
      <h1 class="splash-title cinzel">VASUDHA</h1>
      <div class="splash-subtitle">REAL ESTATE • AHMEDABAD</div>
      <div class="splash-flare"></div>
    </div>

    <!-- Stage 2: Skyline & High-Rise Transition -->
    <div class="splash-skyline-stage" id="splashSkylineStage" style="background-image: url('/splash_skyline.jpg');">
      <div class="skyline-overlay"></div>
      <div class="skyline-caption cinzel">PRECISION PROPERTY INTELLIGENCE</div>
    </div>

    <!-- Skip Intro Button -->
    <button type="button" class="splash-skip-btn" onclick="dismissCinematicSplash()">Skip ➔</button>
  </div>

  <!-- Ambient Glow Pointer Tracking -->
  <div class="glow-blob" id="glowBlob"></div>

  <!-- Navigation Bar -->
  <nav class="navbar">
    <div class="container nav-inner">
      <a href="/" class="brand">
        <div class="brand-vr-icon">
          <!-- Mini VR Monogram SVG -->
          <svg viewBox="0 0 100 90" width="36" height="32" fill="none">
            <polygon points="15,20 28,20 44,65 34,65" fill="#F5D77F"/>
            <polygon points="45,18 52,14 52,65 45,65" fill="#131E33"/>
            <polygon points="52,14 58,18 58,65 52,65" fill="#C9922E"/>
            <path d="M60,22 L72,22 C82,22 86,30 86,40 C86,50 78,56 68,56 L60,56" stroke="#38BDF8" stroke-width="7"/>
            <path d="M68,54 L84,72" stroke="#F5D77F" stroke-width="7" stroke-linecap="round"/>
            <path d="M10,75 Q 50,68 90,75" stroke="#C9922E" stroke-width="3" stroke-linecap="round"/>
          </svg>
        </div>
        <div>
          <div class="brand-title cinzel">VASUDHA</div>
          <div class="brand-subtitle">AHMEDABAD VALUATION</div>
        </div>
      </a>

      <div class="nav-links">
        <a href="#valuation" class="nav-link">Valuation Suite</a>
        <a href="#explorer" class="nav-link">Micro-Markets (25+)</a>
        <a href="#heritage" class="nav-link">Ahmedabad Belts</a>
      </div>

      <div class="auth-bar" id="authBar" style="display: flex; align-items: center; gap: 10px;">
        <div class="dev-badge-nav" onclick="openModal('developerModal')" title="View Developer Profile">
          <div class="dev-pulse-dot"></div>
          <span>Dev:</span>
          <strong class="dev-sparkle-text">Patel Om</strong>
        </div>
        <a href="mailto:Vasudha.realestate.01@gmail.com" class="dev-badge-nav" title="Contact Support">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
          <span>Vasudha.realestate.01@gmail.com</span>
        </a>
        {% if session.get('user_id') %}
          <span style="font-size: 13px; color: var(--gold-bright);">
            👤 <strong>{{ session.get('user_name') }}</strong>
          </span>
          <a href="javascript:void(0)" onclick="handleUserLogout(event)" class="btn btn-outline" style="padding: 6px 14px; font-size: 12px; text-decoration: none;">Logout</a>
        {% else %}
          <button class="btn btn-ghost" onclick="openModal('loginModal')">Sign In</button>
          <button class="btn btn-gold" onclick="openModal('registerModal')">Create Account</button>
        {% endif %}
      </div>
    </div>
  </nav>

  <!-- ==========================================================================
       CINEMATIC 3D HYDRAULIC VAULT HERO
       ========================================================================== -->
  <section class="vault-hero-section" id="vaultHero">
    <div class="ambient-grid"></div>

    <div class="hero-content">

      <!-- Developer Floating Hero Badge -->
      <div>
        <div class="hero-dev-badge" onclick="openModal('developerModal')" title="Architect & Developer: Patel Om">
          <div class="dev-pulse-dot"></div>
          <span style="font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 600;">ENGINEERED & DEVELOPED BY</span>
          <strong class="dev-sparkle-text cinzel" style="font-size: 14px; letter-spacing: 2px;">PATEL OM</strong>
        </div>
      </div>
      
      <!-- Interactive 3D Hydraulic Vault Portal -->
      <div class="vault-portal" onclick="triggerVaultBreakout()" title="Click to open portal">
        <!-- Center Seam Laser -->
        <div class="vault-seam-laser"></div>

        <!-- Left Vault Wing (V Side) -->
        <div class="vault-wing vault-wing-left">
          <svg viewBox="0 0 380 290" fill="none">
            <defs>
              <linearGradient id="vaultGoldGradL" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#FDF0BD" />
                <stop offset="40%" stop-color="#D4AF37" />
                <stop offset="80%" stop-color="#8F6010" />
                <stop offset="100%" stop-color="#E5C158" />
              </linearGradient>
            </defs>
            <!-- Left Gold V Monogram -->
            <polygon points="50,75 95,75 168,195 132,195" fill="url(#vaultGoldGradL)" />
            <polygon points="88,75 118,75 178,175 158,175" fill="#FDF0BD" />
            <!-- Skyscraper 1 -->
            <polygon points="172,62 190,52 190,195 172,195" fill="#0A111E" stroke="#18263F" stroke-width="1" />
            <polygon points="182,56 190,52 190,195 182,195" fill="url(#vaultGoldGradL)" />
            <line x1="179" y1="75" x2="179" y2="190" stroke="#38BDF8" stroke-width="1.5" opacity="0.7" />
            <!-- Base Arc Left -->
            <path d="M30,220 Q 110,210 190,195" stroke="url(#vaultGoldGradL)" stroke-width="3.5" stroke-linecap="round" />
            <!-- Typography Left -->
            <text x="184" y="255" font-family="'Cinzel', serif" font-size="32" font-weight="900" letter-spacing="8" fill="#F5D77F" text-anchor="end">VASU</text>
            <line x1="30" y1="275" x2="186" y2="275" stroke="url(#vaultGoldGradL)" stroke-width="2" />
          </svg>
        </div>

        <!-- Right Vault Wing (R Side) -->
        <div class="vault-wing vault-wing-right">
          <svg viewBox="0 0 380 290" fill="none">
            <defs>
              <linearGradient id="vaultGoldGradR" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#FDF0BD" />
                <stop offset="40%" stop-color="#D4AF37" />
                <stop offset="80%" stop-color="#8F6010" />
                <stop offset="100%" stop-color="#E5C158" />
              </linearGradient>
            </defs>
            <!-- Right Skyscraper (meets at seam) -->
            <polygon points="0,52 12,58 12,195 0,195" fill="#FDF0BD" />
            <polygon points="12,58 24,68 24,195 12,195" fill="url(#vaultGoldGradR)" />
            <line x1="6" y1="75" x2="6" y2="190" stroke="#38BDF8" stroke-width="1.5" opacity="0.7" />
            <!-- Skyscraper 2 & 3 -->
            <polygon points="24,80 40,70 40,195 24,195" fill="#0A111E" stroke="#18263F" stroke-width="1" />
            <polygon points="40,70 52,78 52,195 40,195" fill="url(#vaultGoldGradR)" />
            <!-- R Monogram -->
            <path d="M42,95 L72,95 C98,95 110,108 110,125 C110,142 96,152 72,152 L50,152" fill="none" stroke="#0E1726" stroke-width="14" stroke-linecap="square" />
            <path d="M44,95 L72,95 C96,95 106,106 106,125 C106,140 94,150 72,150 L52,150" fill="none" stroke="url(#vaultGoldGradR)" stroke-width="10" stroke-linecap="square" />
            <path d="M68,148 C80,148 94,162 108,180 L130,210 C124,210 112,210 95,190 L75,156 Z" fill="url(#vaultGoldGradR)" stroke="#0E1726" stroke-width="1" />
            <!-- Base Arc Right -->
            <path d="M0,195 Q 80,210 160,220" stroke="url(#vaultGoldGradR)" stroke-width="3.5" stroke-linecap="round" />
            <!-- Typography Right -->
            <text x="6" y="255" font-family="'Cinzel', serif" font-size="32" font-weight="900" letter-spacing="8" fill="#F5D77F" text-anchor="start">DHA</text>
            <line x1="4" y1="275" x2="160" y2="275" stroke="url(#vaultGoldGradR)" stroke-width="2" />
          </svg>
        </div>

        <!-- Holographic Core Unveiled Behind Vault -->
        <div class="vault-hologram-core">
          <div class="holo-glow-ring"></div>
          <div class="holo-badge">✨ AHMEDABAD VALUATION MATRIX ACTIVE</div>
        </div>
      </div>

      <!-- Action Pill to toggle/trigger breakout -->
      <div>
        <button class="unlock-trigger-pill" onclick="triggerVaultBreakout()">
          ⚡ Click or Scroll to Breakout & Reveal Platform
        </button>
      </div>

      <!-- Typewriter Hero Title -->
      <h1 class="typewriter-title cinzel">
        <span id="heroTypewriterText"></span><span class="typewriter-cursor"></span>
      </h1>

      <p class="hero-subtitle">
        Powered by an Ahmedabad-customized Machine Learning regression pipeline ($R^2 = 0.9996$). 
        Get instantaneous live market valuations for <strong>Flats & Apartments</strong> and <strong>Tenements & Duplexes</strong> with 5-year future compounding projections.
      </p>

      <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
        <a href="#valuation" class="btn btn-gold" style="padding: 14px 32px; font-size: 16px;">
          🚀 Calculate Property Value
        </a>
        <a href="#explorer" class="btn btn-outline" style="padding: 14px 32px; font-size: 16px;">
          📍 Explore Micro-Markets (25+)
        </a>
      </div>
    </div>

    <!-- Procedural Ahmedabad Skyline Frame -->
    <div class="skyline-frame">
      <svg class="skyline-svg" viewBox="0 0 1440 200" preserveAspectRatio="none" fill="none">
        <defs>
          <linearGradient id="skyGradLine" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#D4AF37" stop-opacity="0.3"/>
            <stop offset="100%" stop-color="#03060C" stop-opacity="0.95"/>
          </linearGradient>
        </defs>
        <!-- Distant Towers -->
        <path d="M120 200 V100 H150 V200 M180 200 V80 H210 V200 M260 200 V120 H290 V200 M420 200 V70 H470 V200 M520 200 V90 H550 V200 M820 200 V60 H860 V200 M910 200 V100 H940 V200 M1100 200 V50 H1150 V200 M1200 200 V110 H1240 V200 M1320 200 V85 H1360 V200" stroke="#18263F" stroke-width="1.5" fill="#0A1120"/>
        <!-- Atal Bridge Curve -->
        <path d="M50 170 Q 720 100 1390 170" stroke="url(#skyGradLine)" stroke-width="3" fill="none"/>
        <path d="M200 170 Q 720 115 1240 170" stroke="#C9922E" stroke-width="1.5" stroke-dasharray="4 4" fill="none" opacity="0.6"/>
        <!-- Sabarmati River Water -->
        <rect x="0" y="175" width="1440" height="25" fill="#070E1A"/>
        <line x1="0" y1="175" x2="1440" y2="175" stroke="#38BDF8" stroke-width="1" opacity="0.4"/>
      </svg>
    </div>
  </section>

  <!-- Facts Strip -->
  <section class="facts-strip">
    <div class="container facts-grid">
      <div class="fact-item">
        <div class="fact-icon">📍</div>
        <div>
          <div class="fact-num mono">25+</div>
          <div class="fact-label">Micro-Markets Covered</div>
        </div>
      </div>
      <div class="fact-item">
        <div class="fact-icon">📈</div>
        <div>
          <div class="fact-num mono">0.9996</div>
          <div class="fact-label">ML Fit Accuracy (R²)</div>
        </div>
      </div>
      <div class="fact-item">
        <div class="fact-icon">🏙️</div>
        <div>
          <div class="fact-num mono">2 Belts</div>
          <div class="fact-label">Sabarmati West & East</div>
        </div>
      </div>
      <div class="fact-item">
        <div class="fact-icon">⚡</div>
        <div>
          <div class="fact-num mono">~6.09%</div>
          <div class="fact-label">Compounding Annual CAGR</div>
        </div>
      </div>
    </div>
  </section>

  <!-- ==========================================================================
       MAIN VALUATION SUITE (AUTH GATED)
       ========================================================================== -->
  <section id="valuation" class="valuation-section">
    <div class="container">
      <div class="section-header">
        <span class="section-badge">Valuation Engine</span>
        <h2 class="section-title cinzel">Ahmedabad Property Price Estimator</h2>
        <p class="section-desc">Choose property archetype, select locality corridor, and enter plot or built-up size (in Sq. Yards / Gaj).</p>
      </div>

      <div class="calc-card">
        <!-- 2-Way Property Type Selector -->
        <label class="form-label" style="margin-bottom: 12px; display: block;">Step 1: Select Property Type</label>
        <div class="prop-type-grid">
          <div class="prop-type-card active" id="typeFlat" onclick="selectPropertyType('Apartment / Flat')">
            <div class="prop-type-icon">🏢</div>
            <div>
              <div class="prop-type-title">Apartment / Flat</div>
              <div class="prop-type-desc">High-rise or low-rise residential unit with shared land undivided share (UDS).</div>
              <span class="prop-type-tag">Baseline Rate (1.0x)</span>
            </div>
          </div>

          <div class="prop-type-card" id="typeTenement" onclick="selectPropertyType('Tenement / Duplex')">
            <div class="prop-type-icon">🏡</div>
            <div>
              <div class="prop-type-title">Tenement / Duplex</div>
              <div class="prop-type-desc">Independent residential structure with full plot/land ownership & private terrace.</div>
              <span class="prop-type-tag">Land & Structure Premium (1.28x)</span>
            </div>
          </div>
        </div>

        <!-- Step 2: Clean Form (Location + Area in Sq. Yards only) -->
        <label class="form-label" style="margin-bottom: 12px; display: block;">Step 2: Locality & Area Dimensions</label>
        <div class="inputs-grid-simple">
          <div class="form-group">
            <label class="form-label">Ahmedabad Locality</label>
            <select id="calcLocality" class="form-control">
              <option value="" disabled selected>Loading localities...</option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">Area (in Sq. Yards / Gaj)</label>
            <input type="number" id="calcArea" class="form-control mono" placeholder="e.g. 150" value="150" min="1" step="1">
          </div>

          <button id="calcBtn" class="btn btn-gold" onclick="calculateValuation()" style="height: 52px; font-size: 15px;">
            Calculate Valuation ➔
          </button>
        </div>

        <!-- Auth Gate Box (Appears when not logged in) -->
        <div id="authGateBox" class="auth-gate-box">
          <div class="gate-icon">🔒</div>
          <h3 class="gate-title cinzel">Member Verification Required</h3>
          <p class="gate-desc">
            To view live machine-learning property valuations, 5-year compounding appreciation schedules, and real historical price curves, please sign in or register with email OTP.
          </p>
          <div style="display: flex; gap: 14px; justify-content: center; flex-wrap: wrap;">
            <button class="btn btn-gold" onclick="openModal('registerModal')">Create Account (Instant OTP)</button>
            <button class="btn btn-outline" onclick="openModal('loginModal')">Sign In</button>
          </div>
        </div>

        <!-- Results Showcase (Shown when authenticated) -->
        <div class="results-container" id="resultsContainer">
          <div class="results-grid">
            <!-- Hero Result Card -->
            <div class="result-hero-card">
              <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap;">
                <div class="result-badge" id="resGrowthBadge">High Growth Corridor</div>
                <button id="btnShareEmail" type="button" class="btn btn-outline" onclick="openShareValuationModal()" style="padding: 6px 14px; font-size: 12px; border-color: var(--gold); color: var(--gold-bright); display: inline-flex; align-items: center; gap: 6px; cursor: pointer; transition: all 0.2s;" title="Share price calculation via email">
                  <span>✉️</span>
                  <span>Share via Email</span>
                </button>
              </div>
              <div class="val-heading" id="resLocHeading">BODAKDEV • APARTMENT / FLAT</div>
              <div class="val-main-price cinzel mono" id="resMainPrice">₹1.24 Cr</div>
              <div class="val-full-price mono" id="resFullPrice">Estimated Valuation: ₹1,24,20,000</div>

              <div class="metrics-row">
                <div class="metric-box">
                  <div class="metric-lbl">Rate per Sq. Yard (Gaj)</div>
                  <div class="metric-val mono" id="resRateSqyd">₹82,800</div>
                </div>
                <div class="metric-box">
                  <div class="metric-lbl">Rate per Sq. Foot</div>
                  <div class="metric-val mono" id="resRateSqft">₹9,200</div>
                </div>
                <div class="metric-box">
                  <div class="metric-lbl">Micro-Market Zone & Tier</div>
                  <div class="metric-val" id="resZoneTier" style="font-size: 15px;">West • Ultra-Luxury</div>
                </div>
                <div class="metric-box">
                  <div class="metric-lbl">Livability Rating</div>
                  <div class="metric-val mono" id="resLivability">9.6 / 10</div>
                </div>
              </div>
            </div>

            <!-- Historical Price Trend Line Chart -->
            <div class="card-panel" style="margin-top: 0;">
              <div class="panel-title">
                <span class="cinzel">Historical Price Trend</span>
                <span class="mono" style="font-size: 12px; color: var(--gold);" id="resTrendType">2020 – 2026</span>
              </div>
              <p style="font-size: 12px; color: var(--text-muted);" id="resTrendNote">Observed transaction data points and ML fitted growth curve.</p>
              
              <!-- SVG Line Chart Container -->
              <div class="chart-box" id="chartBox">
                <svg id="trendSvg" width="100%" height="100%" viewBox="0 0 420 200" preserveAspectRatio="none">
                  <!-- Generated dynamically via JS -->
                </svg>
              </div>
            </div>
          </div>

          <!-- Area Price Context Intelligence & Bilingual TTS Card -->
          <div class="card-panel" style="border-left: 3px solid var(--gold);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 10px;">
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="cinzel" style="font-size: 16px; font-weight: 700; color: var(--gold-bright);">Micro-Market Price Dynamics & Supply Rationale</span>
                  <span class="badge badge-gold" id="priceContextLocalityTag">Thaltej</span>
                </div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Builder supply constraints, redevelopment premiums & infrastructure impact.</div>
              </div>

              <!-- Audio & Bilingual Language Controls -->
              <div class="tts-toolbar">
                <div class="tts-lang-toggle" title="Select Voice Spoken Language">
                  <button type="button" class="tts-lang-btn active" id="ttsLangEn" onclick="setTtsLanguage('en')">English</button>
                  <button type="button" class="tts-lang-btn" id="ttsLangHi" onclick="setTtsLanguage('hi')">हिन्दी</button>
                </div>
                <button type="button" class="tts-speak-btn" id="ttsSpeakBtn" onclick="togglePriceSpeech()" title="Play Audio Voice Explanation">
                  <span class="tts-speaker-icon" id="ttsIcon">🔊</span>
                  <span id="ttsBtnText">Speak Rationale</span>
                  <div class="audio-wave-anim" id="audioWaveAnim" style="display: none;">
                    <span></span><span></span><span></span><span></span>
                  </div>
                </button>
              </div>
            </div>

            <!-- Dynamic English-Only On-Screen Text -->
            <p id="priceExplanationTextEn" style="font-size: 14px; line-height: 1.7; color: var(--text-main); margin-bottom: 14px; background: rgba(11, 18, 32, 0.6); padding: 14px 18px; border-radius: 10px; border: 1px solid rgba(201, 146, 46, 0.2);">
              Loading price rationale...
            </p>

            <!-- Key Price Drivers Tags -->
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--gold); font-weight: 700;">Key Pricing Drivers:</span>
              <div id="priceDriversTags" style="display: flex; gap: 8px; flex-wrap: wrap;"></div>
            </div>
          </div>

          <!-- 5-Year Future Projections -->
          <div class="card-panel">
            <div class="panel-title">
              <span class="cinzel">5-Year Valuation Projections (2027 – 2031)</span>
              <span class="mono" style="font-size: 13px; color: var(--accent-green);" id="res5yrGain">+34.3% Est. Total Appreciation</span>
            </div>
            <div style="overflow-x: auto;">
              <table class="proj-table">
                <thead>
                  <tr>
                    <th>Timeline</th>
                    <th>Rate / Sq.yd (Gaj)</th>
                    <th>Rate / Sq.ft</th>
                    <th>Projected Valuation</th>
                    <th>Cumulative Gain</th>
                  </tr>
                </thead>
                <tbody id="projTableBody">
                  <!-- Dynamically inserted -->
                </tbody>
              </table>
            </div>
          </div>

          <!-- Locality Deep-Dive Intelligence -->
          <div class="card-panel">
            <div class="panel-title">
              <span class="cinzel" id="intelTitle">Locality Infrastructure & Intelligence</span>
              <span class="mono" style="font-size: 12px; color: var(--text-muted);" id="intelSource">ML-Fitted Dataset</span>
            </div>
            <p style="font-size: 14px; color: var(--text-muted); line-height: 1.6;" id="intelOverview">
              Overview note...
            </p>

            <div class="intel-grid">
              <div class="intel-block">
                <div class="intel-block-title">🏛️ Prominent Landmarks & Hubs</div>
                <div class="tag-cloud" id="intelLandmarks"></div>
              </div>

              <div class="intel-block">
                <div class="intel-block-title">🏥 Healthcare & Education</div>
                <div class="tag-cloud" id="intelSchools"></div>
              </div>

              <div class="intel-block" style="grid-column: 1 / -1;">
                <div class="intel-block-title">🚇 Transit & Metro Connectivity</div>
                <p style="font-size: 13px; color: #CBD5E1;" id="intelTransit"></p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Locality Explorer Directory -->
  <section id="explorer" class="explorer-section">
    <div class="container">
      <div class="section-header">
        <span class="section-badge">Micro-Market Directory</span>
        <h2 class="section-title cinzel">Ahmedabad Real Estate Corridors</h2>
        <p class="section-desc">Browse rates, infrastructure, and growth indices across all 25+ localities.</p>
      </div>

      <div class="filters-bar">
        <div class="zone-pills">
          <button class="zone-pill active" onclick="filterLocalities('All')">All Corridors (29+)</button>
          <button class="zone-pill" onclick="filterLocalities('West')">West (SG Highway / Ambli / Bopal)</button>
          <button class="zone-pill" onclick="filterLocalities('North')">North-West & North (Vaishnodevi / Jagatpur / Tragad / Zundal)</button>
          <button class="zone-pill" onclick="filterLocalities('Central')">Central (Navrangpura / Paldi)</button>
          <button class="zone-pill" onclick="filterLocalities('East')">East (Maninagar / Nikol / Naroda)</button>
        </div>

        <div class="search-box" style="min-width: 280px;">
          <input type="text" id="locSearchInput" class="form-control" placeholder="🔍 Search locality (e.g. Shela, Bodakdev)..." oninput="searchLocalities()">
        </div>
      </div>

      <div class="locality-cards-grid" id="localityGrid">
        <!-- Locality cards populated by JS -->
      </div>
    </div>
  </section>

  <!-- Heritage & Geography Section -->
  <section id="heritage" style="padding: 80px 0; background: var(--bg-void); border-top: 1px solid var(--border);">
    <div class="container">
      <div class="section-header">
        <span class="section-badge">City Demographics</span>
        <h2 class="section-title cinzel">The Geography of Ahmedabad</h2>
        <p class="section-desc">Founded in 1411 AD • India's First UNESCO World Heritage City</p>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 32px;">
        <div class="card-panel" style="margin-top: 0;">
          <h3 class="cinzel" style="font-size: 22px; color: var(--gold-bright); margin-bottom: 12px;">
            West Ahmedabad: The High-Growth Corridor
          </h3>
          <p style="font-size: 14px; color: var(--text-muted); line-height: 1.7; margin-bottom: 16px;">
            Stretching along SG Highway, Sardar Patel Ring Road, and Sindhu Bhavan Road, West Ahmedabad is the epicenter of Gujarat's corporate, IT, and luxury residential expansion. Home to IIM-A, top healthcare institutions, premium gated communities in Shela & Ambli, and high capital appreciation rates.
          </p>
          <div style="font-size: 13px; color: var(--text-main);">
            ⭐ <strong>Key Hubs:</strong> Bodakdev, Sindhu Bhavan Road, Ambli, Thaltej, Satellite, Shela, Science City.
          </div>
        </div>

        <div class="card-panel" style="margin-top: 0;">
          <h3 class="cinzel" style="font-size: 22px; color: var(--gold-bright); margin-bottom: 12px;">
            East & Central Ahmedabad: Heritage & Industrial Hub
          </h3>
          <p style="font-size: 14px; color: var(--text-muted); line-height: 1.7; margin-bottom: 16px;">
            East of the Sabarmati River lies the historic walled city with its centuries-old Pols, the iconic Kankaria Lake, and bustling industrial hubs like Naroda & Odhav. It offers highly accessible and affordable housing with extensive connectivity via Ahmedabad Metro Line 1 and BRTS corridors.
          </p>
          <div style="font-size: 13px; color: var(--text-main);">
            ⭐ <strong>Key Hubs:</strong> Maninagar, Nikol, Naroda, Vastral, Odhav, Paldi, Ellisbridge.
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Modals -->

  <!-- 1. Sign In Modal -->
  <div class="modal-overlay" id="loginModal">
    <div class="modal-window">
      <button class="modal-close" onclick="closeModal('loginModal')">✕</button>
      <h3 class="modal-title cinzel">Sign In to Vasudha</h3>
      <p class="modal-subtitle">Access your valuation calculations and market forecasts.</p>

      <form id="loginForm" onsubmit="handleLogin(event)">
        <div class="form-group" style="margin-bottom: 16px;">
          <label class="form-label">Email or Username</label>
          <input type="text" id="loginIdent" class="form-control" required placeholder="name@example.com">
        </div>

        <div class="form-group" style="margin-bottom: 20px;">
          <label class="form-label">Password</label>
          <div class="password-wrapper">
            <input type="password" id="loginPass" class="form-control" required placeholder="••••••••">
            <button type="button" class="btn-toggle-password" onclick="togglePasswordVisibility('loginPass', this)" title="Show / Hide Password" aria-label="Toggle password">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
          </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; font-size: 13px;">
          <a href="#" style="color: var(--gold-bright); text-decoration: none;" onclick="switchModal('loginModal', 'forgotModal')">Forgot password?</a>
        </div>

        <button type="submit" class="btn btn-gold" style="width: 100%; padding: 13px;">Sign In</button>

        <p style="text-align: center; margin-top: 20px; font-size: 13px; color: var(--text-muted);">
          Don't have an account? 
          <a href="#" style="color: var(--gold-bright); font-weight: 600; text-decoration: none;" onclick="switchModal('loginModal', 'registerModal')">Create Account</a>
        </p>
      </form>
    </div>
  </div>

  <!-- 2. Create Account Modal -->
  <div class="modal-overlay" id="registerModal">
    <div class="modal-window" style="max-width: 520px;">
      <button class="modal-close" onclick="closeModal('registerModal')">✕</button>
      <h3 class="modal-title cinzel">Create Vasudha Account</h3>
      <p class="modal-subtitle">Verify with real email OTP to unlock valuation calculations.</p>

      <form id="registerForm" onsubmit="handleRegister(event)">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px;">
          <div class="form-group">
            <label class="form-label">First Name</label>
            <input type="text" id="regFirst" class="form-control" required placeholder="e.g. Aarav">
          </div>
          <div class="form-group">
            <label class="form-label">Surname</label>
            <input type="text" id="regSurname" class="form-control" required placeholder="e.g. Shah">
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1.5fr; gap: 14px; margin-bottom: 14px;">
          <div class="form-group">
            <label class="form-label">Age</label>
            <input type="number" id="regAge" class="form-control" required min="18" max="120" placeholder="e.g. 30">
          </div>
          <div class="form-group">
            <label class="form-label">Phone Number</label>
            <input type="tel" id="regPhone" class="form-control" required placeholder="e.g. 9825012345">
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 14px;">
          <label class="form-label">Email Address</label>
          <input type="email" id="regEmail" class="form-control" required placeholder="name@example.com">
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px;">
          <div class="form-group">
            <label class="form-label">Username</label>
            <input type="text" id="regUser" class="form-control" required placeholder="e.g. aarav_shah">
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <div class="password-wrapper">
              <input type="password" id="regPass" class="form-control" required minlength="6" placeholder="••••••••">
              <button type="button" class="btn-toggle-password" onclick="togglePasswordVisibility('regPass', this)" title="Show / Hide Password" aria-label="Toggle password">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <button type="submit" class="btn btn-gold" id="regSubmitBtn" style="width: 100%; padding: 13px;">
          Send Verification Code ➔
        </button>

        <p style="text-align: center; margin-top: 20px; font-size: 13px; color: var(--text-muted);">
          Already have an account? 
          <a href="#" style="color: var(--gold-bright); font-weight: 600; text-decoration: none;" onclick="switchModal('registerModal', 'loginModal')">Sign In</a>
        </p>
      </form>
    </div>
  </div>

  <!-- 3. OTP Verification Modal -->
  <div class="modal-overlay" id="otpModal">
    <div class="modal-window">
      <button class="modal-close" onclick="closeModal('otpModal')">✕</button>
      <h3 class="modal-title cinzel">Verify Email Code</h3>
      <p class="modal-subtitle">Enter the 6-digit verification code sent to <strong id="otpEmailTarget">your email</strong>.</p>

      <div id="demoOtpBox" class="demo-otp-banner" style="display: none;"></div>

      <form id="otpForm" onsubmit="handleVerifyOtp(event)">
        <div class="otp-input-row">
          <input type="text" maxlength="1" class="otp-box-digit mono" id="otp_1" oninput="handleOtpDigit(1, event)" onkeydown="handleOtpKey(1, event)">
          <input type="text" maxlength="1" class="otp-box-digit mono" id="otp_2" oninput="handleOtpDigit(2, event)" onkeydown="handleOtpKey(2, event)">
          <input type="text" maxlength="1" class="otp-box-digit mono" id="otp_3" oninput="handleOtpDigit(3, event)" onkeydown="handleOtpKey(3, event)">
          <input type="text" maxlength="1" class="otp-box-digit mono" id="otp_4" oninput="handleOtpDigit(4, event)" onkeydown="handleOtpKey(4, event)">
          <input type="text" maxlength="1" class="otp-box-digit mono" id="otp_5" oninput="handleOtpDigit(5, event)" onkeydown="handleOtpKey(5, event)">
          <input type="text" maxlength="1" class="otp-box-digit mono" id="otp_6" oninput="handleOtpDigit(6, event)" onkeydown="handleOtpKey(6, event)">
        </div>

        <button type="submit" class="btn btn-gold" style="width: 100%; padding: 13px;">
          Verify & Unlock Valuation
        </button>

        <div style="text-align: center; margin-top: 16px; font-size: 13px;">
          <a href="#" style="color: var(--gold-bright); text-decoration: none;" onclick="resendOtp()">Didn't receive code? Resend</a>
        </div>
      </form>
    </div>
  </div>

  <!-- 4. Forgot Password Modal -->
  <div class="modal-overlay" id="forgotModal">
    <div class="modal-window">
      <button class="modal-close" onclick="closeModal('forgotModal')">✕</button>
      <h3 class="modal-title cinzel">Reset Password</h3>
      <p class="modal-subtitle">Enter your registered email address to receive a password reset OTP code.</p>

      <form id="forgotForm" onsubmit="handleForgot(event)">
        <div class="form-group" style="margin-bottom: 20px;">
          <label class="form-label">Registered Email</label>
          <input type="email" id="forgotEmail" class="form-control" required placeholder="name@example.com">
        </div>

        <button type="submit" class="btn btn-gold" style="width: 100%; padding: 13px;">Send Reset OTP</button>

        <p style="text-align: center; margin-top: 18px; font-size: 13px; color: var(--text-muted);">
          Back to <a href="#" style="color: var(--gold-bright); text-decoration: none;" onclick="switchModal('forgotModal', 'loginModal')">Sign In</a>
        </p>
      </form>
    </div>
  </div>

  <!-- 5. Reset Password Final Modal -->
  <div class="modal-overlay" id="resetModal">
    <div class="modal-window">
      <button class="modal-close" onclick="closeModal('resetModal')">✕</button>
      <h3 class="modal-title cinzel">Set New Password</h3>
      <p class="modal-subtitle">Enter the 6-digit OTP code and choose a new password.</p>

      <div id="demoResetOtpBox" class="demo-otp-banner" style="display: none;"></div>

      <form id="resetForm" onsubmit="handleReset(event)">
        <div class="form-group" style="margin-bottom: 16px;">
          <label class="form-label">6-Digit Reset OTP</label>
          <input type="text" id="resetOtp" class="form-control mono" required maxlength="6" placeholder="123456">
        </div>

        <div class="form-group" style="margin-bottom: 20px;">
          <label class="form-label">New Password (min 6 characters)</label>
          <div class="password-wrapper">
            <input type="password" id="resetNewPass" class="form-control" required minlength="6" placeholder="••••••••">
            <button type="button" class="btn-toggle-password" onclick="togglePasswordVisibility('resetNewPass', this)" title="Show / Hide Password" aria-label="Toggle password">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
          </div>
        </div>

        <button type="submit" class="btn btn-gold" style="width: 100%; padding: 13px;">Update Password</button>
      </form>
    </div>
  </div>

  <!-- 6. Developer & Architecture Profile Modal -->
  <div class="modal-overlay" id="developerModal">
    <div class="modal-window" style="max-width: 500px; text-align: center;">
      <button class="modal-close" onclick="closeModal('developerModal')">✕</button>
      <div style="display: flex; justify-content: center; margin-top: 10px; margin-bottom: 12px;">
        <div class="dev-avatar-circle" style="width: 68px; height: 68px; font-size: 24px;">PO</div>
      </div>
      <h3 class="modal-title cinzel" style="font-size: 24px; color: var(--gold-bright); margin-bottom: 4px;">Patel Om</h3>
      <p style="font-size: 13px; color: var(--gold); font-weight: 600; letter-spacing: 1px; margin-bottom: 16px; text-transform: uppercase;">
        Lead System Architect & AI Full-Stack Engineer
      </p>

      <div style="margin-bottom: 18px;">
        <span class="tech-pill">Python 3.14</span>
        <span class="tech-pill">Flask REST API</span>
        <span class="tech-pill">scikit-learn (R² 0.9996)</span>
        <span class="tech-pill">SQLite Database</span>
        <span class="tech-pill">Cinematic 3D UI</span>
      </div>

      <div style="background: rgba(19, 30, 51, 0.7); border: 1px solid var(--gold); border-radius: 12px; padding: 16px; margin: 16px 0;">
        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;">Official Project & Support Email:</div>
        <a href="mailto:Vasudha.realestate.01@gmail.com" class="dev-email-link" style="font-size: 15px;">
          ✉️ Vasudha.realestate.01@gmail.com
        </a>
        <div style="margin-top: 10px;">
          <button class="btn btn-outline" style="font-size: 12px; padding: 6px 16px;" onclick="copyEmailToClipboard('Vasudha.realestate.01@gmail.com', this)">
            📋 Copy Email Address
          </button>
        </div>
      </div>

      <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
        Designed and engineered exclusively for Ahmedabad real estate price discovery and 5-year compounding forecasting.
      </p>
    </div>
  </div>

  <!-- 7. Master Admin Login Passcode Modal -->
  <div class="modal-overlay" id="adminLoginModal">
    <div class="modal-window" style="max-width: 440px;">
      <button class="modal-close" onclick="closeModal('adminLoginModal')">✕</button>
      <div style="text-align: center; margin-bottom: 16px;">
        <div style="font-size: 38px; margin-bottom: 8px;">🛡️</div>
        <h3 class="modal-title cinzel" style="color: var(--gold-bright);">Admin Authentication</h3>
        <p class="modal-subtitle" style="margin-bottom: 0;">Enter Master Admin Passcode to manage user accounts & property pricing.</p>
      </div>

      <form id="adminLoginForm" onsubmit="handleAdminLogin(event)">
        <div class="form-group" style="margin-bottom: 12px;">
          <label class="form-label">Master Passcode</label>
          <div class="password-wrapper">
            <input type="password" id="adminPasscode" class="form-control mono" required placeholder="Enter Master Passcode">
            <button type="button" class="btn-toggle-password" onclick="togglePasswordVisibility('adminPasscode', this)" title="Show / Hide Passcode">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
          </div>
        </div>

        <div style="text-align: right; margin-bottom: 18px;">
          <a href="javascript:void(0)" onclick="switchModal('adminLoginModal', 'adminForgotModal')" style="font-size: 12px; color: var(--gold); text-decoration: none;">Forgot Master Passcode?</a>
        </div>

        <button type="submit" class="btn btn-gold" style="width: 100%; padding: 13px; font-weight: 700;">
          Unlock Admin Portal
        </button>
      </form>
    </div>
  </div>

  <!-- 7a. Admin Forgot Passcode Modal -->
  <div class="modal-overlay" id="adminForgotModal">
    <div class="modal-window" style="max-width: 440px;">
      <button class="modal-close" onclick="closeModal('adminForgotModal')">✕</button>
      <div style="text-align: center; margin-bottom: 20px;">
        <div style="font-size: 38px; margin-bottom: 8px;">🔑</div>
        <h3 class="modal-title cinzel" style="color: var(--gold-bright);">Admin Passcode Recovery</h3>
        <p class="modal-subtitle">Dispatch a 6-digit authorization code to the registered administrator email to reset your master passcode.</p>
      </div>

      <form id="adminForgotForm" onsubmit="handleAdminForgotPasscode(event)">
        <button type="submit" id="adminForgotBtn" class="btn btn-gold" style="width: 100%; padding: 13px; font-weight: 700; margin-bottom: 14px;">
          Send Security OTP ➔
        </button>
      </form>

      <div style="text-align: center;">
        <a href="javascript:void(0)" onclick="switchModal('adminForgotModal', 'adminLoginModal')" style="font-size: 13px; color: var(--text-muted); text-decoration: none;">
          ← Back to Admin Login
        </a>
      </div>
    </div>
  </div>

  <!-- 7b. Admin Reset Passcode Modal -->
  <div class="modal-overlay" id="adminResetModal">
    <div class="modal-window" style="max-width: 440px;">
      <button class="modal-close" onclick="closeModal('adminResetModal')">✕</button>
      <div style="text-align: center; margin-bottom: 16px;">
        <div style="font-size: 38px; margin-bottom: 8px;">🛡️</div>
        <h3 class="modal-title cinzel" style="color: var(--gold-bright);">Update Master Passcode</h3>
        <p class="modal-subtitle">Enter the 6-digit verification code sent to administrator email and set your new passcode.</p>
      </div>

      <div id="demoAdminResetOtpBox" style="display: none; background: rgba(201, 146, 46, 0.1); border: 1px dashed var(--gold); padding: 10px 14px; border-radius: 8px; font-size: 13px; color: #F5D77F; margin-bottom: 16px; text-align: center;"></div>

      <form id="adminResetForm" onsubmit="handleAdminResetPasscode(event)">
        <div class="form-group" style="margin-bottom: 14px;">
          <label class="form-label">6-Digit Verification OTP</label>
          <input type="text" id="adminResetOtp" class="form-control mono" required maxlength="6" placeholder="123456" style="text-align: center; letter-spacing: 6px; font-size: 18px; font-weight: 700;">
        </div>

        <div class="form-group" style="margin-bottom: 20px;">
          <label class="form-label">New Master Passcode</label>
          <div class="password-wrapper">
            <input type="password" id="adminNewPasscode" class="form-control mono" required minlength="6" placeholder="Enter new admin passcode">
            <button type="button" class="btn-toggle-password" onclick="togglePasswordVisibility('adminNewPasscode', this)" title="Show / Hide Passcode">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
          </div>
        </div>

        <button type="submit" id="adminResetSubmitBtn" class="btn btn-gold" style="width: 100%; padding: 13px; font-weight: 700;">
          Update Passcode & Return to Login ➔
        </button>
      </form>
    </div>
  </div>

  <!-- 8. Master Admin Portal Modal (Users & Price Management) -->
  <div class="modal-overlay" id="adminPortalModal">
    <div class="modal-window" style="max-width: 1050px; width: 95%;">
      <button class="modal-close" onclick="closeModal('adminPortalModal')">✕</button>
      
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div style="font-size: 28px;">🛡️</div>
          <div>
            <h3 class="modal-title cinzel" style="margin: 0; color: var(--gold-bright); font-size: 22px;">Vasudha Administration Center</h3>
            <span style="font-size: 12px; color: var(--accent-green); font-weight: 600;">● Admin Session Active (SQLite Database: vasudha.db)</span>
          </div>
        </div>
        <button class="btn btn-outline" style="padding: 6px 14px; font-size: 12px;" onclick="handleAdminLogout()">Lock & Logout</button>
      </div>

      <!-- Tab Navigation -->
      <div class="admin-tab-nav">
        <button class="admin-tab-btn active" id="tabBtnUsers" onclick="switchAdminTab('users')">
          👥 Registered Users (<span id="adminUsersBadge">0</span>)
        </button>
        <button class="admin-tab-btn" id="tabBtnPrices" onclick="switchAdminTab('prices')">
          💰 Locality Price & Rates Editor (<span id="adminPricesBadge">0</span>)
        </button>
      </div>

      <!-- Tab 1: User Management -->
      <div id="adminTabUsers">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
          <input type="text" id="adminUserSearch" class="form-control" style="max-width: 320px; padding: 8px 14px; font-size: 13px;" placeholder="🔍 Search by name, username, email..." oninput="renderAdminUsersTable()">
          <span style="font-size: 12px; color: var(--text-muted);">Showing live accounts stored in SQLite database.</span>
        </div>

        <div class="admin-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Full Name</th>
                <th>Username</th>
                <th>Email Address</th>
                <th>Phone</th>
                <th>Age</th>
                <th>Registered Date</th>
                <th style="text-align: right;">Action</th>
              </tr>
            </thead>
            <tbody id="adminUsersTbody">
              <tr>
                <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading registered users...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 2: Locality Price Editor -->
      <div id="adminTabPrices" style="display: none;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
          <input type="text" id="adminPriceSearch" class="form-control" style="max-width: 320px; padding: 8px 14px; font-size: 13px;" placeholder="🔍 Search locality by name or zone..." oninput="renderAdminPricesTable()">
          <span style="font-size: 12px; color: var(--gold-bright);">💡 Tip: Click 'Edit Rate' to change flat/tenement rates manually in the database.</span>
        </div>

        <div class="admin-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Locality</th>
                <th>Zone</th>
                <th>Tier</th>
                <th>Flat Rate (₹/sqft)</th>
                <th>Flat Rate (₹/sqyd)</th>
                <th>Tenement Rate (₹/sqft)</th>
                <th>YoY Growth</th>
                <th>Livability</th>
                <th style="text-align: right;">Action</th>
              </tr>
            </thead>
            <tbody id="adminPricesTbody">
              <tr>
                <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading locality rates...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- 9. Edit Locality Price Modal -->
  <div class="modal-overlay" id="adminEditPriceModal">
    <div class="modal-window" style="max-width: 480px;">
      <button class="modal-close" onclick="closeModal('adminEditPriceModal')">✕</button>
      <h3 class="modal-title cinzel" style="color: var(--gold-bright); margin-bottom: 4px;">Edit Locality Pricing</h3>
      <p class="modal-subtitle">Manually set market rates for Ahmedabad micro-market.</p>

      <form id="adminEditPriceForm" onsubmit="handleSaveLocalityPrice(event)">
        <div class="form-group" style="margin-bottom: 14px;">
          <label class="form-label">Locality Name</label>
          <input type="text" id="editLocName" class="form-control" readonly style="background: rgba(11, 18, 32, 0.9); font-weight: 700; color: var(--gold-bright);">
        </div>

        <div class="form-group" style="margin-bottom: 14px;">
          <label class="form-label">Base Flat Rate (₹ / sq.ft)</label>
          <input type="number" id="editLocRateSqft" class="form-control mono" required min="100" max="200000" oninput="updateEditPriceCalculations()">
        </div>

        <div style="background: rgba(19, 30, 51, 0.7); border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 14px;">
          <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px;">
            <span style="color: var(--text-muted);">Flat Rate (₹ / sq.yd):</span>
            <strong id="previewRateSqyd" style="color: var(--gold-bright);">₹0</strong>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 13px;">
            <span style="color: var(--text-muted);">Tenement / Duplex (1.28x):</span>
            <strong id="previewRateTenement" style="color: var(--accent-cyan);">₹0 / sq.ft</strong>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
          <div class="form-group">
            <label class="form-label">YoY Growth (%)</label>
            <input type="number" id="editLocYoy" class="form-control mono" step="0.1" min="0" max="100">
          </div>
          <div class="form-group">
            <label class="form-label">Livability Score (0-10)</label>
            <input type="number" id="editLocLivability" class="form-control mono" step="0.1" min="0" max="10">
          </div>
        </div>

        <button type="submit" class="btn btn-gold" id="savePriceBtn" style="width: 100%; padding: 12px; font-weight: 700;">
          Save Price Update
        </button>
      </form>
    </div>
  </div>

  <!-- 10. Share Valuation via Email Modal -->
  <div class="modal-overlay" id="shareEmailModal">
    <div class="modal-window" style="max-width: 500px;">
      <button class="modal-close" onclick="closeModal('shareEmailModal')">✕</button>
      <div style="text-align: center; margin-bottom: 16px;">
        <div style="font-size: 38px; margin-bottom: 8px;">✉️</div>
        <h3 class="modal-title cinzel" style="color: var(--gold-bright); font-size: 22px;">Share Price Valuation</h3>
        <p class="modal-subtitle" style="margin-bottom: 0;">Send this valuation summary directly to any email address.</p>
      </div>

      <!-- Quick Summary Preview Card -->
      <div style="background: rgba(19, 30, 51, 0.7); border: 1px solid rgba(201, 146, 46, 0.3); border-radius: 10px; padding: 14px 16px; margin-bottom: 18px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; color: var(--text-muted);">Selected Area:</span>
          <strong id="sharePreviewLocality" style="color: var(--gold-bright); font-size: 14px;">Bodakdev</strong>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; color: var(--text-muted);">Calculated Size:</span>
          <strong id="sharePreviewArea" class="mono" style="color: var(--text-main); font-size: 13px;">150 Sq. Yards (Gaj)</strong>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; color: var(--text-muted);">Calculated Price:</span>
          <strong id="sharePreviewPrice" class="mono" style="color: var(--gold-bright); font-size: 16px;">₹1.24 Cr</strong>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 11px; color: var(--text-dim);">Calculation Timestamp:</span>
          <span id="sharePreviewTime" class="mono" style="font-size: 11px; color: var(--text-dim);">Just now</span>
        </div>
      </div>

      <form id="shareEmailForm" onsubmit="handleSendShareEmail(event)">
        <div class="form-group" style="margin-bottom: 16px;">
          <label class="form-label">Recipient Email Address</label>
          <input type="email" id="shareRecipientEmail" class="form-control" required placeholder="recipient@example.com">
        </div>

        <div style="background: rgba(201, 146, 46, 0.08); border-left: 3px solid var(--gold); border-radius: 6px; padding: 10px 12px; margin-bottom: 20px; font-size: 11px; color: var(--text-muted); line-height: 1.5;">
          ⚠️ <strong>Disclaimer:</strong> The dispatched email contains an explicit disclaimer that the estimated price is approximate, along with the selected area, calculated size in sq. yards, price, and date & time of calculation.
        </div>

        <button type="submit" id="btnSendShareEmail" class="btn btn-gold" style="width: 100%; padding: 13px; font-weight: 700; font-size: 15px;">
          Send Valuation Report ➔
        </button>
      </form>
    </div>
  </div>

  <!-- Footer -->
  <footer class="footer">
    <div class="container">
      
      <!-- Animated Developer Showcase Card -->
      <div class="footer-dev-card">
        <div class="footer-dev-left">
          <div class="dev-avatar-circle">PO</div>
          <div>
            <div style="font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--gold-bright); font-weight: 700;">
              ENGINEERED & ARCHITECTED BY
            </div>
            <div class="cinzel" style="font-size: 20px; font-weight: 900; color: #FFFFFF; letter-spacing: 1px; margin: 2px 0;">
              Patel Om
            </div>
            <div style="font-size: 13px; color: var(--text-muted);">
              Lead AI & Full-Stack System Developer
            </div>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">
          <a href="mailto:Vasudha.realestate.01@gmail.com" class="dev-email-link">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
            Vasudha.realestate.01@gmail.com
          </a>
          <button class="btn btn-outline" style="padding: 6px 14px; font-size: 12px;" onclick="copyEmailToClipboard('Vasudha.realestate.01@gmail.com', this)">
            📋 Copy Email
          </button>
        </div>
      </div>
    </div>

    <div class="container footer-grid">
      <div>
        <div class="brand" style="margin-bottom: 16px;">
          <div class="brand-vr-icon">
            <svg viewBox="0 0 100 90" width="32" height="28" fill="none">
              <polygon points="15,20 28,20 44,65 34,65" fill="#F5D77F"/>
              <polygon points="45,18 52,14 52,65 45,65" fill="#131E33"/>
              <polygon points="52,14 58,18 58,65 52,65" fill="#C9922E"/>
              <path d="M60,22 L72,22 C82,22 86,30 86,40 C86,50 78,56 68,56 L60,56" stroke="#38BDF8" stroke-width="7"/>
              <path d="M68,54 L84,72" stroke="#F5D77F" stroke-width="7" stroke-linecap="round"/>
              <path d="M10,75 Q 50,68 90,75" stroke="#C9922E" stroke-width="3" stroke-linecap="round"/>
            </svg>
          </div>
          <div>
            <div class="brand-title cinzel">VASUDHA</div>
            <div class="brand-subtitle">REAL ESTATE</div>
          </div>
        </div>
        <p style="font-size: 13px; color: var(--text-muted); max-width: 320px; line-height: 1.6;">
          Dedicated property valuation, historical appreciation analysis, and micro-market intelligence platform for Ahmedabad, Gujarat.
        </p>
      </div>

      <div>
        <h4 style="font-size: 14px; color: var(--gold-bright); margin-bottom: 16px; text-transform: uppercase;">Corridors</h4>
        <ul style="list-style: none; font-size: 13px; color: var(--text-muted); line-height: 2;">
          <li>Bodakdev & Ambli</li>
          <li>Sindhu Bhavan Road</li>
          <li>Shela & South Bopal</li>
          <li>Thaltej & Satellite</li>
        </ul>
      </div>

      <div>
        <h4 style="font-size: 14px; color: var(--gold-bright); margin-bottom: 16px; text-transform: uppercase;">Platform</h4>
        <ul style="list-style: none; font-size: 13px; color: var(--text-muted); line-height: 2;">
          <li>ML Regression Engine</li>
          <li>Historical Trends (2020-26)</li>
          <li>5-Year Price Projections</li>
          <li>Land & Duplex Multipliers</li>
        </ul>
      </div>

      <div>
        <h4 style="font-size: 14px; color: var(--gold-bright); margin-bottom: 16px; text-transform: uppercase;">Ahmedabad Heritage</h4>
        <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
          Founded 1411 AD<br>
          Sabarmati Riverfront<br>
          UNESCO World Heritage
        </p>
      </div>
    </div>

    <div class="container footer-bottom">
      <div>
        © 2026 Vasudha Real Estate Platform. All rights reserved. • Contact: <a href="mailto:Vasudha.realestate.01@gmail.com" style="color: var(--gold); text-decoration: none;">Vasudha.realestate.01@gmail.com</a>
        <span style="margin: 0 8px; opacity: 0.4;">|</span>
        <a href="javascript:void(0)" onclick="openAdminPortal()" style="color: var(--text-dim); text-decoration: none; font-size: 12px; transition: color 0.2s;" onmouseover="this.style.color='var(--gold-bright)'" onmouseout="this.style.color='var(--text-dim)'" title="Restricted Access">🛡️ Admin Portal</a>
      </div>
      <div class="mono" style="font-size: 12px; color: var(--gold);">scikit-learn ML Model v2.4 (R² = 0.9996)</div>
    </div>
  </footer>

  <!-- Siri-Style Voice Assistant Floating Orb -->
  <div class="siri-orb-widget" id="siriOrbWidget" onclick="triggerAssistantGreeting(true)" title="Vasudha Voice Assistant (Click to listen)">
    <div class="siri-orb"></div>
    <div class="siri-label">
      <span class="siri-title" id="siriTitleText">Vasudha Assistant</span>
      <span class="siri-sub" id="siriSubText">Click to listen</span>
    </div>
  </div>

  <!-- Frontend JavaScript Logic -->
  <script>
    // State
    let currentPropertyType = 'Apartment / Flat';
    let allLocalities = [];
    let pendingEmail = '';
    let isVaultUnlocked = false;

    // =========================================================================
    // Siri-Style MALE Voice Greeting & Cinematic Splash Controller (English Only)
    // =========================================================================
    let hasPlayedWelcomeGreeting = false;
    let isAssistantSpeaking = false;
    let splashDismissTimer = null;

    function getGreetingMessage() {
      const now = new Date();
      const hour = now.getHours();
      let timeGreeting = "Good morning";
      if (hour >= 12 && hour < 17) {
        timeGreeting = "Good afternoon";
      } else if (hour >= 17 || hour < 5) {
        timeGreeting = "Good evening";
      }
      return `${timeGreeting}! Vasudha Real Estate — Your dream home starts here.`;
    }

    function getBestAssistantVoice() {
      if (!('speechSynthesis' in window)) return null;
      const voices = window.speechSynthesis.getVoices();
      
      // Look for distinguished, natural MALE English voices
      const maleVoice = voices.find(v => 
        (v.lang.startsWith('en') && (
          v.name.includes('David') ||
          v.name.includes('Alex') ||
          v.name.includes('Daniel') ||
          v.name.includes('George') ||
          v.name.includes('Rishi') ||
          v.name.includes('Oliver') ||
          v.name.includes('Google US English Male') ||
          v.name.includes('Male') ||
          v.name.includes('Guy')
        ))
      );
      if (maleVoice) return maleVoice;

      // Fallback: any standard English voice
      const standardEn = voices.find(v => v.lang.startsWith('en') && !v.name.includes('Zira') && !v.name.includes('Samantha'));
      return standardEn || voices.find(v => v.lang.startsWith('en')) || null;
    }

    function speakAssistantPhrase(phrase, onComplete) {
      if (!('speechSynthesis' in window)) {
        if (onComplete) onComplete();
        return;
      }

      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(phrase);
      utterance.lang = 'en-US';
      utterance.rate = 0.98;
      utterance.pitch = 0.92; // Deep, clear executive male tone

      const voice = getBestAssistantVoice();
      if (voice) utterance.voice = voice;

      const widget = document.getElementById('siriOrbWidget');
      const subText = document.getElementById('siriSubText');

      utterance.onstart = function() {
        isAssistantSpeaking = true;
        if (widget) widget.classList.add('is-speaking');
        if (subText) subText.textContent = 'Speaking...';
      };

      utterance.onend = function() {
        isAssistantSpeaking = false;
        if (widget) widget.classList.remove('is-speaking');
        if (subText) subText.textContent = 'Click to listen';
        if (onComplete) onComplete();
      };

      utterance.onerror = function() {
        isAssistantSpeaking = false;
        if (widget) widget.classList.remove('is-speaking');
        if (subText) subText.textContent = 'Click to listen';
        if (onComplete) onComplete();
      };

      window.speechSynthesis.speak(utterance);
    }

    function triggerAssistantGreeting(manualClick = false) {
      if (!manualClick && hasPlayedWelcomeGreeting) return;
      hasPlayedWelcomeGreeting = true;
      sessionStorage.setItem('vasudha_greeted', '1');
      const greeting = getGreetingMessage();
      speakAssistantPhrase(greeting);
    }

    function speakAssistantLogout(callback) {
      const farewell = "Thank you for using Vasudha Real Estate. Come again soon!";
      let completed = false;
      
      const done = () => {
        if (!completed) {
          completed = true;
          if (callback) callback();
        }
      };

      speakAssistantPhrase(farewell, done);
      setTimeout(done, 2600);
    }

    async function handleUserLogout(e) {
      if (e) e.preventDefault();
      speakAssistantLogout(() => {
        window.location.href = '/api/auth/logout';
      });
    }

    // Cinematic 4-Second Splash Controller
    function dismissCinematicSplash() {
      const splash = document.getElementById('cinematicSplash');
      if (splash) {
        splash.classList.add('is-hidden');
        setTimeout(() => {
          splash.style.display = 'none';
        }, 700);
      }
      if (splashDismissTimer) {
        clearTimeout(splashDismissTimer);
        splashDismissTimer = null;
      }
    }

    function initCinematicIntro() {
      const splash = document.getElementById('cinematicSplash');
      if (!splash) return;

      // Auto dismiss after 4 seconds (4000ms)
      splashDismissTimer = setTimeout(() => {
        dismissCinematicSplash();
      }, 4000);

      // Play male voice greeting once on entry
      if (!sessionStorage.getItem('vasudha_greeted')) {
        setTimeout(() => {
          triggerAssistantGreeting(false);
        }, 600);
      }
    }

    // Initialize splash on load
    window.addEventListener('DOMContentLoaded', () => {
      initCinematicIntro();
    });

    // Auto-trigger voice greeting on first user interaction anywhere on the page if not yet spoken
    document.addEventListener('click', function onFirstUserClick() {
      if (!hasPlayedWelcomeGreeting) {
        triggerAssistantGreeting(false);
      }
    }, { once: true });

    // Typewriter Phrases
    const phrases = [
      "Precision Property Valuation for Ahmedabad",
      "AI-Powered 5-Year Price Appreciation Projections",
      "Real Historical Trends Across 25+ Micro-Markets",
      "Flats, Apartments, Tenements & Duplex Valuations"
    ];
    let pIdx = 0, cIdx = 0, isDel = false;

    // Ambient mouse tracking
    document.addEventListener('mousemove', (e) => {
      const blob = document.getElementById('glowBlob');
      if (blob) {
        blob.style.left = e.clientX + 'px';
        blob.style.top = e.clientY + 'px';
      }
    });

    // 3D Vault Breakout Toggle
    function triggerVaultBreakout() {
      const hero = document.getElementById('vaultHero');
      if (isVaultUnlocked) {
        hero.classList.remove('is-unlocked');
        isVaultUnlocked = false;
      } else {
        hero.classList.add('is-unlocked');
        isVaultUnlocked = true;
        if (!hasPlayedWelcomeGreeting) {
          setTimeout(() => triggerAssistantGreeting(false), 500);
        }
      }
    }

    // Init
    document.addEventListener('DOMContentLoaded', () => {
      fetchLocalities();
      startHeroTypewriter();
      
      // Auto-trigger vault breakout on scroll
      window.addEventListener('scroll', () => {
        if (window.scrollY > 30 && !isVaultUnlocked) {
          triggerVaultBreakout();
        }
      });
    });

    // Dynamic Typewriter
    function startHeroTypewriter() {
      const el = document.getElementById('heroTypewriterText');
      if (!el) return;

      const currentPhrase = phrases[pIdx];

      if (isDel) {
        el.textContent = currentPhrase.substring(0, cIdx - 1);
        cIdx--;
      } else {
        el.textContent = currentPhrase.substring(0, cIdx + 1);
        cIdx++;
      }

      let speed = isDel ? 25 : 60;

      if (!isDel && cIdx === currentPhrase.length) {
        speed = 2200;
        isDel = true;
      } else if (isDel && cIdx === 0) {
        isDel = false;
        pIdx = (pIdx + 1) % phrases.length;
        speed = 350;
      }

      setTimeout(startHeroTypewriter, speed);
    }

    // Property Type Switcher
    function selectPropertyType(type) {
      currentPropertyType = type;
      document.getElementById('typeFlat').classList.toggle('active', type === 'Apartment / Flat');
      document.getElementById('typeTenement').classList.toggle('active', type === 'Tenement / Duplex');
      
      const locality = document.getElementById('calcLocality').value;
      if (locality && document.getElementById('resultsContainer').style.display === 'block') {
        calculateValuation();
      }
    }

    // Fetch localities from API
    async function fetchLocalities() {
      try {
        const res = await fetch('/api/localities');
        const data = await res.json();
        if (data.success) {
          allLocalities = data.localities;
          populateLocalitySelect(allLocalities);
          renderLocalityGrid(allLocalities);
        }
      } catch (err) {
        console.error('Failed to load localities:', err);
      }
    }

    function populateLocalitySelect(localities) {
      const select = document.getElementById('calcLocality');
      select.innerHTML = '<option value="" disabled selected>Select an Ahmedabad Locality...</option>';
      
      // Preferred zone ordering
      const preferredZones = ['West', 'North-West', 'North', 'Central', 'East'];
      const rawZones = Array.from(new Set(localities.map(l => l.zone)));
      const allZones = [...preferredZones.filter(z => rawZones.includes(z)), ...rawZones.filter(z => !preferredZones.includes(z))];

      allZones.forEach(zone => {
        const zoneLocs = localities.filter(l => (l.zone || '').toLowerCase() === zone.toLowerCase());
        if (zoneLocs.length > 0) {
          const group = document.createElement('optgroup');
          group.label = `${zone} Ahmedabad (${zoneLocs.length} Localities)`;
          zoneLocs.forEach(loc => {
            const opt = document.createElement('option');
            opt.value = loc.name;
            opt.textContent = `${loc.name} (${loc.tier}) — ₹${Number(loc.rate_per_sqyd).toLocaleString('en-IN')}/sq.yd`;
            group.appendChild(opt);
          });
          select.appendChild(group);
        }
      });
    }

    function renderLocalityGrid(localities) {
      const grid = document.getElementById('localityGrid');
      grid.innerHTML = '';

      localities.forEach(loc => {
        const card = document.createElement('div');
        card.className = 'loc-card';
        card.onclick = () => selectLocalityForValuation(loc.name);

        card.innerHTML = `
          <div>
            <div class="loc-header" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
              <div class="loc-name">${loc.name}</div>
              <span class="loc-tier-badge">${loc.tier}</span>
            </div>
            <div class="loc-rate-highlight mono">₹${Number(loc.rate_per_sqyd).toLocaleString('en-IN')}<span style="font-size: 12px; color: var(--text-muted); font-weight: normal;"> / sq.yd (Gaj)</span></div>
            <div style="font-size: 12px; color: var(--accent-green); margin-bottom: 8px;">📈 ${loc.yoy_percent}% YoY Growth</div>
            <p class="loc-note-preview">${loc.note || 'Prime residential sector.'}</p>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid var(--border); font-size: 12px; color: var(--gold-bright);">
            <span>Zone: ${loc.zone}</span>
            <span>Est: ₹${Number(loc.rate_per_sqft).toLocaleString('en-IN')}/sq.ft ➔</span>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    function selectLocalityForValuation(localityName) {
      const select = document.getElementById('calcLocality');
      select.value = localityName;
      document.getElementById('valuation').scrollIntoView({ behavior: 'smooth' });
    }

    function filterLocalities(zone) {
      document.querySelectorAll('.zone-pill').forEach(p => p.classList.remove('active'));
      event.target.classList.add('active');

      if (zone === 'All') {
        renderLocalityGrid(allLocalities);
      } else if (zone === 'North') {
        const filtered = allLocalities.filter(l => (l.zone === 'North-West' || l.zone === 'North'));
        renderLocalityGrid(filtered);
      } else {
        const filtered = allLocalities.filter(l => l.zone === zone);
        renderLocalityGrid(filtered);
      }
    }

    function searchLocalities() {
      const q = document.getElementById('locSearchInput').value.toLowerCase().trim();
      const filtered = allLocalities.filter(l => 
        l.name.toLowerCase().includes(q) || 
        l.zone.toLowerCase().includes(q) ||
        l.tier.toLowerCase().includes(q) ||
        (l.landmarks && l.landmarks.toLowerCase().includes(q))
      );
      renderLocalityGrid(filtered);
    }

    // Valuation Calculator
    async function calculateValuation() {
      const locality = document.getElementById('calcLocality').value;
      const area = document.getElementById('calcArea').value;

      if (!locality) {
        alert('Please select an Ahmedabad locality.');
        return;
      }
      if (!area || area <= 0) {
        alert('Please enter a valid property area.');
        return;
      }

      const btn = document.getElementById('calcBtn');
      btn.textContent = 'Calculating Model...';
      btn.disabled = true;

      try {
        const res = await fetch('/api/estimate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            locality: locality,
            area: Number(area),
            property_type: currentPropertyType
          })
        });

        const data = await res.json();

        // If user is not logged in -> show auth gate notice
        if (res.status === 401 || data.requires_auth) {
          document.getElementById('resultsContainer').style.display = 'none';
          document.getElementById('authGateBox').style.display = 'block';
          document.getElementById('authGateBox').scrollIntoView({ behavior: 'smooth', block: 'center' });
          return;
        }

        if (!data.success) {
          alert(data.error || 'Valuation failed');
          return;
        }

        document.getElementById('authGateBox').style.display = 'none';
        displayValuationResults(data);
      } catch (err) {
        console.error(err);
        alert('Error connecting to valuation service.');
      } finally {
        btn.textContent = 'Calculate Valuation ➔';
        btn.disabled = false;
      }
    }

    // Bilingual Speech Synthesis & Price Context Intelligence
    let currentValuationData = null;
    let currentTtsLang = 'en'; // 'en' (English) or 'hi' (Hindi Devanagari)
    let isSpeaking = false;

    function setTtsLanguage(lang) {
      currentTtsLang = lang;
      const btnEn = document.getElementById('ttsLangEn');
      const btnHi = document.getElementById('ttsLangHi');
      if (btnEn && btnHi) {
        if (lang === 'en') {
          btnEn.classList.add('active');
          btnHi.classList.remove('active');
        } else {
          btnHi.classList.add('active');
          btnEn.classList.remove('active');
        }
      }
      if (isSpeaking) {
        stopPriceSpeech();
        togglePriceSpeech();
      }
    }

    function stopPriceSpeech() {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      isSpeaking = false;
      const btn = document.getElementById('ttsSpeakBtn');
      const icon = document.getElementById('ttsIcon');
      const text = document.getElementById('ttsBtnText');
      const wave = document.getElementById('audioWaveAnim');
      if (btn) {
        btn.classList.remove('is-playing');
        icon.textContent = '🔊';
        text.textContent = 'Speak Rationale';
        wave.style.display = 'none';
      }
    }

    function togglePriceSpeech() {
      if (!('speechSynthesis' in window)) {
        alert('Voice text-to-speech is not supported by your current browser.');
        return;
      }

      if (isSpeaking) {
        stopPriceSpeech();
        return;
      }

      if (!currentValuationData) return;

      const textToSpeak = (currentTtsLang === 'hi' && currentValuationData.price_explanation_hi)
        ? currentValuationData.price_explanation_hi
        : (currentValuationData.price_explanation_en || 'No explanation available.');

      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      utterance.rate = currentTtsLang === 'hi' ? 0.95 : 1.0;
      utterance.pitch = 1.0;

      // Select appropriate voice if available
      const voices = window.speechSynthesis.getVoices();
      if (currentTtsLang === 'hi') {
        const hiVoice = voices.find(v => v.lang.includes('hi') || v.name.toLowerCase().includes('hindi'));
        if (hiVoice) utterance.voice = hiVoice;
        utterance.lang = 'hi-IN';
      } else {
        const enVoice = voices.find(v => (v.lang === 'en-IN' || v.lang === 'en-GB' || v.lang === 'en-US') && !v.name.toLowerCase().includes('david'));
        if (enVoice) utterance.voice = enVoice;
        utterance.lang = 'en-IN';
      }

      const btn = document.getElementById('ttsSpeakBtn');
      const icon = document.getElementById('ttsIcon');
      const txtSpan = document.getElementById('ttsBtnText');
      const wave = document.getElementById('audioWaveAnim');

      utterance.onstart = function() {
        isSpeaking = true;
        if (btn) {
          btn.classList.add('is-playing');
          icon.textContent = '⏹️';
          txtSpan.textContent = currentTtsLang === 'hi' ? 'Speaking (Hindi)...' : 'Speaking (English)...';
          wave.style.display = 'inline-flex';
        }
      };

      utterance.onend = function() {
        stopPriceSpeech();
      };

      utterance.onerror = function() {
        stopPriceSpeech();
      };

      window.speechSynthesis.speak(utterance);
    }

    function displayValuationResults(data) {
      currentValuationData = data;
      stopPriceSpeech();

      const container = document.getElementById('resultsContainer');
      container.style.display = 'block';

      // Update Top Hero Card
      document.getElementById('resGrowthBadge').textContent = data.growth_badge;
      document.getElementById('resLocHeading').textContent = `${data.locality.toUpperCase()} • ${data.property_type.toUpperCase()}`;
      document.getElementById('resMainPrice').textContent = data.total_price_formatted;
      document.getElementById('resFullPrice').textContent = `Total Estimated Market Value: ${data.total_price_full} (INR)`;
      document.getElementById('resRateSqyd').textContent = data.rate_per_sqyd_formatted;
      document.getElementById('resRateSqft').textContent = data.rate_per_sqft_formatted;
      document.getElementById('resZoneTier').textContent = `${data.zone} Zone • ${data.tier}`;
      document.getElementById('resLivability').textContent = `${data.livability_score} / 10`;

      // Area Price Context Intelligence Card (On-Screen English only)
      document.getElementById('priceContextLocalityTag').textContent = data.locality;
      document.getElementById('priceExplanationTextEn').textContent = data.price_explanation_en || 'Standard market valuation applies.';

      // Key Pricing Drivers Tags
      const driversBox = document.getElementById('priceDriversTags');
      if (driversBox) {
        driversBox.innerHTML = '';
        (data.price_drivers || []).forEach(d => {
          const tag = document.createElement('span');
          tag.className = 'info-tag';
          tag.style.background = 'rgba(201, 146, 46, 0.12)';
          tag.style.borderColor = 'rgba(201, 146, 46, 0.4)';
          tag.style.color = '#F5D77F';
          tag.textContent = `⚡ ${d}`;
          driversBox.appendChild(tag);
        });
      }

      // Render Historical Chart
      renderHistoricalChart(data.historical_trends);

      // Render 5-Year Projections Table
      const tbody = document.getElementById('projTableBody');
      tbody.innerHTML = '';
      data.five_year_projections.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${p.year_label}</strong></td>
          <td class="mono">${p.rate_per_sqyd_formatted}</td>
          <td class="mono">${p.rate_per_sqft_formatted}</td>
          <td class="mono" style="color: var(--gold-bright); font-weight: 700;">${p.estimated_value_formatted}</td>
          <td class="mono" style="color: var(--accent-green);">+${p.gain_percent}% (+${Number(p.gain_from_current).toLocaleString('en-IN', {maximumFractionDigits: 0})})</td>
        `;
        tbody.appendChild(tr);
      });

      if (data.five_year_projections.length > 0) {
        const lastP = data.five_year_projections[data.five_year_projections.length - 1];
        document.getElementById('res5yrGain').textContent = `+${lastP.gain_percent}% Total 5-Yr Growth`;
      }

      // Locality Intelligence
      const intel = data.locality_intelligence;
      document.getElementById('intelTitle').textContent = `${data.locality} Locality Infrastructure & Growth Drivers`;
      document.getElementById('intelSource').textContent = intel.data_source;
      document.getElementById('intelOverview').textContent = intel.note;

      const lmContainer = document.getElementById('intelLandmarks');
      lmContainer.innerHTML = '';
      (intel.landmarks || []).forEach(lm => {
        const span = document.createElement('span');
        span.className = 'info-tag';
        span.textContent = lm;
        lmContainer.appendChild(span);
      });

      const scContainer = document.getElementById('intelSchools');
      scContainer.innerHTML = '';
      (intel.schools_hospitals || []).forEach(sc => {
        const span = document.createElement('span');
        span.className = 'info-tag';
        span.textContent = sc;
        scContainer.appendChild(span);
      });

      document.getElementById('intelTransit').textContent = intel.transit;

      container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // =========================================================================
    // Share Calculation via Email Controller
    // =========================================================================
    function openShareValuationModal() {
      if (!currentValuationData) {
        alert('Please calculate a property valuation first.');
        return;
      }

      const loc = currentValuationData.locality || 'Ahmedabad';
      const propType = currentValuationData.property_type || currentPropertyType;
      const areaVal = currentValuationData.area_sqyd || document.getElementById('calcArea').value || 150;
      const priceFmt = currentValuationData.total_price_formatted || document.getElementById('resMainPrice').textContent;

      document.getElementById('sharePreviewLocality').textContent = `${loc} (${propType})`;
      document.getElementById('sharePreviewArea').textContent = `${Number(areaVal).toLocaleString('en-IN')} Sq. Yards (Gaj)`;
      document.getElementById('sharePreviewPrice').textContent = priceFmt;

      const now = new Date();
      const timeStr = now.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) + ', ' +
                      now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
      document.getElementById('sharePreviewTime').textContent = timeStr;

      const emailInput = document.getElementById('shareRecipientEmail');
      // Pre-fill user email if authenticated
      fetch('/api/auth/me')
        .then(res => res.json())
        .then(authData => {
          if (authData.authenticated && authData.user && authData.user.email && !emailInput.value) {
            emailInput.value = authData.user.email;
          }
        })
        .catch(() => {});

      openModal('shareEmailModal');
      setTimeout(() => {
        if (emailInput) emailInput.focus();
      }, 200);
    }

    async function handleSendShareEmail(event) {
      event.preventDefault();
      if (!currentValuationData) {
        alert('Please calculate a valuation first.');
        return;
      }

      const emailInput = document.getElementById('shareRecipientEmail');
      const recipientEmail = emailInput ? emailInput.value.trim() : '';
      if (!recipientEmail) {
        alert('Please enter a valid recipient email address.');
        return;
      }

      const btn = document.getElementById('btnSendShareEmail');
      const origText = btn.innerHTML;
      btn.textContent = 'Dispatching Valuation Report...';
      btn.disabled = true;

      try {
        const payload = {
          email: recipientEmail,
          locality: currentValuationData.locality,
          property_type: currentValuationData.property_type,
          area_sqyd: currentValuationData.area_sqyd,
          area_sqft: currentValuationData.area_sqft,
          total_price: currentValuationData.total_price,
          total_price_formatted: currentValuationData.total_price_formatted,
          total_price_full: currentValuationData.total_price_full,
          rate_per_sqyd_formatted: currentValuationData.rate_per_sqyd_formatted,
          rate_per_sqft_formatted: currentValuationData.rate_per_sqft_formatted,
          zone: currentValuationData.zone,
          tier: currentValuationData.tier,
          calculated_at: document.getElementById('sharePreviewTime').textContent
        };

        const res = await fetch('/api/share-calculation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
          closeModal('shareEmailModal');
          alert(`✉️ Valuation report successfully sent to ${recipientEmail}!`);
        } else {
          alert(`⚠️ ${data.error || 'Failed to dispatch email.'}`);
        }
      } catch (err) {
        console.error('Error sharing calculation via email:', err);
        alert('Network error while attempting to send valuation report.');
      } finally {
        btn.innerHTML = origText;
        btn.disabled = false;
      }
    }

    // SVG Chart Renderer
    function renderHistoricalChart(trendData) {
      const svg = document.getElementById('trendSvg');
      const points = trendData.points || [];
      if (points.length === 0) return;

      const padding = { top: 20, right: 30, bottom: 30, left: 50 };
      const width = 420;
      const height = 200;

      const rates = points.map(p => p.rate_per_sqft);
      const minRate = Math.min(...rates) * 0.9;
      const maxRate = Math.max(...rates) * 1.1;

      const minYear = points[0].year;
      const maxYear = points[points.length - 1].year;
      const yearSpan = (maxYear - minYear) || 1;

      const getX = (yr) => padding.left + ((yr - minYear) / yearSpan) * (width - padding.left - padding.right);
      const getY = (rate) => height - padding.bottom - ((rate - minRate) / (maxRate - minRate)) * (height - padding.top - padding.bottom);

      let pathD = '';
      let areaD = `M ${getX(points[0].year)} ${height - padding.bottom}`;

      points.forEach((p, idx) => {
        const x = getX(p.year);
        const y = getY(p.rate_per_sqft);
        if (idx === 0) pathD += `M ${x} ${y}`;
        else pathD += ` L ${x} ${y}`;
        areaD += ` L ${x} ${y}`;
      });

      areaD += ` L ${getX(points[points.length - 1].year)} ${height - padding.bottom} Z`;

      let svgHtml = `
        <defs>
          <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#C9922E" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#C9922E" stop-opacity="0.0"/>
          </linearGradient>
        </defs>
        <line x1="${padding.left}" y1="${getY(minRate * 1.05)}" x2="${width - padding.right}" y2="${getY(minRate * 1.05)}" stroke="#18263F" stroke-dasharray="2 2"/>
        <line x1="${padding.left}" y1="${getY((minRate + maxRate) / 2)}" x2="${width - padding.right}" y2="${getY((minRate + maxRate) / 2)}" stroke="#18263F" stroke-dasharray="2 2"/>
        <line x1="${padding.left}" y1="${getY(maxRate * 0.95)}" x2="${width - padding.right}" y2="${getY(maxRate * 0.95)}" stroke="#18263F" stroke-dasharray="2 2"/>
        <path d="${areaD}" fill="url(#chartGrad)"/>
        <path d="${pathD}" fill="none" stroke="#D4AF37" stroke-width="3"/>
      `;

      points.forEach(p => {
        const x = getX(p.year);
        const y = getY(p.rate_per_sqft);
        svgHtml += `
          <circle cx="${x}" cy="${y}" r="4.5" fill="#F5D77F" stroke="#060B14" stroke-width="2"/>
          <text x="${x}" y="${height - 10}" fill="#94A3B8" font-size="10" font-family="JetBrains Mono" text-anchor="middle">${p.year}</text>
          <text x="${x}" y="${y - 8}" fill="#F8FAFC" font-size="10" font-family="JetBrains Mono" font-weight="bold" text-anchor="middle">₹${Math.round(p.rate_per_sqft)}</text>
        `;
      });

      svg.innerHTML = svgHtml;
    }

    // Modal Handlers
    function openModal(id) {
      document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active'));
      const target = document.getElementById(id);
      if (target) target.classList.add('active');
    }

    function closeModal(id) {
      const target = document.getElementById(id);
      if (target) target.classList.remove('active');
    }

    function switchModal(closeId, openId) {
      closeModal(closeId);
      openModal(openId);
    }

    // OTP 6-Box Input Helper
    function handleOtpDigit(index, e) {
      const val = e.target.value;
      if (val && index < 6) {
        document.getElementById(`otp_${index + 1}`).focus();
      }
    }

    function handleOtpKey(index, e) {
      if (e.key === 'Backspace' && !e.target.value && index > 1) {
        document.getElementById(`otp_${index - 1}`).focus();
      }
    }

    function getEnteredOtp() {
      let code = '';
      for (let i = 1; i <= 6; i++) {
        code += document.getElementById(`otp_${i}`).value;
      }
      return code;
    }

    function setEnteredOtp(code) {
      const str = String(code).trim();
      for (let i = 1; i <= 6; i++) {
        const box = document.getElementById(`otp_${i}`);
        if (box) box.value = str[i - 1] || '';
      }
    }

    // Auth Actions
    async function handleLogin(e) {
      e.preventDefault();
      const ident = document.getElementById('loginIdent').value;
      const pass = document.getElementById('loginPass').value;

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: ident, password: pass })
        });
        const data = await res.json();
        if (data.success) {
          closeModal('loginModal');
          window.location.reload();
        } else {
          alert(data.error || 'Login failed.');
        }
      } catch (err) {
        alert('Network error during login.');
      }
    }

    async function handleRegister(e) {
      e.preventDefault();
      const first = document.getElementById('regFirst').value;
      const surname = document.getElementById('regSurname').value;
      const age = document.getElementById('regAge').value;
      const phone = document.getElementById('regPhone').value;
      const email = document.getElementById('regEmail').value;
      const user = document.getElementById('regUser').value;
      const pass = document.getElementById('regPass').value;

      try {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: first,
            surname: surname,
            age: age,
            phone: phone,
            email: email,
            username: user,
            password: pass
          })
        });

        const data = await res.json();
        if (data.success) {
          pendingEmail = email;
          document.getElementById('otpEmailTarget').textContent = email;
          const demoBox = document.getElementById('demoOtpBox');
          
          if (data.email_sent_via_smtp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(16, 185, 129, 0.12)';
            demoBox.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            demoBox.style.color = '#10B981';
            demoBox.innerHTML = `✉️ <strong>Live Email Sent!</strong> A 6-digit verification code has been dispatched to <strong>${email}</strong>. Please check your inbox and spam folder.`;
          } else if (data.demo_otp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(201, 146, 46, 0.1)';
            demoBox.style.borderColor = 'rgba(201, 146, 46, 0.3)';
            demoBox.style.color = '#F5D77F';
            demoBox.innerHTML = `🔑 <strong>Dev Mode OTP:</strong> <span style="cursor:pointer; text-decoration:underline;" onclick="setEnteredOtp('${data.demo_otp}')">${data.demo_otp} (Click to auto-fill)</span><br><small style="color:var(--text-muted); font-size:11px;">Configure Gmail App Password in .env to send real emails to ${email}</small>`;
            setEnteredOtp(data.demo_otp);
          }

          switchModal('registerModal', 'otpModal');
          document.getElementById('otp_1').focus();
        } else {
          const errMsg = data.error || 'Registration failed.';
          if (errMsg.toLowerCase().includes('phone')) {
            const phoneInput = document.getElementById('regPhone');
            if (phoneInput) {
              phoneInput.style.borderColor = '#EF4444';
              phoneInput.focus();
            }
          }
          alert(`⚠️ ${errMsg}`);
        }
      } catch (err) {
        alert('Error initiating registration.');
      }
    }

    async function handleVerifyOtp(e) {
      e.preventDefault();
      const otp = getEnteredOtp();

      if (otp.length < 6) {
        alert('Please enter all 6 digits of the OTP code.');
        return;
      }

      try {
        const res = await fetch('/api/auth/verify-otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: pendingEmail, otp: otp })
        });
        const data = await res.json();
        if (data.success) {
          alert('Account verified successfully! Valuation unlocked.');
          closeModal('otpModal');
          window.location.reload();
        } else {
          alert(data.error || 'Invalid OTP code.');
        }
      } catch (err) {
        alert('Verification error.');
      }
    }

    async function resendOtp() {
      if (!pendingEmail) return;
      try {
        const res = await fetch('/api/auth/resend-otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: pendingEmail })
        });
        const data = await res.json();
        if (data.success) {
          const demoBox = document.getElementById('demoOtpBox');
          if (data.email_sent_via_smtp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(16, 185, 129, 0.12)';
            demoBox.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            demoBox.style.color = '#10B981';
            demoBox.innerHTML = `✉️ <strong>New Code Dispatched!</strong> Sent directly to <strong>${pendingEmail}</strong>.`;
          } else if (data.demo_otp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(201, 146, 46, 0.1)';
            demoBox.style.borderColor = 'rgba(201, 146, 46, 0.3)';
            demoBox.style.color = '#F5D77F';
            demoBox.innerHTML = `🔑 <strong>New Dev Mode OTP:</strong> <span style="cursor:pointer; text-decoration:underline;" onclick="setEnteredOtp('${data.demo_otp}')">${data.demo_otp} (Click to auto-fill)</span>`;
            setEnteredOtp(data.demo_otp);
          }
          alert('A new OTP has been dispatched.');
        }
      } catch (err) {
        alert('Failed to resend code.');
      }
    }

    async function handleForgot(e) {
      e.preventDefault();
      const email = document.getElementById('forgotEmail').value;
      try {
        const res = await fetch('/api/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email })
        });
        const data = await res.json();
        if (data.success) {
          pendingEmail = email;
          const demoBox = document.getElementById('demoResetOtpBox');
          if (data.email_sent_via_smtp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(16, 185, 129, 0.12)';
            demoBox.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            demoBox.style.color = '#10B981';
            demoBox.innerHTML = `✉️ <strong>Reset Code Sent!</strong> A 6-digit OTP code has been sent to <strong>${email}</strong>.`;
          } else if (data.demo_otp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(201, 146, 46, 0.1)';
            demoBox.style.borderColor = 'rgba(201, 146, 46, 0.3)';
            demoBox.style.color = '#F5D77F';
            demoBox.innerHTML = `🔑 <strong>Reset OTP:</strong> ${data.demo_otp}`;
          }
          switchModal('forgotModal', 'resetModal');
        } else {
          alert(data.error || 'Email not found.');
        }
      } catch (err) {
        alert('Error requesting reset code.');
      }
    }

    async function handleReset(e) {
      e.preventDefault();
      const otp = document.getElementById('resetOtp').value;
      const newPass = document.getElementById('resetNewPass').value;

      try {
        const res = await fetch('/api/auth/reset-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: pendingEmail, otp: otp, new_password: newPass })
        });
        const data = await res.json();
        if (data.success) {
          alert('Password updated successfully! Please sign in with your new password.');
          switchModal('resetModal', 'loginModal');
        } else {
          alert(data.error || 'Failed to update password.');
        }
      } catch (err) {
        alert('Reset password error.');
      }
    }

    function togglePasswordVisibility(inputId, btn) {
      const input = document.getElementById(inputId);
      if (!input) return;
      const isPass = input.type === 'password';
      input.type = isPass ? 'text' : 'password';
      
      if (isPass) {
        btn.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#F5D77F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>
            <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/>
            <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/>
            <line x1="2" x2="22" y1="2" y2="22"/>
          </svg>`;
        btn.setAttribute('title', 'Hide password');
      } else {
        btn.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>`;
        btn.setAttribute('title', 'Show password');
      }
    }

    function copyEmailToClipboard(email, btn) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(email).then(() => {
          const orig = btn.innerHTML;
          btn.innerHTML = '✅ Copied!';
          setTimeout(() => { btn.innerHTML = orig; }, 2200);
        }).catch(() => {
          prompt('Copy Email:', email);
        });
      } else {
        prompt('Copy Email:', email);
      }
    }

    // =========================================================================
    // Master Admin Portal Logic (User Management & Price Editor)
    // =========================================================================

    let adminUsersList = [];
    let adminPricesList = [];

    async function openAdminPortal() {
      try {
        const res = await fetch('/api/admin/me');
        const data = await res.json();
        if (data.is_admin) {
          openModal('adminPortalModal');
          loadAdminData();
        } else {
          openModal('adminLoginModal');
          setTimeout(() => {
            const el = document.getElementById('adminPasscode');
            if (el) el.focus();
          }, 200);
        }
      } catch (err) {
        openModal('adminLoginModal');
      }
    }

    async function handleAdminLogin(e) {
      e.preventDefault();
      const code = document.getElementById('adminPasscode').value;

      try {
        const res = await fetch('/api/admin/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ passcode: code })
        });
        const data = await res.json();

        if (data.success) {
          closeModal('adminLoginModal');
          document.getElementById('adminPasscode').value = '';
          openModal('adminPortalModal');
          loadAdminData();
        } else {
          alert(data.error || 'Invalid Master Admin Passcode.');
        }
      } catch (err) {
        alert('Network error during admin login.');
      }
    }

    async function handleAdminLogout() {
      try {
        await fetch('/api/admin/logout', { method: 'POST' });
        closeModal('adminPortalModal');
        speakAssistantLogout();
      } catch (err) {
        closeModal('adminPortalModal');
      }
    }

    async function handleAdminForgotPasscode(e) {
      e.preventDefault();
      const btn = document.getElementById('adminForgotBtn');
      const origText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '⏳ Dispatching OTP...';

      try {
        const res = await fetch('/api/admin/forgot-passcode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        btn.disabled = false;
        btn.innerHTML = origText;

        if (data.success) {
          const demoBox = document.getElementById('demoAdminResetOtpBox');
          if (data.email_sent_via_smtp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(16, 185, 129, 0.12)';
            demoBox.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            demoBox.style.color = '#10B981';
            demoBox.innerHTML = `✉️ <strong>Security OTP Dispatched!</strong> A 6-digit authorization code was delivered to the registered administrator email.`;
          } else if (data.demo_otp) {
            demoBox.style.display = 'block';
            demoBox.style.background = 'rgba(201, 146, 46, 0.1)';
            demoBox.style.borderColor = 'rgba(201, 146, 46, 0.3)';
            demoBox.style.color = '#F5D77F';
            demoBox.innerHTML = `🔑 <strong>Admin Dev Mode OTP:</strong> <span style="cursor:pointer; text-decoration:underline;" onclick="document.getElementById('adminResetOtp').value='${data.demo_otp}'">${data.demo_otp} (Click to fill)</span>`;
            document.getElementById('adminResetOtp').value = data.demo_otp;
          }

          switchModal('adminForgotModal', 'adminResetModal');
          document.getElementById('adminResetOtp').focus();
        } else {
          alert(data.error || 'Failed to dispatch security code.');
        }
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = origText;
        alert('Network error requesting admin reset.');
      }
    }

    async function handleAdminResetPasscode(e) {
      e.preventDefault();
      const otp = document.getElementById('adminResetOtp').value.trim();
      const newPasscode = document.getElementById('adminNewPasscode').value.trim();

      if (!otp || otp.length < 6) {
        alert('Please enter the 6-digit OTP code.');
        return;
      }
      if (!newPasscode || newPasscode.length < 6) {
        alert('New admin passcode must be at least 6 characters.');
        return;
      }

      const btn = document.getElementById('adminResetSubmitBtn');
      const origText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '⏳ Updating...';

      try {
        const res = await fetch('/api/admin/reset-passcode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ otp: otp, new_passcode: newPasscode })
        });
        const data = await res.json();
        btn.disabled = false;
        btn.innerHTML = origText;

        if (data.success) {
          alert('🎉 ' + data.message);
          closeModal('adminResetModal');
          document.getElementById('adminResetOtp').value = '';
          document.getElementById('adminNewPasscode').value = '';
          openModal('adminLoginModal');
        } else {
          alert(data.error || 'Failed to update admin passcode.');
        }
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = origText;
        alert('Network error updating admin passcode.');
      }
    }

    function switchAdminTab(tab) {
      const btnUsers = document.getElementById('tabBtnUsers');
      const btnPrices = document.getElementById('tabBtnPrices');
      const tabUsers = document.getElementById('adminTabUsers');
      const tabPrices = document.getElementById('adminTabPrices');

      if (tab === 'users') {
        btnUsers.classList.add('active');
        btnPrices.classList.remove('active');
        tabUsers.style.display = 'block';
        tabPrices.style.display = 'none';
      } else {
        btnPrices.classList.add('active');
        btnUsers.classList.remove('active');
        tabPrices.style.display = 'block';
        tabUsers.style.display = 'none';
        if (adminPricesList.length === 0) fetchAdminPrices();
      }
    }

    function loadAdminData() {
      fetchAdminUsers();
      fetchAdminPrices();
    }

    async function fetchAdminUsers() {
      try {
        const res = await fetch('/api/admin/users');
        const data = await res.json();
        if (data.success) {
          adminUsersList = data.users || [];
          document.getElementById('adminUsersBadge').textContent = adminUsersList.length;
          renderAdminUsersTable();
        }
      } catch (err) {
        console.error('Error fetching admin users:', err);
      }
    }

    function renderAdminUsersTable() {
      const tbody = document.getElementById('adminUsersTbody');
      if (!tbody) return;
      const search = (document.getElementById('adminUserSearch').value || '').toLowerCase().trim();

      const filtered = adminUsersList.filter(u => {
        const fullName = `${u.first_name || ''} ${u.surname || ''}`.toLowerCase();
        return fullName.includes(search) ||
               (u.username || '').toLowerCase().includes(search) ||
               (u.email || '').toLowerCase().includes(search) ||
               (u.phone || '').includes(search);
      });

      if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">No user accounts found.</td></tr>`;
        return;
      }

      tbody.innerHTML = filtered.map(u => {
        const dateStr = u.created_at ? new Date(u.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
        return `
          <tr>
            <td class="mono" style="color: var(--gold); font-weight: bold;">#${u.id}</td>
            <td><strong>${u.first_name} ${u.surname}</strong></td>
            <td class="mono" style="color: var(--accent-cyan);">${u.username}</td>
            <td>${u.email}</td>
            <td class="mono">${u.phone || '—'}</td>
            <td>${u.age || '—'}</td>
            <td style="color: var(--text-muted); font-size: 12px;">${dateStr}</td>
            <td style="text-align: right;">
              <button class="btn-danger-sm" onclick="deleteAdminUser(${u.id}, '${u.username}')">
                🗑️ Delete
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    async function deleteAdminUser(userId, username) {
      if (!confirm(`Are you sure you want to permanently delete user account '${username}' (ID: ${userId}) from the database?`)) {
        return;
      }

      try {
        const res = await fetch('/api/admin/users/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId })
        });
        const data = await res.json();
        if (data.success) {
          alert(`✅ ${data.message}`);
          fetchAdminUsers();
        } else {
          alert(data.error || 'Failed to delete user.');
        }
      } catch (err) {
        alert('Network error deleting user.');
      }
    }

    async function fetchAdminPrices() {
      try {
        const res = await fetch('/api/localities');
        const data = await res.json();
        if (data.success) {
          adminPricesList = data.localities || [];
          document.getElementById('adminPricesBadge').textContent = adminPricesList.length;
          renderAdminPricesTable();
        }
      } catch (err) {
        console.error('Error fetching localities for admin:', err);
      }
    }

    function renderAdminPricesTable() {
      const tbody = document.getElementById('adminPricesTbody');
      if (!tbody) return;
      const search = (document.getElementById('adminPriceSearch').value || '').toLowerCase().trim();

      const filtered = adminPricesList.filter(l => {
        return (l.name || '').toLowerCase().includes(search) ||
               (l.zone || '').toLowerCase().includes(search) ||
               (l.tier || '').toLowerCase().includes(search);
      });

      if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">No localities found matching search.</td></tr>`;
        return;
      }

      tbody.innerHTML = filtered.map(l => {
        const tenementRate = Math.round(l.rate_per_sqft * 1.28);
        return `
          <tr>
            <td><strong style="color: var(--gold-bright);">${l.name}</strong></td>
            <td><span class="badge badge-zone" style="font-size: 11px; padding: 2px 8px;">${l.zone}</span></td>
            <td><span class="tier-pill" style="font-size: 11px; padding: 2px 8px;">${l.tier}</span></td>
            <td class="mono" style="font-weight: bold; color: #FFFFFF;">₹${Math.round(l.rate_per_sqft).toLocaleString('en-IN')}</td>
            <td class="mono" style="color: var(--text-muted);">₹${Math.round(l.rate_per_sqyd).toLocaleString('en-IN')}</td>
            <td class="mono" style="color: var(--accent-cyan);">₹${tenementRate.toLocaleString('en-IN')}</td>
            <td class="mono" style="color: var(--accent-green); font-weight: 600;">+${l.yoy_percent || 6.0}%</td>
            <td class="mono" style="color: var(--gold);">${l.livability_score || '—'} / 10</td>
            <td style="text-align: right;">
              <button class="btn-edit-sm" onclick="openAdminPriceEditor('${l.name}', ${l.rate_per_sqft}, ${l.yoy_percent || 6.0}, ${l.livability_score || 9.0})">
                ✏️ Edit Rate
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    function openAdminPriceEditor(name, rateSqft, yoy, liv) {
      document.getElementById('editLocName').value = name;
      document.getElementById('editLocRateSqft').value = Math.round(rateSqft);
      document.getElementById('editLocYoy').value = yoy || 6.0;
      document.getElementById('editLocLivability').value = liv || 9.0;
      updateEditPriceCalculations();
      openModal('adminEditPriceModal');
    }

    function updateEditPriceCalculations() {
      const sqft = parseFloat(document.getElementById('editLocRateSqft').value) || 0;
      const sqyd = Math.round(sqft * 9);
      const tenement = Math.round(sqft * 1.28);
      document.getElementById('previewRateSqyd').textContent = `₹${sqyd.toLocaleString('en-IN')}`;
      document.getElementById('previewRateTenement').textContent = `₹${tenement.toLocaleString('en-IN')} / sq.ft (₹${(sqyd * 1.28).toLocaleString('en-IN')}/sqyd)`;
    }

    async function handleSaveLocalityPrice(e) {
      e.preventDefault();
      const locName = document.getElementById('editLocName').value;
      const rateSqft = parseFloat(document.getElementById('editLocRateSqft').value);
      const yoy = parseFloat(document.getElementById('editLocYoy').value);
      const liv = parseFloat(document.getElementById('editLocLivability').value);

      if (!rateSqft || rateSqft <= 0) {
        alert('Please enter a valid rate per sq.ft.');
        return;
      }

      try {
        const res = await fetch('/api/admin/locality/update-price', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: locName,
            rate_per_sqft: rateSqft,
            yoy_percent: yoy,
            livability_score: liv
          })
        });

        const data = await res.json();
        if (data.success) {
          alert(`✅ ${data.message}`);
          closeModal('adminEditPriceModal');
          fetchAdminPrices();
          fetchLocalities(); // Updates client-side locality list
        } else {
          alert(data.error || 'Failed to update locality pricing.');
        }
      } catch (err) {
        alert('Network error updating price.');
      }
    }
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
