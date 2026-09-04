"""
Vasudha Real Estate — Core Backend Service
Handles authentication, OTP generation, email notifications, password hashing,
and ML-driven property valuation calculations with rich locality insights.
"""

import os
import re
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash

import database
from ml_model import ml_model, SQYD_TO_SQFT, PROPERTY_TYPE_MULTIPLIERS

# In-memory OTP storage
# Format: email -> {"otp": str, "expires_at": datetime, "user_data": dict}
_pending_registrations = {}
# Format: email -> {"otp": str, "expires_at": datetime}
_pending_resets = {}

OTP_EXPIRY_MINUTES = 10


def format_inr(amount):
    """
    Format a numeric amount into Indian Currency notation (Lakhs / Crores).
    Example: 14850000 -> '₹1.49 Cr', 6500000 -> '₹65.00 L'
    """
    if amount is None:
        return "₹0"
    amount = float(amount)
    if amount >= 10000000:  # 1 Crore = 100 Lakhs = 10 Million
        crores = amount / 10000000.0
        return f"₹{crores:.2f} Cr"
    elif amount >= 100000:  # 1 Lakh = 100 Thousand
        lakhs = amount / 100000.0
        return f"₹{lakhs:.2f} L"
    else:
        return f"₹{amount:,.0f}"


def format_inr_full(amount):
    """Format full number with Indian comma grouping: 1,48,50,000"""
    if amount is None:
        return "₹0"
    s = f"{int(round(amount))}"
    if len(s) <= 3:
        return f"₹{s}"
    last_three = s[-3:]
    remaining = s[:-3]
    # Group remaining digits in pairs of 2 from right
    chunks = []
    while len(remaining) > 2:
        chunks.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        chunks.insert(0, remaining)
    return f"₹{','.join(chunks)},{last_three}"


# ---------------------------------------------------------------------------
# Email & OTP Dispatcher with Live SMTP (.env / email_config.json)
# ---------------------------------------------------------------------------

def load_email_config():
    """Load SMTP email configuration from .env or email_config.json."""
    config_dir = os.path.dirname(__file__)
    
    # 1. Check .env file
    env_file = os.path.join(config_dir, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        clean_v = v.strip().strip('"').strip("'")
                        if clean_v:
                            os.environ[k.strip()] = clean_v
        except Exception:
            pass

    # 2. Check email_config.json file
    json_file = os.path.join(config_dir, "email_config.json")
    if os.path.exists(json_file):
        try:
            import json
            with open(json_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                for k, v in cfg.items():
                    if v is not None and str(v).strip():
                        os.environ[str(k).strip()] = str(v).strip()
        except Exception:
            pass

load_email_config()


def generate_otp():
    """Generate a secure 6-digit OTP code."""
    return f"{random.randint(100000, 999999)}"


def send_email_otp(recipient_email, otp_code, purpose="Registration"):
    """
    Send real OTP email to recipient using SMTP (Gmail / Custom SMTP).
    If SMTP credentials are provided, dispatches live email directly to the recipient's inbox.
    Falls back gracefully to developer console display if no SMTP credentials are configured.
    """
    load_email_config()

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USERNAME", os.environ.get("GMAIL_USER", "Vasudha.realestate.01@gmail.com"))
    smtp_pass = os.environ.get("SMTP_PASSWORD", os.environ.get("GMAIL_APP_PASSWORD", "")).replace(" ", "")
    sender_email = os.environ.get("SMTP_SENDER", smtp_user or "Vasudha.realestate.01@gmail.com")

    subject = f"Vasudha Real Estate — Your {purpose} Verification Code: {otp_code}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b1220; color: #f8fafc; padding: 24px; }}
        .card {{ max-width: 520px; margin: 0 auto; background: #131c2e; border: 1px solid #c9922e; border-radius: 12px; padding: 32px; }}
        .brand {{ font-size: 22px; color: #c9922e; font-weight: bold; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 20px; }}
        .otp-box {{ background: #0b1220; border: 1px dashed #c9922e; padding: 18px; text-align: center; border-radius: 8px; margin: 24px 0; }}
        .otp-code {{ font-family: 'Courier New', monospace; font-size: 32px; font-weight: bold; color: #e8c468; letter-spacing: 8px; }}
        .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; border-top: 1px solid #1e293b; padding-top: 16px; line-height: 1.6; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="brand">VASUDHA REAL ESTATE</div>
        <h2 style="color: #f5d77f; margin-top: 0;">{purpose} Verification</h2>
        <p>You requested a one-time verification code for your Vasudha Real Estate account.</p>
        <div class="otp-box">
          <div class="otp-code">{otp_code}</div>
        </div>
        <p>This code is valid for <strong>10 minutes</strong>. Do not share this code with anyone.</p>
        <div class="footer">
          Ahmedabad Property Valuation & Analytics Platform<br>
          Architected & Developed by <strong>Patel Om</strong><br>
          Official Support: <a href="mailto:Vasudha.realestate.01@gmail.com" style="color: #c9922e; text-decoration: none;">Vasudha.realestate.01@gmail.com</a><br>
          © 2026 Vasudha Real Estate. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    email_sent = False
    error_msg = None

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Vasudha Real Estate <{sender_email}>"
            msg["To"] = recipient_email
            msg.attach(MIMEText(f"Your Vasudha Real Estate verification code is: {otp_code}. Valid for 10 minutes.", "plain"))
            msg.attach(MIMEText(html_content, "html"))

            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(sender_email, [recipient_email], msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(sender_email, [recipient_email], msg.as_string())

            email_sent = True
            print(f"[OTP Dispatch SUCCESS] Live email delivered to {recipient_email} via SMTP ({smtp_host}:{smtp_port}).")
        except Exception as e:
            error_msg = str(e)
            print(f"[OTP Dispatch Error] SMTP delivery failed: {e}. Falling back to console OTP.")

    if not email_sent:
        print("=" * 60)
        print(f"[DEMO / DEV MODE OTP] Recipient: {recipient_email}")
        print(f"[DEMO / DEV MODE OTP] Code:      {otp_code}")
        print(f"[DEMO / DEV MODE OTP] Purpose:   {purpose}")
        print(f"[DEMO / DEV MODE OTP] Expiry:    {OTP_EXPIRY_MINUTES} minutes")
        if error_msg:
            print(f"[SMTP Notice]        Add Gmail App Password in .env / email_config.json for live inbox dispatch.")
        print("=" * 60)

    return {
        "email_sent_via_smtp": email_sent,
        "demo_otp": None if email_sent else otp_code,
        "recipient": recipient_email,
        "smtp_error": error_msg if not email_sent else None
    }


# ---------------------------------------------------------------------------
# Admin Passcode & Portal Operations
# ---------------------------------------------------------------------------

# OTP and security limits
MAX_OTP_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60

# Admin Passcode (Configurable via environment variable)
ADMIN_PASSCODE = os.environ.get("ADMIN_PASSCODE", "OPatel050512%")
ADMIN_RECOVERY_EMAIL = "ompatel94929@gmail.com"

_pending_admin_reset = {}


def check_admin_passcode(passcode):
    """Verify Master Admin Passcode."""
    if not passcode:
        return False
    load_email_config()
    current_passcode = os.environ.get("ADMIN_PASSCODE", "OPatel050512%").strip()
    return str(passcode).strip() == current_passcode


def start_admin_password_reset():
    """
    Initiate Admin Passcode Reset.
    Dispatches security OTP directly to ompatel94929@gmail.com without revealing the address to user.
    """
    load_email_config()
    now_utc = datetime.now(timezone.utc)
    
    # Cooldown check
    if _pending_admin_reset and "last_sent_at" in _pending_admin_reset:
        elapsed = (now_utc - _pending_admin_reset["last_sent_at"]).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait_sec = int(RESEND_COOLDOWN_SECONDS - elapsed)
            return {"success": False, "error": f"Please wait {wait_sec} seconds before requesting a new admin security code."}

    otp = generate_otp()
    expires_at = now_utc + timedelta(minutes=OTP_EXPIRY_MINUTES)

    _pending_admin_reset.clear()
    _pending_admin_reset.update({
        "otp": otp,
        "attempts": 0,
        "last_sent_at": now_utc,
        "expires_at": expires_at
    })

    dispatch_res = send_email_otp(ADMIN_RECOVERY_EMAIL, otp, purpose="Master Admin Passcode Reset")

    return {
        "success": True,
        "message": "Security verification OTP has been dispatched to authorized administrator email.",
        "email_sent_via_smtp": dispatch_res.get("email_sent_via_smtp", False),
        "demo_otp": dispatch_res.get("demo_otp")
    }


def verify_admin_password_reset(otp_entered, new_passcode):
    """Verify admin reset OTP and update master passcode."""
    if not _pending_admin_reset:
        return {"success": False, "error": "No pending admin reset request found. Please request a new code."}

    now_utc = datetime.now(timezone.utc)
    if now_utc > _pending_admin_reset["expires_at"]:
        _pending_admin_reset.clear()
        return {"success": False, "error": "Admin security OTP has expired. Please request a new code."}

    if _pending_admin_reset.get("attempts", 0) >= MAX_OTP_ATTEMPTS:
        _pending_admin_reset.clear()
        return {"success": False, "error": "Maximum OTP verification attempts exceeded. Please request a fresh code."}

    if str(_pending_admin_reset["otp"]).strip() != str(otp_entered).strip():
        _pending_admin_reset["attempts"] = _pending_admin_reset.get("attempts", 0) + 1
        rem = MAX_OTP_ATTEMPTS - _pending_admin_reset["attempts"]
        if rem <= 0:
            _pending_admin_reset.clear()
            return {"success": False, "error": "Too many invalid attempts. Admin reset request cancelled."}
        return {"success": False, "error": f"Invalid verification OTP. {rem} attempt(s) remaining."}

    new_pwd = str(new_passcode or "").strip()
    if len(new_pwd) < 6:
        return {"success": False, "error": "New admin passcode must be at least 6 characters long."}

    global ADMIN_PASSCODE
    ADMIN_PASSCODE = new_pwd
    os.environ["ADMIN_PASSCODE"] = new_pwd

    # Update in .env file if present
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            found = False
            new_lines = []
            for line in lines:
                if line.startswith("ADMIN_PASSCODE="):
                    new_lines.append(f"ADMIN_PASSCODE={new_pwd}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"ADMIN_PASSCODE={new_pwd}\n")
            
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            pass

    _pending_admin_reset.clear()

    return {
        "success": True,
        "message": "Master Admin Passcode updated successfully! You can now sign in with your new passcode."
    }


def admin_get_all_users():
    """Admin: Return list of all registered users."""
    users = database.get_all_users()
    return {"success": True, "count": len(users), "users": users}


def admin_delete_user(user_id):
    """Admin: Delete user account by ID."""
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid User ID."}

    user = database.get_user_by_id(uid)
    if not user:
        return {"success": False, "error": "User not found."}

    deleted = database.delete_user(uid)
    if deleted:
        return {"success": True, "message": f"User account '{user['username']}' ({user['email']}) deleted successfully."}
    return {"success": False, "error": "Failed to delete user."}


def admin_update_locality_price(locality_name, rate_per_sqft, yoy_percent=None, livability_score=None):
    """Admin: Manually update pricing and metrics for any locality."""
    loc = database.get_locality_by_name(locality_name)
    if not loc:
        return {"success": False, "error": f"Locality '{locality_name}' not found."}

    try:
        sqft = float(rate_per_sqft)
        if sqft <= 0:
            return {"success": False, "error": "Rate per sq.ft must be greater than 0."}
        sqyd = round(sqft * 9.0, 2)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid rate value."}

    yoy_val = None
    if yoy_percent is not None and str(yoy_percent).strip():
        try:
            yoy_val = float(yoy_percent)
        except (ValueError, TypeError):
            return {"success": False, "error": "Invalid YoY percentage value."}

    liv_val = None
    if livability_score is not None and str(livability_score).strip():
        try:
            liv_val = float(livability_score)
            if liv_val < 0 or liv_val > 10:
                return {"success": False, "error": "Livability score must be between 0 and 10."}
        except (ValueError, TypeError):
            return {"success": False, "error": "Invalid livability score."}

    # Calculate 5-year compounding projection
    effective_yoy = yoy_val if yoy_val is not None else (loc.get("yoy_percent") or 6.0)
    projected_5yr = round(sqyd * ((1.0 + (effective_yoy / 100.0)) ** 5), 2)

    updated = database.update_locality_price(
        name=loc["name"],
        rate_per_sqft=sqft,
        rate_per_sqyd=sqyd,
        yoy_percent=yoy_val,
        projected_5yr=projected_5yr,
        livability_score=liv_val
    )

    if updated:
        return {
            "success": True,
            "message": f"Pricing for '{loc['name']}' updated successfully!",
            "locality": loc["name"],
            "rate_per_sqft": sqft,
            "rate_per_sqyd": sqyd,
            "yoy_percent": yoy_val or loc.get("yoy_percent"),
            "projected_5yr": projected_5yr,
            "livability_score": liv_val or loc.get("livability_score")
        }
    return {"success": False, "error": "Database update failed."}


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------

def validate_registration_fields(first_name, surname, age, phone, email, username, password):
    """Validate all user registration inputs with strict bounds."""
    first = str(first_name or "").strip()
    last = str(surname or "").strip()
    if len(first) < 2 or len(first) > 50:
        return "First name must be between 2 and 50 characters."
    if len(last) < 2 or len(last) > 50:
        return "Surname must be between 2 and 50 characters."

    try:
        age_int = int(age)
        if age_int < 18 or age_int > 120:
            return "Age must be between 18 and 120."
    except (ValueError, TypeError):
        return "Please enter a valid age."

    phone_clean = re.sub(r"[\s\-\+]", "", str(phone or ""))
    if len(phone_clean) < 10 or len(phone_clean) > 15 or not phone_clean.isdigit():
        return "Phone number must be a valid 10-15 digit number."

    email_clean = str(email or "").strip().lower()
    if len(email_clean) > 120 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_clean):
        return "Please enter a valid email address."

    username_clean = str(username or "").strip()
    if len(username_clean) < 3 or len(username_clean) > 30 or not re.match(r"^[A-Za-z0-9_]+$", username_clean):
        return "Username must be 3-30 characters (letters, numbers, underscores only)."

    pwd = str(password or "")
    if len(pwd) < 8 or len(pwd) > 128:
        return "Password must be between 8 and 128 characters long."

    # Check if email, username, or phone already exists in DB
    conflict = database.check_user_credentials_exist(email_clean, username_clean, phone_clean)
    if conflict:
        return conflict

    return None


# ---------------------------------------------------------------------------
# Registration Flow with Email OTP & Security Defenses
# ---------------------------------------------------------------------------

def start_registration(first_name, surname, age, phone, email, username, password):
    """Initiate registration, validate fields, and send OTP with flood protection."""
    err = validate_registration_fields(first_name, surname, age, phone, email, username, password)
    if err:
        return {"success": False, "error": err}

    email_key = email.lower().strip()
    now_utc = datetime.now(timezone.utc)

    # Flood cooldown check
    existing = _pending_registrations.get(email_key)
    if existing and "last_sent_at" in existing:
        elapsed = (now_utc - existing["last_sent_at"]).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait_sec = int(RESEND_COOLDOWN_SECONDS - elapsed)
            return {"success": False, "error": f"Please wait {wait_sec} seconds before requesting a new code."}

    otp = generate_otp()
    expires_at = now_utc + timedelta(minutes=OTP_EXPIRY_MINUTES)

    _pending_registrations[email_key] = {
        "otp": otp,
        "attempts": 0,
        "last_sent_at": now_utc,
        "expires_at": expires_at,
        "user_data": {
            "first_name": first_name.strip(),
            "surname": surname.strip(),
            "age": int(age),
            "phone": str(phone).strip(),
            "email": email_key,
            "username": username.strip(),
            "password_hash": generate_password_hash(password)
        }
    }

    dispatch_res = send_email_otp(email_key, otp, purpose="Account Registration")

    return {
        "success": True,
        "message": f"Verification code sent to {email_key}",
        "email": email_key,
        "email_sent_via_smtp": dispatch_res.get("email_sent_via_smtp", False),
        "demo_otp": dispatch_res.get("demo_otp")
    }


def verify_registration_otp(email, otp_entered):
    """Verify OTP with attempt bounds and complete user account creation."""
    email_key = email.lower().strip()
    pending = _pending_registrations.get(email_key)

    if not pending:
        return {"success": False, "error": "No pending registration found for this email. Please register again."}

    now_utc = datetime.now(timezone.utc)
    if now_utc > pending["expires_at"]:
        _pending_registrations.pop(email_key, None)
        return {"success": False, "error": "OTP has expired. Please register again to get a fresh code."}

    # Brute-force protection
    if pending.get("attempts", 0) >= MAX_OTP_ATTEMPTS:
        _pending_registrations.pop(email_key, None)
        return {"success": False, "error": "Maximum OTP verification attempts exceeded. Please register again."}

    if str(pending["otp"]).strip() != str(otp_entered).strip():
        pending["attempts"] = pending.get("attempts", 0) + 1
        remaining = MAX_OTP_ATTEMPTS - pending["attempts"]
        if remaining <= 0:
            _pending_registrations.pop(email_key, None)
            return {"success": False, "error": "Too many incorrect attempts. This verification code has been invalidated for security."}
        return {"success": False, "error": f"Invalid OTP code. {remaining} attempt(s) remaining."}

    # OTP is valid -> Create user in DB
    user_data = pending["user_data"]
    db_res = database.create_user(
        first_name=user_data["first_name"],
        surname=user_data["surname"],
        age=user_data["age"],
        phone=user_data["phone"],
        email=user_data["email"],
        username=user_data["username"],
        password_hash=user_data["password_hash"]
    )

    _pending_registrations.pop(email_key, None)

    if not db_res["success"]:
        return db_res

    created_user = database.get_user_by_id(db_res["user_id"])
    return {
        "success": True,
        "message": "Account created and verified successfully!",
        "user": {
            "id": created_user["id"],
            "first_name": created_user["first_name"],
            "surname": created_user["surname"],
            "email": created_user["email"],
            "username": created_user["username"]
        }
    }


def resend_registration_otp(email):
    """Resend OTP for pending registration with cooldown enforcement."""
    email_key = email.lower().strip()
    pending = _pending_registrations.get(email_key)

    if not pending:
        return {"success": False, "error": "No pending registration found. Please register first."}

    now_utc = datetime.now(timezone.utc)
    if "last_sent_at" in pending:
        elapsed = (now_utc - pending["last_sent_at"]).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait_sec = int(RESEND_COOLDOWN_SECONDS - elapsed)
            return {"success": False, "error": f"Please wait {wait_sec} seconds before requesting a new code."}

    otp = generate_otp()
    pending["otp"] = otp
    pending["attempts"] = 0
    pending["last_sent_at"] = now_utc
    pending["expires_at"] = now_utc + timedelta(minutes=OTP_EXPIRY_MINUTES)

    dispatch_res = send_email_otp(email_key, otp, purpose="Account Registration")
    return {
        "success": True,
        "message": f"A fresh OTP has been sent to {email_key}",
        "email_sent_via_smtp": dispatch_res.get("email_sent_via_smtp", False),
        "demo_otp": dispatch_res.get("demo_otp")
    }


# ---------------------------------------------------------------------------
# Authentication Flow
# ---------------------------------------------------------------------------

def authenticate_user(identifier, password):
    """Authenticate user with username/email and password."""
    ident = identifier.strip()
    user = database.get_user_by_email(ident)
    if not user:
        user = database.get_user_by_username(ident)

    if not user:
        return {"success": False, "error": "No account found with this username or email."}

    if not check_password_hash(user["password_hash"], password):
        return {"success": False, "error": "Incorrect password. Please try again."}

    return {
        "success": True,
        "user": {
            "id": user["id"],
            "first_name": user["first_name"],
            "surname": user["surname"],
            "email": user["email"],
            "username": user["username"],
            "phone": user["phone"],
            "age": user["age"]
        }
    }


# ---------------------------------------------------------------------------
# Forgot & Reset Password Flow with Security Defenses
# ---------------------------------------------------------------------------

def start_password_reset(email):
    """Initiate password reset with cooldown enforcement."""
    email_key = email.lower().strip()
    user = database.get_user_by_email(email_key)

    if not user:
        return {"success": False, "error": "No account registered with this email address."}

    now_utc = datetime.now(timezone.utc)
    existing = _pending_resets.get(email_key)
    if existing and "last_sent_at" in existing:
        elapsed = (now_utc - existing["last_sent_at"]).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait_sec = int(RESEND_COOLDOWN_SECONDS - elapsed)
            return {"success": False, "error": f"Please wait {wait_sec} seconds before requesting a new reset code."}

    otp = generate_otp()
    expires_at = now_utc + timedelta(minutes=OTP_EXPIRY_MINUTES)

    _pending_resets[email_key] = {
        "otp": otp,
        "attempts": 0,
        "last_sent_at": now_utc,
        "expires_at": expires_at
    }

    dispatch_res = send_email_otp(email_key, otp, purpose="Password Reset")

    return {
        "success": True,
        "message": f"Password reset OTP sent to {email_key}",
        "email": email_key,
        "email_sent_via_smtp": dispatch_res.get("email_sent_via_smtp", False),
        "demo_otp": dispatch_res.get("demo_otp")
    }


def verify_password_reset(email, otp_entered, new_password):
    """Verify OTP and update password with attempt tracking and length validation."""
    email_key = email.lower().strip()
    pending = _pending_resets.get(email_key)

    if not pending:
        return {"success": False, "error": "No active password reset request found. Please request a new code."}

    now_utc = datetime.now(timezone.utc)
    if now_utc > pending["expires_at"]:
        _pending_resets.pop(email_key, None)
        return {"success": False, "error": "OTP has expired. Please request a new password reset."}

    # Brute-force protection
    if pending.get("attempts", 0) >= MAX_OTP_ATTEMPTS:
        _pending_resets.pop(email_key, None)
        return {"success": False, "error": "Maximum OTP verification attempts exceeded. Please request a new code."}

    if str(pending["otp"]).strip() != str(otp_entered).strip():
        pending["attempts"] = pending.get("attempts", 0) + 1
        remaining = MAX_OTP_ATTEMPTS - pending["attempts"]
        if remaining <= 0:
            _pending_resets.pop(email_key, None)
            return {"success": False, "error": "Too many incorrect attempts. This reset request has been invalidated."}
        return {"success": False, "error": f"Invalid OTP code. {remaining} attempt(s) remaining."}

    pwd = str(new_password or "")
    if len(pwd) < 8 or len(pwd) > 128:
        return {"success": False, "error": "New password must be between 8 and 128 characters long."}

    new_hash = generate_password_hash(pwd)
    updated = database.update_user_password(email_key, new_hash)
    _pending_resets.pop(email_key, None)

    if not updated:
        return {"success": False, "error": "Failed to update password. Please try again."}

    return {
        "success": True,
        "message": "Password reset successfully! You can now log in with your new password."
    }


# ---------------------------------------------------------------------------
# Locality Price Dynamics & Bilingual Explanation Catalog (29+ Ahmedabad Areas)
# ---------------------------------------------------------------------------

LOCALITY_PRICE_EXPLANATIONS = {
    "Thaltej": {
        "explanation_en": "Prices in Thaltej command a prime tier due to high demand along Drive-In Road and SG Highway, combined with an acute scarcity of vacant residential plots. There is a limited supply of 3 BHK units from premium builders in the popular 190–200 sq. yard segment, pushing competition and prices upward. Additionally, several legacy low-rise housing societies are undergoing high-rise redevelopment and reconstruction, commanding significant new-construction premiums. Excellent social infrastructure—including SAL and CIMS hospitals, Udgam and Anand Niketan schools, and the operational Thaltej Metro Station—solidifies its enduring investment appeal.",
        "explanation_hi": "थलतेज में संपत्ति की कीमतें ड्राइव-इन रोड और एसजी हाईवे की उच्च मांग के कारण प्रीमियम स्तर पर हैं। 190 से 200 वर्ग गज के लोकप्रिय 3 बीएचके फ्लैटों की सीमित आपूर्ति के कारण कीमतों में लगातार उछाल देखा जा रहा है। इसके अतिरिक्त, पुरानी सोसायटियों में चल रहे पुनर्विकास (रीडेवलपमेंट) प्रोजेक्ट्स नए निर्माण पर उच्च प्रीमियम हासिल कर रहे हैं। सल अस्पताल, उद्गम स्कूल और ऑपरेशनल मेट्रो कनेक्टिविटी जैसी बेहतरीन सुविधाएं इस क्षेत्र के आकर्षण को और मजबूत बनाती हैं।",
        "price_drivers": ["Limited 3 BHK Builder Supply (190-200 sq.yd)", "Active Society Redevelopment", "Operational Metro Corridor & Tertiary Hospitals"]
    },
    "Bodakdev": {
        "explanation_en": "Bodakdev stands as Ahmedabad's most exclusive luxury residential enclave along Judges Bungalow Road. Extreme land scarcity and strict zoning keep inventory ultra-tight. Reputed builders offering spacious 3 and 4 BHK configurations face overwhelming demand, while upscale redevelopment of low-rise bungalows into boutique luxury floors commands top-tier pricing. Proximity to elite institutions like Zydus Hospital, AIS, and Ahmedabad One Mall anchors premium capital appreciation.",
        "explanation_hi": "बोडकदेव जजेस बंगला रोड पर स्थित अहमदाबाद का सबसे प्रतिष्ठित और अल्ट्रा-लक्जरी इलाका है। यहां जमीन की भारी कमी और सीमित नए प्रोजेक्ट्स के कारण कीमतें शीर्ष स्तर पर हैं। बड़े 3 और 4 बीएचके फ्लैट्स और पुराने बंगलों के नए बुटीक फ्लोर्स में पुनर्विकास से उच्चतम दरें प्राप्त होती हैं। जायडस अस्पताल, अहमदाबाद वन मॉल और शीर्ष अंतरराष्ट्रीय स्कूलों की निकटता इसे उच्च मूल्यवान बनाती है।",
        "price_drivers": ["Extreme Land Scarcity", "Boutique Low-Rise to Luxury High-Rise Redevelopment", "Judges Bungalow Elite Hub"]
    },
    "Ambli": {
        "explanation_en": "Ambli's valuation is driven by its emergence as the ultra-luxury high-rise corridor along the Ambli-Bopal road. Premium developers focus on expansive 3 and 4 BHK lifestyle residences with club amenities, creating high ticket prices. The absence of mid-segment inventory and ongoing reconstruction of expansive farm-plots into luxury high-rises drives benchmark rates. Superb connectivity to SP Ring Road and SG Highway makes it a prime magnet for high-net-worth investors.",
        "explanation_hi": "आंबली-बोपाल रोड अहमदाबाद का प्रमुख अल्ट्रा-लक्जरी हाई-राइज कॉरिडोर बन चुका है। यहां बिल्डर्स मुख्य रूप से बड़े और आधुनिक 3 व 4 बीएचके लक्जरी अपार्टमेंट्स पर ध्यान केंद्रित कर रहे हैं, जिससे औसत कीमतें काफी ऊंची हैं। मध्यम श्रेणी के मकानों की कमी और फार्म-प्लॉट्स के लक्जरी प्रोजेक्ट्स में पुनर्विकास से दरों में भारी वृद्धि हुई है। एसपी रिंग रोड से सीधा जुड़ाव इसे निवेशकों की पहली पसंद बनाता है।",
        "price_drivers": ["Ultra-Luxury High-Rise Concentration", "Clubhouse & Lifestyle Amenities", "Direct SP Ring Road & SBR Link"]
    },
    "Sindhu Bhavan Road": {
        "explanation_en": "Sindhu Bhavan Road (SBR) represents Ahmedabad's highest-valued lifestyle boulevard. Commercial grade-A tech parks, high-end retail, and gourmet dining make residential units here command peak market rates. Builders face limited permissible FSI and high land acquisition costs, keeping inventory limited to ultra-luxury 3, 4, and 5 BHK penthouses. Proximity to Taj Skyline, corporate headquarters, and wide 45m arterial access justify its premium position.",
        "explanation_hi": "सिंधु भवन रोड (एसबीआर) अहमदाबाद का सबसे प्रमुख और आधुनिक लाइफस्टाइल बुलेवार्ड है। यहां ग्रेड-ए टेक पार्क्स, महंगे रिटेल स्टोर्स और कॉर्पोरेट ऑफिसों के कारण आवासीय संपत्तियों की कीमतें रिकॉर्ड स्तर पर हैं। सीमित जमीन और उच्च अधिग्रहण लागत के कारण केवल विशिष्ट 3, 4 और 5 बीएचके पेंटहाउस उपलब्ध हैं। चौड़ी 45 मीटर सड़कें और ताज स्काईलाइन की निकटता इसे सबसे प्रीमियम बनाती है।",
        "price_drivers": ["Peak Commercial & Retail Synergy", "Ultra-Luxury Penthouse Inventory", "45m Arterial Boulevard Infrastructure"]
    },
    "Satellite": {
        "explanation_en": "Satellite is a mature, densely populated prime western neighborhood around ISRO and Shivranjani. Prices remain high due to high family occupancy and practically zero greenfield land. Rising prices are driven by redevelopment projects replacing 30-year-old societies with contemporary high-rises. Top healthcare like Shalby Hospital, premier schools, and the Shivranjani BRTS/metro hub maintain consistent end-user demand.",
        "explanation_hi": "सैटेलाइट इसरो और शिवरंजनी के आसपास का एक परिपक्व और सुविकसित इलाका है। यहां नई खाली जमीन न होने के कारण कीमतें निरंतर मजबूत हैं। पुरानी सोसायटियों के आधुनिक बहुमंजिला इमारतों में पुनर्विकास के कारण नए फ्लैट्स पर अच्छा प्रीमियम मिल रहा है। शालबी अस्पताल, बेहतरीन स्कूल और शिवरंजनी बीआरटीएस हब की मौजूदगी से यहां पारिवारिक खरीदारों की मांग हमेशा बनी रहती है।",
        "price_drivers": ["Zero Greenfield Land", "Legacy Society Reconstruction", "Shivranjani Hub & Shalby Hospital"]
    },
    "SG Highway": {
        "explanation_en": "The SG Highway commercial spine commands premium pricing driven by corporate office expansion and rapid transit upgrades. Premium 3 BHK inventory along the service road faces strong absorption from corporate executives. Ongoing flyover infrastructure, Metro Phase-2 connectivity, and proximity to KD Hospital and Vaishnodevi circle keep price growth robust.",
        "explanation_hi": "एसजी हाईवे अहमदाबाद की प्रमुख आर्थिक रीढ़ है जहां कॉर्पोरेट विस्तार और मेट्रो फेज-2 के कारण कीमतें मजबूत हैं। सर्विस रोड के आसपास 3 बीएचके फ्लैट्स की कॉरपोरेट अधिकारियों द्वारा भारी मांग है। लगातार सुधरते फ्लाईओवर नेटवर्क और केडी अस्पताल जैसी विश्वस्तरीय सुविधाओं से यहां प्रॉपर्टी के दामों में स्थिर तेजी बनी हुई है।",
        "price_drivers": ["Corporate Corridor Growth", "Metro Phase-2 Connectivity", "High Executive Rental Yields"]
    },
    "Vastrapur": {
        "explanation_en": "Vastrapur is a culturally rich, top-tier residential market centered on Vastrapur Lake and IIM Ahmedabad. High land values and established infrastructure limit new builder developments to exclusive society redevelopment projects. Proximity to Alpha One Mall, Sanjivani Hospital, and premier institutions sustains high per-sq-yard valuations.",
        "explanation_hi": "वस्त्रापुर झील और आईआईएम अहमदाबाद के निकट स्थित वस्त्रापुर एक अत्यंत प्रतिष्ठित आवासीय क्षेत्र है। यहां खाली जमीन की अनुपलब्धता के कारण नए प्रोजेक्ट्स केवल पुनर्विकास (रीडेवलपमेंट) के जरिए ही आ रहे हैं, जिससे कीमतें ऊंची हैं। अल्फा वन मॉल, संजीवनी अस्पताल और प्रमुख शैक्षणिक संस्थानों की उपस्थिति से इस क्षेत्र की मांग सर्वोच्च है।",
        "price_drivers": ["Vastrapur Lakefront & IIM Vicinity", "Selective Society Redevelopment", "High Educational & Lifestyle Value"]
    },
    "Prahlad Nagar": {
        "explanation_en": "Prahlad Nagar commands premium rates as a master-planned corporate and residential address. High rental yields and established corporate parks create intense buyer demand, with limited resale supply in standard 3 BHK configurations. Well-maintained civic infrastructure, Anand Niketan school, and Shalby Hospital ensure continued capital appreciation.",
        "explanation_hi": "प्रहलाद नगर एक सुव्यवस्थित और आधुनिक कॉर्पोरेट व आवासीय क्षेत्र है। कॉर्पोरेट पार्कों और उच्च किराये की आय के कारण यहां 3 बीएचके फ्लैट्स की जबरदस्त मांग है जबकि पुनर्विक्रय (रीसेल) इन्वेंट्री काफी सीमित है। प्रहलाद नगर गार्डन, आनंद निकेतन स्कूल और शालबी अस्पताल जैसी सुविधाएं इसकी मजबूत कीमतों को बनाए रखती हैं।",
        "price_drivers": ["Corporate Business Hub Proximity", "Tight 3 BHK Resale Supply", "High Livability & Civic Gardens"]
    },
    "Shela": {
        "explanation_en": "Shela is an appreciating high-growth corridor offering mid-to-premium modern gated communities. While initial inventory was plentiful, rapid absorption of 3 BHK units near Club O7 and Applewoods has created upward price pressure. Planned lake developments and direct SP Ring Road access make it an attractive alternative to saturated core western micro-markets.",
        "explanation_hi": "शीला तेजी से विकसित होता हुआ आधुनिक गेटेड कम्युनिटीज का केंद्र है। क्लब ओ7 और एप्पलवुड्स टाउनशिप के पास 3 बीएचके फ्लैट्स की भारी मांग के कारण दरों में निरंतर वृद्धि हो रही है। सुनियोजित झील का विकास और एसपी रिंग रोड से सीधा जुड़ाव इसे एक तेजी से बढ़ता हुआ निवेश विकल्प बनाते हैं।",
        "price_drivers": ["Rapid 3 BHK Inventory Absorption", "Modern Gated Townships & Club O7", "Direct SP Ring Road Arterial Link"]
    },
    "South Bopal": {
        "explanation_en": "South Bopal is a vibrant cosmopolitan suburban hub popular among young tech and finance professionals. Prices have transitioned from affordable to mid-premium due to modern infrastructure around SOBO Center and TRP Mall. Limited standalone bungalow options and high demand for quality multi-storey 3 BHKs sustain healthy annual price gains.",
        "explanation_hi": "साउथ बोपाल युवा प्रोफेशनल्स के लिए एक पसंदीदा आधुनिक उपनगरीय क्षेत्र है। सोबो सेंटर और टीआरपी मॉल के आसपास सुधरे बुनियादी ढांचे के कारण कीमतें मध्यम से प्रीमियम श्रेणी में पहुंच चुकी हैं। बहुमंजिला 3 बीएचके फ्लैट्स की मजबूत मांग और बीआरटीएस कनेक्टिविटी के चलते यहां प्रॉपर्टी के दाम तेजी से बढ़ रहे हैं।",
        "price_drivers": ["Cosmopolitan Young Professional Demand", "SOBO Center Retail Ecosystem", "Transit-Oriented Growth"]
    },
    "Bopal": {
        "explanation_en": "Bopal represents a self-contained, established residential market with stable pricing. Broad retail presence, DPS Bopal, and Bopal Lake provide complete community living. Prices are moderately priced compared to core western areas, offering value-driven 2 and 3 BHK housing options with steady appreciation.",
        "explanation_hi": "बोपाल एक पूर्ण और सुस्थापित आवासीय क्षेत्र है जहां कीमतें संतुलित और स्थिर हैं। डीपीएस बोपाल स्कूल, व्यापक बाजार और बोपाल झील जैसी सुविधाएं इसे पारिवारिक जीवन के लिए आदर्श बनाती हैं। मुख्य पश्चिमी इलाकों की तुलना में यह किफायती और मूल्यवान 2 व 3 बीएचके विकल्प प्रदान करता है।",
        "price_drivers": ["Established Community Infrastructure", "DPS Bopal Educational Proximity", "Affordable-to-Mid Transition"]
    },
    "Science City": {
        "explanation_en": "Science City road is a fast-appreciating modern corridor adjacent to Gujarat Science City. Spacious wide-road planning and limited builder plots in prime segments push new 3 and 4 BHK high-rises to premium rate brackets. CIMS hospital and direct links to SG Highway and Ring Road bolster its prestige.",
        "explanation_hi": "साइंस सिटी रोड गुजरात साइंस सिटी के पास स्थित एक तेजी से बढ़ता आधुनिक आवासीय कॉरिडोर है। चौड़ी सड़कें और स्वच्छ वातावरण के कारण यहां नए 3 और 4 बीएचके हाई-राइज प्रोजेक्ट्स प्रीमियम दरों पर बिक रहे हैं। सिम्स अस्पताल और एसजी हाईवे से सीधी कनेक्टिविटी इसकी मांग को निरंतर बढ़ा रही है।",
        "price_drivers": ["Wide Avenue Urban Planning", "Science City Tourism & Green Belt", "CIMS Hospital & Ring Road Proximity"]
    },
    "Shilaj": {
        "explanation_en": "Shilaj is transitioning from a tranquil western suburb into a luxury villa and mid-premium residential zone near Shilaj Lake. Scarcity of low-density plots and high demand for independent duplexes drive solid rate appreciation. GIIS school and Ring Road connectivity provide strong fundamentals.",
        "explanation_hi": "शीलाज एक शांत उपनगर से लक्जरी विला और आधुनिक आवासीय क्षेत्र के रूप में उभर रहा है। स्वतंत्र डुप्लेक्स और कम घनत्व वाले प्लॉट्स की कमी के कारण यहां जमीन और मकानों की कीमतों में लगातार वृद्धि हो रही है। जीआईआईएस स्कूल और रिंग रोड से आसान पहुंच इसके मुख्य आकर्षण हैं।",
        "price_drivers": ["Low-Density Villa & Duplex Appeal", "Shilaj Lake Development", "Sardar Patel Ring Road Junction"]
    },
    "Motera": {
        "explanation_en": "Motera's real estate trajectory has surged following the Narendra Modi Stadium and Metro Phase-1 & 2 integration. High transit connectivity and direct arterial access to GIFT City make 3 BHK units here in high demand among professionals. Sabarmati Riverfront extension and Bullet Train terminal proximity add immense long-term value.",
        "explanation_hi": "मोटेरा में नरेंद्र मोदी स्टेडियम और मेट्रो कनेक्टिविटी के बाद प्रॉपर्टी की कीमतों में भारी उछाल आया है। गिफ्ट सिटी के निकट होने और साबरमती बुलेट ट्रेन टर्मिनल की निकटता के कारण यहां 3 बीएचके आवासीय इकाइयों की जबर्दस्त मांग है, जिससे यह एक उत्कृष्ट निवेश क्षेत्र बन चुका है।",
        "price_drivers": ["Narendra Modi Stadium & Sports Hub", "Direct GIFT City Corridor Link", "Metro Station & Bullet Train Node"]
    },
    "Chandkheda": {
        "explanation_en": "Chandkheda offers practical mid-tier housing with strong rental demand from ONGC and IIT Gandhinagar corridors. Abundant residential supply keeps entry prices competitive, while proximity to the Ahmedabad-Gandhinagar highway ensures steady appreciation for standard 2 and 3 BHK homes.",
        "explanation_hi": "चांदखेड़ा ओएनजीसी और आईआईटी गांधीनगर कॉरिडोर के निकट एक किफायती और सुव्यवस्थित आवासीय क्षेत्र है। यहां पर्याप्त हाउसिंग सप्लाई के कारण कीमतें संतुलित हैं, जबकि गांधीनगर हाईवे और अपोलो अस्पताल की निकटता से 2 व 3 बीएचके फ्लैट्स में स्थिर विकास बना हुआ है।",
        "price_drivers": ["ONGC & IIT Gandhinagar Demand", "Balanced Mid-Tier Housing Supply", "Apollo Hospital Connectivity"]
    },
    "Gota": {
        "explanation_en": "Gota is a bustling high-density residential hotspot along the northern SG Highway corridor. Affordable to mid-tier multi-storey developments provide accessible entry points. High builder competition balances pricing, while quick connectivity to High Court and Ring Road supports solid rental yields.",
        "explanation_hi": "गोटा उत्तरी एसजी हाईवे पर स्थित एक तेजी से विकसित होता हुआ आवासीय हब है। यहां बहुमंजिला हाउसिंग प्रोजेक्ट्स किफायती और मध्यम दरों पर उपलब्ध हैं। गुजरात हाईकोर्ट और एसजी हाईवे से त्वरित जुड़ाव के कारण यहां किराये और रीसेल की मांग काफी मजबूत है।",
        "price_drivers": ["High Builder Competition (Fair Pricing)", "Gujarat High Court & SG Highway Proximity", "Strong Rental Yields"]
    },
    "Vaishnodevi": {
        "explanation_en": "Vaishnodevi Circle is an appreciating junction linking SG Highway, SP Ring Road, and the Gandhinagar highway. Large-scale integrated townships and premium high-rise developments command mid-to-high pricing. Proximity to Nirma University and Adani Shantigram drives high demand for 3 BHK homes.",
        "explanation_hi": "वैष्णोदेवी सर्कल एसजी हाईवे और एसपी रिंग रोड का एक प्रमुख रणनीतिक जंक्शन है। निरमा यूनिवर्सिटी और बड़े इंटीग्रेटेड टाउनशिप प्रोजेक्ट्स के कारण यहां 3 बीएचके अपार्टमेंट्स की अच्छी मांग है और कीमतों में तेजी से बढ़ोतरी हो रही है।",
        "price_drivers": ["Strategic Twin-City Junction", "Integrated Townships & Shantigram", "Nirma University Educational Hub"]
    },
    "Jagatpur": {
        "explanation_en": "Jagatpur is a flourishing residential micro-market adjacent to Godrej Garden City. High supply of modern multi-storey apartments offers competitive pricing per square yard. Broad tree-lined township roads and proximity to KD Hospital make it popular among first-time homebuyers.",
        "explanation_hi": "जगतपुर गोदरेज गार्डन सिटी के पास एक हरा-भरा और सुनियोजित आवासीय क्षेत्र है। आधुनिक हाई-राइज फ्लैट्स की भरपूर उपलब्धता के कारण यहां कीमतें बजट अनुकूल हैं। चौड़ी सड़कें, स्कूल और केडी अस्पताल की निकटता इसे नए परिवारों के लिए उपयुक्त बनाती है।",
        "price_drivers": ["Township Environment & Greenery", "Competitive Per-Sq-Yard Rates", "KD Hospital Healthcare Access"]
    },
    "Tragad": {
        "explanation_en": "Tragad offers budget-friendly suburban living near IOC Road and Chandkheda. Balanced builder inventory prevents aggressive price spikes, making standard 2 and 3 BHK units accessible to young families. Direct road links to SG Highway provide easy commutes.",
        "explanation_hi": "त्रागड़ आईओसी रोड के पास स्थित एक किफायती उपनगरीय क्षेत्र है। संतुलित हाउसिंग सप्लाई के कारण यहां 2 और 3 बीएचके फ्लैट्स उचित दरों पर उपलब्ध हैं। एसजी हाईवे और चांदखेड़ा से सीधा संपर्क दैनिक आवागमन को सुगम बनाता है।",
        "price_drivers": ["Accessible Budget-Friendly 2/3 BHK", "IOC Road Arterial Access", "Low Density Suburban Feel"]
    },
    "Zundal": {
        "explanation_en": "Zundal is a strategic growth node on SP Ring Road North bridging Ahmedabad and Gandhinagar. Proximity to the state administrative capital and GIFT City transit routes fuels healthy price growth. Master-planned high-rises attract government and corporate professionals.",
        "explanation_hi": "झुंडाल एसपी रिंग रोड नॉर्थ पर अहमदाबाद और गांधीनगर को जोड़ने वाला एक रणनीतिक विकास क्षेत्र है। गिफ्ट सिटी और सचिवालय के निकट होने के कारण यहां सुनियोजित बहुमंजिला प्रोजेक्ट्स में कीमतों की अच्छी बढ़ोतरी देखी जा रही है।",
        "price_drivers": ["Gandhinagar Capital Bridge", "SP Ring Road Expansion", "GIFT City Commute Advantage"]
    },
    "Chandlodiya": {
        "explanation_en": "Chandlodiya provides affordable, central suburban residential housing. Proximity to Chandlodiya Railway Station and 132ft Ring Road maintains solid connectivity. Dense existing development limits new supply, maintaining steady and accessible price levels.",
        "explanation_hi": "चांदलोदिया एक किफायती और सुलभ आवासीय क्षेत्र है। रेलवे स्टेशन और 132 फीट रिंग रोड की निकटता दैनिक यात्रियों के लिए सुविधाजनक है। सीमित नई जमीन के चलते यहां कीमतें स्थिर और आम बजट के अनुकूल रहती हैं।",
        "price_drivers": ["Suburban Railway Connectivity", "132ft Ring Road Feeder", "High Density Affordable Base"]
    },
    "Navrangpura": {
        "explanation_en": "Navrangpura is the historic institutional and educational core of Ahmedabad, housing Gujarat University and CEPT. Land scarcity is absolute, driving premium pricing through high-end society redevelopment projects. SVP Hospital and operational Metro stations support strong property values.",
        "explanation_hi": "नवरंगपुरा गुजरात यूनिवर्सिटी और सीईपीटी के पास स्थित अहमदाबाद का प्रमुख शैक्षणिक व सांस्कृतिक केंद्र है। खाली जमीन की पूरी कमी के कारण यहां पुरानी सोसायटियों का प्रीमियम रीडेवलपमेंट हो रहा है, जिससे नए फ्लैट्स की कीमतें काफी उच्च स्तर पर हैं।",
        "price_drivers": ["Absolute Land Scarcity", "High-End Society Redevelopment", "Gujarat University & CEPT Precinct"]
    },
    "Paldi": {
        "explanation_en": "Paldi is a culturally rich, central micro-market near the Sabarmati Riverfront and NID. High demand for independent community housing and low new inventory keep prices in the mid-premium range. Paldi Metro Station and central bridge connectivity reinforce high livability.",
        "explanation_hi": "पालदी साबरमती रिवरफ्रंट और एनआईडी के पास स्थित एक शांत और प्रतिष्ठित इलाका है। नई जमीनों की कमी और मजबूत सामुदायिक मांग के कारण यहां प्रॉपर्टी के दाम मध्यम-प्रीमियम श्रेणी में स्थिर हैं। पालदी मेट्रो स्टेशन इसे बेहतरीन कनेक्टिविटी प्रदान करता है।",
        "price_drivers": ["Riverfront West Promenade", "Paldi Metro Interchange", "Strong Heritage & Community Trust"]
    },
    "Ellisbridge": {
        "explanation_en": "Ellisbridge holds heritage value directly bordering the Sabarmati Riverfront Promenade and Atal Bridge. Redevelopment of classic residential pockets commands significant per-sqft premiums. SVP Multi-speciality Hospital and central location preserve enduring real estate value.",
        "explanation_hi": "एलिसब्रिज साबरमती रिवरफ्रंट और अटल ब्रिज से सटा एक ऐतिहासिक और केंद्रीय क्षेत्र है। पुराने मकानों के आधुनिक बहुमंजिला इमारतों में पुनर्विकास से यहां अच्छी कीमतें मिल रही हैं। एसवीपी सुपर-स्पेशलिटी अस्पताल और केंद्रीय स्थिति इसकी मजबूती का आधार हैं।",
        "price_drivers": ["Atal Bridge & Riverfront Views", "SVP Multi-Speciality Hospital", "Central Business District Links"]
    },
    "Maninagar": {
        "explanation_en": "Maninagar is the primary cultural and residential hub of East Ahmedabad around Kankaria Lake. Dense existing occupancy leaves minimal open land, driving prices via society reconstruction. Direct Railway and Metro Phase-1 connectivity ensure strong end-user demand.",
        "explanation_hi": "मणिनगर कांकरिया झील के निकट पूर्वी अहमदाबाद का सबसे प्रमुख और सुविकसित आवासीय क्षेत्र है। खुली जमीन न होने के कारण पुनर्विकास प्रोजेक्ट्स की मांग अधिक है। रेलवे स्टेशन और मेट्रो कनेक्टिविटी के कारण यहां संपत्तियों के दाम स्थिर और मजबूत हैं।",
        "price_drivers": ["Kankaria Lake Tourist & Cultural Anchor", "Maninagar Railway Terminal & Metro", "East Ahmedabad Prime Anchor"]
    },
    "Nikol": {
        "explanation_en": "Nikol is a high-growth eastern suburb with extensive modern high-rise societies. Competitive builder supply keeps rates affordable-to-mid, while Nikol Lake Garden and SP Ring Road access drive steady appreciation for 2 and 3 BHK family apartments.",
        "explanation_hi": "निकोल पूर्वी अहमदाबाद का एक तेजी से बढ़ता हुआ उपनगर है जहां आधुनिक हाई-राइज अपार्टमेंट्स उचित दरों पर उपलब्ध हैं। निकोल लेक गार्डन और एसपी रिंग रोड से सीधी कनेक्टिविटी के कारण यह पारिवारिक खरीदारों के बीच बेहद लोकप्रिय है।",
        "price_drivers": ["Modern High-Rise Cluster Growth", "SP Ring Road Eastern Arm", "Nikol Lake Garden Ecosystem"]
    },
    "Naroda": {
        "explanation_en": "Naroda is an established industrial and residential cluster in northeast Ahmedabad. Proximity to Naroda GIDC and Airport road provides steady entry-level homebuyer demand. Affordable pricing makes it an accessible market for first-time owners.",
        "explanation_hi": "नरोडा जीआईडीसी और एयरपोर्ट रोड के निकट स्थित एक प्रमुख औद्योगिक व आवासीय क्षेत्र है। किफायती दरों और मजबूत रोजगार अवसरों के कारण यहां शुरुआती बजट वाले घर खरीदारों की निरंतर मांग बनी रहती है।",
        "price_drivers": ["Naroda GIDC Industrial Employment", "Airport Road Access", "Entry-Level Homeownership"]
    },
    "Vastral": {
        "explanation_en": "Vastral was the pioneer beneficiary of Ahmedabad Metro Line 1. Ready metro access and SP Ring Road entry have created solid appreciation in affordable high-rise apartments, offering attractive value for working-class families.",
        "explanation_hi": "वस्त्राल अहमदाबाद मेट्रो लाइन-1 से सीधे जुड़े होने का प्रमुख लाभ उठाता है। मेट्रो स्टेशन और एसपी रिंग रोड की पहुंच के चलते यहां किफायती बहुमंजिला अपार्टमेंट्स में स्थिर वृद्धि देखने को मिल रही है।",
        "price_drivers": ["Metro Line-1 Ready Transit", "Affordable Multi-Storey Supply", "SP Ring Road Eastern Tollway"]
    },
    "Odhav": {
        "explanation_en": "Odhav is a primary industrial corridor with affordable residential housing clusters. Metro rail connectivity at Apparel Park and BRTS routes provide affordable commutes. Prices remain attractive for entry-level residential investors.",
        "explanation_hi": "ओढव प्रमुख औद्योगिक इकाइयों और बजट हाउसिंग सोसायटियों का केंद्र है। मेट्रो और बीआरटीएस नेटवर्क से जुड़े होने के कारण यहां रहने का खर्च और प्रॉपर्टी की दरें काफी किफायती और व्यावहारिक हैं।",
        "price_drivers": ["Odhav Industrial Employment", "Affordable Living Index", "BRTS & Metro Feeder Routes"]
    }
}


def get_locality_price_explanation(locality_name):
    """Retrieve structured bilingual price explanation for any Ahmedabad locality from MongoDB (or fallback catalog)."""
    clean = (locality_name or "").strip()
    
    # 1. Query MongoDB first
    mongo_doc = database.get_price_explanation(clean)
    if mongo_doc and mongo_doc.get("explanation_en"):
        return {
            "explanation_en": mongo_doc["explanation_en"],
            "explanation_hi": mongo_doc.get("explanation_hi") or "",
            "price_drivers": mongo_doc.get("price_drivers") or []
        }

    # 2. Check in-memory catalog exact match
    if clean in LOCALITY_PRICE_EXPLANATIONS:
        return LOCALITY_PRICE_EXPLANATIONS[clean]
        
    # 3. Check case-insensitive match
    for k, v in LOCALITY_PRICE_EXPLANATIONS.items():
        if k.lower() == clean.lower():
            return v
            
    # 4. Fallback explanation
    return {
        "explanation_en": f"Property valuations in {clean} reflect localized micro-market dynamics, infrastructural connectivity, builder inventory density, and ongoing residential redevelopment in Ahmedabad.",
        "explanation_hi": f"{clean} में संपत्ति का मूल्यांकन स्थानीय बाजार की मांग, बुनियादी ढांचे, बिल्डर्स की आपूर्ति और अहमदाबाद में चल रहे आवासीय पुनर्विकास पर आधारित है।",
        "price_drivers": ["Micro-Market Supply & Demand", "Civic & Transit Connectivity", "Ahmedabad Urban Growth Corridor"]
    }


# ---------------------------------------------------------------------------
# Valuation Engine with Property Types & Rich Intelligence
# ---------------------------------------------------------------------------

def calculate_property_valuation(locality_name, area_value, unit="sqyd", property_type="Apartment / Flat", year=2026):
    """
    Comprehensive valuation calculation:
    - Supports Apartment / Flat (1.0x) and Tenement / Duplex (1.28x)
    - Returns formatted Indian Currency numbers (Lakhs & Crores)
    - Fetches rich locality metadata (Landmarks, Schools, Transit, Livability)
    - Generates 5-year future projections
    - Retrieves real historical price trends
    - Provides dynamic bilingual price-context explanations (English & Devanagari Hindi)
    """
    try:
        area_float = float(area_value)
        if area_float <= 0:
            return {"success": False, "error": "Area must be a positive number."}
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid area value."}

    # Normalize area to sq. yards
    if unit.lower() in ["sqft", "sq.ft", "sq feet"]:
        area_sqyd = area_float / SQYD_TO_SQFT
        area_sqft = area_float
    else:
        area_sqyd = area_float
        area_sqft = area_float * SQYD_TO_SQFT

    # Lookup locality in DB
    loc_db = database.get_locality_by_name(locality_name)
    if not loc_db:
        # Check all localities
        all_locs = database.get_all_localities()
        matched = next((l for l in all_locs if l["name"].lower() == locality_name.lower().strip()), None)
        if matched:
            loc_db = matched
        else:
            return {"success": False, "error": f"Locality '{locality_name}' not found in Ahmedabad database."}

    clean_loc_name = loc_db["name"]
    multiplier = PROPERTY_TYPE_MULTIPLIERS.get(property_type, 1.0)

    # Use database live rate if available for base year 2026, or ML model prediction
    if loc_db and loc_db.get("rate_per_sqft") and year == 2026:
        rate_sqft = round(loc_db["rate_per_sqft"] * multiplier, 2)
        rate_sqyd = round(loc_db["rate_per_sqyd"] * multiplier, 2)
        total_price = round(rate_sqyd * area_sqyd, 2)
        yoy_pct = loc_db.get("yoy_percent") or 6.0
    else:
        val_data = ml_model.predict_purchase(clean_loc_name, area_sqyd, property_type, year)
        total_price = val_data["total_price"]
        rate_sqyd = val_data["rate_per_sqyd"]
        rate_sqft = val_data["rate_per_sqft"]
        yoy_pct = loc_db.get("yoy_percent") or val_data["annual_growth_rate_pct"]

    # 5-Year Projection (compounding from current rate)
    projections = []
    base_val = total_price
    for i in range(1, 6):
        proj_year = year + i
        comp_factor = (1.0 + (yoy_pct / 100.0)) ** i
        proj_sqyd = round(rate_sqyd * comp_factor, 2)
        proj_sqft = round(rate_sqft * comp_factor, 2)
        proj_total = round(total_price * comp_factor, 2)
        gain = proj_total - base_val
        gain_pct = round(((comp_factor - 1.0) * 100.0), 2)
        projections.append({
            "year": proj_year,
            "year_label": f"Year +{i} ({proj_year})",
            "rate_per_sqyd": proj_sqyd,
            "rate_per_sqft": proj_sqft,
            "estimated_value": proj_total,
            "gain_from_current": round(gain, 2),
            "gain_percent": gain_pct
        })
    for p in projections:
        p["estimated_value_formatted"] = format_inr(p["estimated_value"])
        p["estimated_value_full"] = format_inr_full(p["estimated_value"])
        p["rate_per_sqyd_formatted"] = format_inr(p["rate_per_sqyd"])
        p["rate_per_sqft_formatted"] = format_inr(p["rate_per_sqft"])

    # Historical trend points from DB or ML
    hist_points_db = database.get_historical_trends(clean_loc_name)
    if hist_points_db:
        # Apply property multiplier if Tenement/Duplex
        hist_trend = {
            "locality": clean_loc_name,
            "has_real_history": True,
            "points": [
                {
                    "year": h["year"],
                    "rate_per_sqft": round(h["rate_per_sqft"] * multiplier, 2),
                    "rate_per_sqyd": round(h["rate_per_sqyd"] * multiplier, 2),
                    "source": h["source"]
                }
                for h in hist_points_db
            ]
        }
    else:
        raw_trend = ml_model.get_historical_trend(clean_loc_name)
        hist_trend = {
            "locality": clean_loc_name,
            "has_real_history": raw_trend["has_real_history"],
            "points": [
                {
                    "year": h["year"],
                    "rate_per_sqft": round(h["rate_per_sqft"] * multiplier, 2),
                    "rate_per_sqyd": round(h["rate_per_sqyd"] * multiplier, 2),
                    "source": h["source"]
                }
                for h in raw_trend["points"]
            ]
        }

    # Growth pace verdict
    yoy_pct = loc_db.get("yoy_percent") or (val_data["annual_growth_rate_pct"] if "val_data" in locals() else 6.0)
    if yoy_pct >= 6.5:
        growth_verdict = "High Growth Corridor (Fast Pace)"
        growth_badge = "High Growth"
    elif yoy_pct >= 5.0:
        growth_verdict = "Steady Appreciation (Moderate Pace)"
        growth_badge = "Steady Growth"
    else:
        growth_verdict = "Mature & Stable Corridor (Consistent Pace)"
        growth_badge = "Stable"

    # Fetch structured bilingual price explanation
    price_exp = get_locality_price_explanation(clean_loc_name)

    return {
        "success": True,
        "locality": clean_loc_name,
        "zone": loc_db["zone"],
        "tier": loc_db["tier"],
        "livability_score": loc_db["livability_score"],
        "property_type": property_type,
        "property_multiplier": multiplier,
        "is_tenement": multiplier > 1.0,
        "area_sqyd": round(area_sqyd, 2),
        "area_sqft": round(area_sqft, 2),
        "rate_per_sqyd": rate_sqyd,
        "rate_per_sqft": rate_sqft,
        "rate_per_sqyd_formatted": format_inr(rate_sqyd),
        "rate_per_sqft_formatted": format_inr(rate_sqft),
        "total_price": total_price,
        "total_price_formatted": format_inr(total_price),
        "total_price_full": format_inr_full(total_price),
        "yoy_percent": round(yoy_pct, 2),
        "growth_verdict": growth_verdict,
        "growth_badge": growth_badge,
        "five_year_projection_total": projections[-1]["estimated_value_formatted"] if projections else "",
        "five_year_projections": projections,
        "historical_trends": hist_trend,
        "price_explanation_en": price_exp["explanation_en"],
        "price_explanation_hi": price_exp["explanation_hi"],
        "price_drivers": price_exp.get("price_drivers", []),
        "locality_intelligence": {
            "note": loc_db["note"],
            "landmarks": [item.strip() for item in (loc_db["landmarks"] or "").split(",") if item.strip()],
            "schools_hospitals": [item.strip() for item in (loc_db["schools_hospitals"] or "").split(",") if item.strip()],
            "transit": loc_db["transit"],
            "data_source": loc_db["data_source"]
        }
    }


def send_valuation_email(recipient_email, details):
    """
    Send property price calculation report directly to the recipient's email address.
    Includes:
      - Approximate price disclaimer
      - Area / Locality selected
      - Calculated size (in sq. yards and sq. feet)
      - Calculated price (formatted and full INR)
      - Date & time of calculation
    """
    load_email_config()

    recipient_email = str(recipient_email or "").strip()
    if not recipient_email or not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", recipient_email):
        return {"success": False, "error": "Please provide a valid recipient email address."}

    # Extract & sanitize valuation attributes
    locality = str(details.get("locality") or "Ahmedabad Micro-Market").strip()
    property_type = str(details.get("property_type") or "Apartment / Flat").strip()
    area_sqyd = details.get("area_sqyd")
    try:
        area_sqyd_val = float(area_sqyd) if area_sqyd is not None else 0.0
    except (ValueError, TypeError):
        area_sqyd_val = 0.0

    area_sqft_val = details.get("area_sqft") or (area_sqyd_val * SQYD_TO_SQFT)

    total_price = details.get("total_price")
    total_price_formatted = details.get("total_price_formatted") or (format_inr(total_price) if total_price else "₹0")
    total_price_full = details.get("total_price_full") or (format_inr_full(total_price) if total_price else "₹0")

    rate_per_sqyd_formatted = details.get("rate_per_sqyd_formatted") or "N/A"
    rate_per_sqft_formatted = details.get("rate_per_sqft_formatted") or "N/A"
    zone = details.get("zone") or "Ahmedabad"
    tier = details.get("tier") or "Prime"

    # Calculation timestamp in IST (Indian Standard Time: UTC+5:30)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz)
    calc_time_str = details.get("calculated_at") or now_ist.strftime("%d %B %Y, %I:%M %p IST")

    disclaimer_text = (
        "DISCLAIMER: This property price valuation is an approximate estimation generated by algorithmic "
        "machine-learning models and current micro-market data points. It is provided exclusively for informational "
        "and preliminary planning purposes, and must not be considered a legally certified valuation, official bank "
        "appraisal, or financial guarantee. Actual transaction values may vary based on specific building specifications, "
        "road frontage, floor rise, negotiation, and legal due diligence."
    )

    subject = f"Vasudha Real Estate — Property Valuation Report: {locality} ({total_price_formatted})"

    # Luxury HTML email layout
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body {{
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
          background-color: #03060c;
          color: #f8fafc;
          margin: 0;
          padding: 24px;
        }}
        .email-wrapper {{
          max-width: 620px;
          margin: 0 auto;
          background: #0b1220;
          border: 1px solid #c9922e;
          border-radius: 14px;
          overflow: hidden;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
        }}
        .header {{
          background: linear-gradient(135deg, #0f1a2e 0%, #060b14 100%);
          padding: 28px 32px;
          border-bottom: 1px solid #c9922e;
          text-align: center;
        }}
        .brand {{
          font-size: 24px;
          font-weight: 800;
          letter-spacing: 3px;
          color: #f5d77f;
          text-transform: uppercase;
          margin: 0;
        }}
        .subbrand {{
          font-size: 12px;
          color: #c9922e;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          margin-top: 6px;
        }}
        .content {{
          padding: 32px;
        }}
        .hero-price-card {{
          background: linear-gradient(140deg, #131d31 0%, #0c1424 100%);
          border: 1px solid rgba(201, 146, 46, 0.4);
          border-radius: 10px;
          padding: 24px;
          text-align: center;
          margin-bottom: 24px;
        }}
        .price-badge {{
          display: inline-block;
          background: rgba(201, 146, 46, 0.15);
          color: #f5d77f;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          padding: 4px 12px;
          border-radius: 20px;
          border: 1px solid rgba(201, 146, 46, 0.3);
          margin-bottom: 10px;
        }}
        .hero-price {{
          font-size: 38px;
          font-weight: 800;
          color: #f5d77f;
          margin: 6px 0;
          letter-spacing: -0.5px;
        }}
        .hero-subprice {{
          font-size: 14px;
          color: #94a3b8;
        }}
        .spec-table {{
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 24px;
        }}
        .spec-table td {{
          padding: 12px 14px;
          border-bottom: 1px solid #1a273f;
          font-size: 14px;
        }}
        .spec-label {{
          color: #94a3b8;
          font-weight: 500;
          width: 42%;
        }}
        .spec-value {{
          color: #f8fafc;
          font-weight: 600;
          text-align: right;
        }}
        .highlight {{
          color: #f5d77f;
        }}
        .disclaimer-card {{
          background: rgba(201, 146, 46, 0.08);
          border-left: 4px solid #c9922e;
          border-radius: 6px;
          padding: 16px 18px;
          margin-top: 24px;
        }}
        .disclaimer-title {{
          font-size: 12px;
          font-weight: 700;
          color: #f5d77f;
          letter-spacing: 1px;
          text-transform: uppercase;
          margin-bottom: 6px;
        }}
        .disclaimer-text {{
          font-size: 12px;
          color: #cbd5e1;
          line-height: 1.6;
          margin: 0;
        }}
        .timestamp-box {{
          text-align: center;
          margin-top: 20px;
          font-size: 12px;
          color: #64748b;
        }}
        .footer {{
          background: #060b14;
          padding: 20px 32px;
          border-top: 1px solid #1a273f;
          text-align: center;
          font-size: 12px;
          color: #64748b;
          line-height: 1.6;
        }}
        .footer a {{
          color: #c9922e;
          text-decoration: none;
        }}
      </style>
    </head>
    <body>
      <div class="email-wrapper">
        <div class="header">
          <div class="brand">VASUDHA REAL ESTATE</div>
          <div class="subbrand">Ahmedabad Property Valuation & Analytics Platform</div>
        </div>
        <div class="content">
          <p style="margin-top: 0; font-size: 15px; color: #e2e8f0;">
            Hello,
          </p>
          <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
            Here is the summary of the property valuation calculation generated on Vasudha Real Estate for your review:
          </p>

          <div class="hero-price-card">
            <div class="price-badge">Valuation Estimate</div>
            <div class="hero-price">{total_price_formatted}</div>
            <div class="hero-subprice">Total Estimated Market Value: {total_price_full} (INR)</div>
          </div>

          <table class="spec-table">
            <tr>
              <td class="spec-label">Selected Area / Locality</td>
              <td class="spec-value highlight">{locality} ({zone} Zone • {tier})</td>
            </tr>
            <tr>
              <td class="spec-label">Property Type</td>
              <td class="spec-value">{property_type}</td>
            </tr>
            <tr>
              <td class="spec-label">Calculated Area (Size)</td>
              <td class="spec-value highlight">{area_sqyd_val:,.1f} Sq. Yards (Gaj) <span style="color: #94a3b8; font-weight: normal;">({area_sqft_val:,.0f} Sq.ft)</span></td>
            </tr>
            <tr>
              <td class="spec-label">Rate per Sq. Yard (Gaj)</td>
              <td class="spec-value">{rate_per_sqyd_formatted}</td>
            </tr>
            <tr>
              <td class="spec-label">Rate per Sq. Foot</td>
              <td class="spec-value">{rate_per_sqft_formatted}</td>
            </tr>
            <tr>
              <td class="spec-label">Calculation Date & Time</td>
              <td class="spec-value" style="font-size: 13px;">{calc_time_str}</td>
            </tr>
          </table>

          <div class="disclaimer-card">
            <div class="disclaimer-title">⚠️ Important Notice & Disclaimer</div>
            <p class="disclaimer-text">{disclaimer_text}</p>
          </div>

          <div class="timestamp-box">
            Generated via Vasudha Valuation Engine on {calc_time_str}
          </div>
        </div>

        <div class="footer">
          Architected & Engineered for Ahmedabad Property Price Discovery<br>
          Developed by <strong>Patel Om</strong> • Support: <a href="mailto:Vasudha.realestate.01@gmail.com">Vasudha.realestate.01@gmail.com</a><br>
          © 2026 Vasudha Real Estate. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    plain_content = f"""VASUDHA REAL ESTATE — PROPERTY VALUATION REPORT
===========================================================
Estimated Market Value: {total_price_formatted} ({total_price_full} INR)

PROPERTY VALUATION DETAILS:
- Locality / Area Selected: {locality} ({zone} Zone • {tier})
- Property Type:            {property_type}
- Calculated Size:          {area_sqyd_val:,.1f} Sq. Yards (Gaj) [{area_sqft_val:,.0f} Sq. Feet]
- Rate per Sq. Yard:        {rate_per_sqyd_formatted}
- Rate per Sq. Foot:        {rate_per_sqft_formatted}
- Date & Time Generated:    {calc_time_str}

===========================================================
DISCLAIMER:
{disclaimer_text}
===========================================================
© 2026 Vasudha Real Estate • Official Support: Vasudha.realestate.01@gmail.com
"""

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USERNAME", os.environ.get("GMAIL_USER", "Vasudha.realestate.01@gmail.com"))
    smtp_pass = os.environ.get("SMTP_PASSWORD", os.environ.get("GMAIL_APP_PASSWORD", "")).replace(" ", "")
    sender_email = os.environ.get("SMTP_SENDER", smtp_user or "Vasudha.realestate.01@gmail.com")

    email_sent = False
    error_msg = None

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Vasudha Real Estate <{sender_email}>"
            msg["To"] = recipient_email
            msg.attach(MIMEText(plain_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(sender_email, [recipient_email], msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(sender_email, [recipient_email], msg.as_string())

            email_sent = True
            print(f"[Valuation Share SUCCESS] Report successfully delivered to {recipient_email} via SMTP ({smtp_host}:{smtp_port}).")
        except Exception as e:
            error_msg = str(e)
            print(f"[Valuation Share Error] SMTP delivery failed: {e}. Falling back to console dispatch.")

    if not email_sent:
        print("=" * 60)
        print(f"[DEMO / DEV MODE VALUATION REPORT] Recipient: {recipient_email}")
        print(f"[Locality]: {locality} | [Size]: {area_sqyd_val} Sq.yd | [Price]: {total_price_formatted}")
        print(f"[Timestamp]: {calc_time_str}")
        print(f"[Disclaimer]: {disclaimer_text[:80]}...")
        if error_msg:
            print(f"[Notice]: SMTP error: {error_msg}")
        print("=" * 60)

    return {
        "success": True,
        "email_sent_via_smtp": email_sent,
        "recipient": recipient_email,
        "calculated_at": calc_time_str,
        "locality": locality,
        "area_sqyd": area_sqyd_val,
        "total_price_formatted": total_price_formatted,
        "message": f"Valuation report successfully sent to {recipient_email}."
    }


if __name__ == "__main__":
    database.init_db()
    res = calculate_property_valuation("Shela", 150, "sqyd", "Apartment / Flat")
    print("Valuation Test (Shela Flat):", res["total_price_formatted"].replace("\u20b9", "Rs "), "|", res["growth_verdict"])
    res2 = calculate_property_valuation("Shela", 150, "sqyd", "Tenement / Duplex")
    print("Valuation Test (Shela Duplex):", res2["total_price_formatted"].replace("\u20b9", "Rs "), "| Land Multiplier:", res2["property_multiplier"])
