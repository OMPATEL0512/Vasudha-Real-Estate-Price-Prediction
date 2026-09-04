"""
Vasudha Real Estate — Database Layer (MongoDB & SQLite Hybrid Engine)
Seamlessly connects to MongoDB (default) with automatic fallback to SQLite.
Handles schema/index definition, CRUD operations for users, localities,
and multi-year historical trend points.
"""

import os
import sys
import re
import sqlite3
from datetime import datetime, timezone

def re_escape(s):
    """Safely escape strings for regex queries."""
    return re.escape(str(s or ""))

# Optional PyMongo import with graceful degradation
try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.errors import DuplicateKeyError, ConnectionFailure, ServerSelectionTimeoutError
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration & Engine Detection
# ---------------------------------------------------------------------------
DB_ENGINE_CONFIG = os.environ.get("DB_ENGINE", "mongodb").strip().lower()
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/").strip()
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "vasudha_real_estate").strip()
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "vasudha.db")

_mongo_client = None
_mongo_db = None
_active_engine = None  # "mongodb" or "sqlite"


def get_mongo_db():
    """Return MongoDB database handle if available and connected."""
    global _mongo_client, _mongo_db, _active_engine
    if not PYMONGO_AVAILABLE:
        return None

    if _mongo_db is not None:
        return _mongo_db

    try:
        # Connect with a 2-second timeout to avoid blocking on startup
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2500)
        # Test connection with a ping
        _mongo_client.admin.command("ping")
        _mongo_db = _mongo_client[MONGO_DB_NAME]
        _active_engine = "mongodb"
        return _mongo_db
    except Exception as e:
        print(f"[Database Notice] MongoDB connection to '{MONGO_URI}' not active ({e}). Using SQLite fallback.")
        _mongo_client = None
        _mongo_db = None
        _active_engine = "sqlite"
        return None


def is_mongodb_active():
    """Check if MongoDB is actively selected and connected."""
    if DB_ENGINE_CONFIG == "sqlite":
        return False
    return get_mongo_db() is not None


def get_active_engine_name():
    """Return friendly name of currently active database engine."""
    if is_mongodb_active():
        return f"MongoDB ({MONGO_DB_NAME} @ {MONGO_URI})"
    return f"SQLite ({SQLITE_DB_PATH})"


# ---------------------------------------------------------------------------
# SQLite Helpers
# ---------------------------------------------------------------------------

def get_sqlite_connection():
    """Return a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_sqlite_tables():
    """Initialize SQLite database tables as fallback/backup."""
    conn = get_sqlite_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            surname TEXT,
            age INTEGER,
            phone TEXT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # Deduplicate existing legacy rows if any before creating unique index
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone 
            ON users(phone) 
            WHERE phone IS NOT NULL AND phone != '';
        """)
    except sqlite3.IntegrityError:
        # If existing test records have duplicate phones, keep the latest one per phone
        cursor.execute("""
            DELETE FROM users 
            WHERE id NOT IN (
                SELECT MAX(id) FROM users GROUP BY phone
            ) AND phone IS NOT NULL AND phone != '';
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone 
            ON users(phone) 
            WHERE phone IS NOT NULL AND phone != '';
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS localities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            zone TEXT NOT NULL,
            tier TEXT NOT NULL,
            rate_per_sqyd REAL NOT NULL,
            rate_per_sqft REAL NOT NULL,
            yoy_percent REAL,
            projected_5yr REAL,
            note TEXT,
            landmarks TEXT,
            schools_hospitals TEXT,
            transit TEXT,
            livability_score REAL,
            data_source TEXT,
            price_explanation_en TEXT,
            price_explanation_hi TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            locality_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            rate_per_sqft REAL NOT NULL,
            rate_per_sqyd REAL NOT NULL,
            source TEXT,
            UNIQUE(locality_name, year)
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MongoDB Indexes & Auto-Migration
# ---------------------------------------------------------------------------

def _get_next_sequence(sequence_name):
    """Generate atomic auto-increment integer ID in MongoDB."""
    db = get_mongo_db()
    if db is None:
        return 1
    counter = db["counters"].find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    return counter["seq"]


def _init_mongo_indexes():
    """Initialize MongoDB collections, indexes, and unique constraints."""
    db = get_mongo_db()
    if db is None:
        return

    # 1. Users indexes
    db["users"].create_index([("email", ASCENDING)], unique=True)
    db["users"].create_index([("username", ASCENDING)], unique=True)
    db["users"].create_index([("phone", ASCENDING)], unique=True, sparse=True)
    db["users"].create_index([("id", ASCENDING)], unique=True)

    # 2. Localities index
    db["localities"].create_index([("name", ASCENDING)], unique=True)
    db["localities"].create_index([("zone", ASCENDING)])

    # 3. Historical Trends compound index
    db["historical_trends"].create_index(
        [("locality_name", ASCENDING), ("year", ASCENDING)],
        unique=True
    )

    # 4. Price Explanations index
    db["price_explanations"].create_index([("locality_name", ASCENDING)], unique=True)


def migrate_sqlite_to_mongodb(verbose=True):
    """Migrate all data from SQLite database file into MongoDB."""
    db = get_mongo_db()
    if db is None:
        if verbose:
            print("[Migration Error] Cannot migrate: MongoDB is not connected.")
        return False

    if not os.path.exists(SQLITE_DB_PATH):
        if verbose:
            print(f"[Migration Notice] No SQLite file found at {SQLITE_DB_PATH}.")
        return False

    _init_mongo_indexes()

    try:
        conn = get_sqlite_connection()
        cursor = conn.cursor()

        # Migrate Users
        cursor.execute("SELECT * FROM users ORDER BY id ASC")
        users = [dict(r) for r in cursor.fetchall()]
        user_migrated = 0
        max_user_id = 0
        for u in users:
            uid = int(u["id"])
            if uid > max_user_id:
                max_user_id = uid
            existing = db["users"].find_one({"$or": [{"email": u["email"].lower().strip()}, {"username": u["username"].strip()}]})
            if not existing:
                doc = {
                    "id": uid,
                    "first_name": u.get("first_name", ""),
                    "surname": u.get("surname", ""),
                    "age": u.get("age"),
                    "phone": u.get("phone", ""),
                    "email": u["email"].lower().strip(),
                    "username": u["username"].strip(),
                    "password_hash": u["password_hash"],
                    "created_at": u.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "updated_at": u.get("updated_at") or datetime.now(timezone.utc).isoformat()
                }
                db["users"].insert_one(doc)
                user_migrated += 1

        # Synchronize counter sequence for users
        if max_user_id > 0:
            db["counters"].update_one(
                {"_id": "user_id"},
                {"$set": {"seq": max_user_id}},
                upsert=True
            )

        # Migrate Localities
        cursor.execute("SELECT * FROM localities")
        locs = [dict(r) for r in cursor.fetchall()]
        loc_migrated = 0
        for l in locs:
            name = l["name"].strip()
            db["localities"].update_one(
                {"name": name},
                {"$set": {
                    "name": name,
                    "zone": l.get("zone", ""),
                    "tier": l.get("tier", ""),
                    "rate_per_sqyd": float(l.get("rate_per_sqyd", 0)),
                    "rate_per_sqft": float(l.get("rate_per_sqft", 0)),
                    "yoy_percent": float(l["yoy_percent"]) if l.get("yoy_percent") is not None else None,
                    "projected_5yr": float(l["projected_5yr"]) if l.get("projected_5yr") is not None else None,
                    "note": l.get("note", ""),
                    "landmarks": l.get("landmarks", ""),
                    "schools_hospitals": l.get("schools_hospitals", ""),
                    "transit": l.get("transit", ""),
                    "livability_score": float(l["livability_score"]) if l.get("livability_score") is not None else None,
                    "data_source": l.get("data_source", ""),
                    "updated_at": l.get("updated_at") or datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            loc_migrated += 1

        # Migrate Historical Trends
        cursor.execute("SELECT * FROM historical_trends")
        trends = [dict(r) for r in cursor.fetchall()]
        trend_migrated = 0
        for t in trends:
            loc_name = t["locality_name"].strip()
            year = int(t["year"])
            db["historical_trends"].update_one(
                {"locality_name": loc_name, "year": year},
                {"$set": {
                    "locality_name": loc_name,
                    "year": year,
                    "rate_per_sqft": float(t.get("rate_per_sqft", 0)),
                    "rate_per_sqyd": float(t.get("rate_per_sqyd", 0)),
                    "source": t.get("source", "")
                }},
                upsert=True
            )
            trend_migrated += 1

        conn.close()
        if verbose:
            print(f"[MongoDB Migration Complete] {user_migrated} new users, {loc_migrated} localities, {trend_migrated} trends synchronized to MongoDB.")
        return True
    except Exception as e:
        if verbose:
            print(f"[Migration Error] Failed to migrate SQLite to MongoDB: {e}")
        return False


def sync_price_explanations_to_mongodb():
    """Sync all bilingual price explanations from backend catalog to MongoDB collection."""
    if not is_mongodb_active():
        return
    db = get_mongo_db()
    if db is None:
        return
    try:
        import backend
        now = datetime.now(timezone.utc).isoformat()
        for loc_name, data in getattr(backend, "LOCALITY_PRICE_EXPLANATIONS", {}).items():
            db["price_explanations"].update_one(
                {"locality_name": loc_name},
                {"$set": {
                    "locality_name": loc_name,
                    "explanation_en": data.get("explanation_en", ""),
                    "explanation_hi": data.get("explanation_hi", ""),
                    "price_drivers": data.get("price_drivers", []),
                    "updated_at": now
                }},
                upsert=True
            )
            # Also update into localities collection
            db["localities"].update_one(
                {"name": loc_name},
                {"$set": {
                    "price_explanation_en": data.get("explanation_en", ""),
                    "price_explanation_hi": data.get("explanation_hi", ""),
                    "price_drivers": data.get("price_drivers", []),
                    "updated_at": now
                }}
            )
    except Exception as e:
        print(f"[MongoDB Sync Notice] Price explanation sync skipped: {e}")


def get_price_explanation(locality_name):
    """Retrieve bilingual price explanation from MongoDB (or SQLite)."""
    clean = (locality_name or "").strip()
    if not clean:
        return None

    if is_mongodb_active():
        db = get_mongo_db()
        doc = db["price_explanations"].find_one({"locality_name": {"$regex": f"^{re_escape(clean)}$", "$options": "i"}})
        if doc:
            return _sanitize_mongo_doc(doc)

    return None


def init_db():
    """Initialize database tables, MongoDB collections, indexes, and initial data."""
    # Always ensure SQLite schema exists as fallback
    _init_sqlite_tables()

    if is_mongodb_active():
        db = get_mongo_db()
        _init_mongo_indexes()

        # Check if MongoDB is empty and sync from SQLite if available
        user_count = db["users"].count_documents({})
        loc_count = db["localities"].count_documents({})

        if loc_count == 0:
            if os.path.exists(SQLITE_DB_PATH):
                migrate_sqlite_to_mongodb(verbose=False)
            else:
                # Fallback to seeder if sqlite db is not present
                try:
                    import seed_data
                    seed_data.seed()
                except Exception:
                    pass

        # Sync bilingual price explanations to MongoDB
        sync_price_explanations_to_mongodb()

        print(f"[Database Active] Connected to MongoDB database '{MONGO_DB_NAME}' at {MONGO_URI}")
    else:
        try:
            conn = get_sqlite_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM localities")
            loc_cnt = cur.fetchone()[0]
            conn.close()
            if loc_cnt == 0:
                print("[Database Notice] SQLite database empty. Auto-seeding initial dataset...")
                import seed_data
                seed_data.seed()
        except Exception as se:
            print(f"[Database Warning] Auto-seed check notice: {se}")
        print(f"[Database Active] Connected to SQLite database at {SQLITE_DB_PATH}")


# ---------------------------------------------------------------------------
# User CRUD Operations
# ---------------------------------------------------------------------------

def create_user(first_name, surname, age, phone, email, username, password_hash):
    """Insert a new registered user into active database (MongoDB or SQLite)."""
    clean_email = email.lower().strip()
    clean_username = username.strip()
    now = datetime.now(timezone.utc).isoformat()

    if is_mongodb_active():
        db = get_mongo_db()
        try:
            # Check unique constraint proactively
            if db["users"].find_one({"email": clean_email}):
                return {"success": False, "error": "An account with this email already exists."}
            clean_phone = re.sub(r"[\s\-\+]", "", str(phone or "")).strip()
            if clean_phone and db["users"].find_one({"phone": clean_phone}):
                return {"success": False, "error": "This phone number is already registered."}
            if db["users"].find_one({"email": clean_email}):
                return {"success": False, "error": "An account with this email already exists."}
            if db["users"].find_one({"username": {"$regex": f"^{re_escape(clean_username)}$", "$options": "i"}}):
                return {"success": False, "error": "This username is already taken."}

            user_id = _get_next_sequence("user_id")
            doc = {
                "id": user_id,
                "first_name": first_name.strip(),
                "surname": surname.strip(),
                "age": int(age) if age else None,
                "phone": clean_phone,
                "email": clean_email,
                "username": clean_username,
                "password_hash": password_hash,
                "created_at": now,
                "updated_at": now
            }
            db["users"].insert_one(doc)
            return {"success": True, "user_id": user_id}
        except DuplicateKeyError as e:
            err_str = str(e)
            if "phone" in err_str:
                return {"success": False, "error": "This phone number is already registered."}
            elif "email" in err_str:
                return {"success": False, "error": "An account with this email already exists."}
            elif "username" in err_str:
                return {"success": False, "error": "This username is already taken."}
            return {"success": False, "error": "User already exists with given credentials."}
        except Exception as e:
            return {"success": False, "error": f"Database error: {str(e)}"}

    # SQLite Fallback
    clean_phone = re.sub(r"[\s\-\+]", "", str(phone or "")).strip()
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (first_name, surname, age, phone, email, username, password_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (first_name, surname, age, clean_phone, clean_email, clean_username, password_hash, now, now))
        conn.commit()
        user_id = cursor.lastrowid
        return {"success": True, "user_id": user_id}
    except sqlite3.IntegrityError as e:
        err_msg = str(e)
        if "users.phone" in err_msg or "UNIQUE constraint failed: users.phone" in err_msg:
            return {"success": False, "error": "This phone number is already registered."}
        elif "users.email" in err_msg or "UNIQUE constraint failed: users.email" in err_msg:
            return {"success": False, "error": "An account with this email already exists."}
        elif "users.username" in err_msg or "UNIQUE constraint failed: users.username" in err_msg:
            return {"success": False, "error": "This username is already taken."}
        return {"success": False, "error": "User already exists with given credentials."}
    finally:
        conn.close()


def _sanitize_mongo_doc(doc):
    """Convert Mongo document to standard dict, ensuring id field is populated."""
    if not doc:
        return None
    d = dict(doc)
    if "_id" in d:
        if "id" not in d or d["id"] is None:
            d["id"] = str(d["_id"])
        del d["_id"]
    return d


def re_escape(s):
    """Escape regex characters safely."""
    import re
    return re.escape(s)


def get_user_by_email(email):
    """Retrieve user record by email."""
    if not email:
        return None
    clean_email = email.lower().strip()

    if is_mongodb_active():
        db = get_mongo_db()
        doc = db["users"].find_one({"email": clean_email})
        return _sanitize_mongo_doc(doc)

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (clean_email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_username(username):
    """Retrieve user record by username."""
    if not username:
        return None
    clean_username = username.strip()

    if is_mongodb_active():
        db = get_mongo_db()
        doc = db["users"].find_one({"username": {"$regex": f"^{re_escape(clean_username)}$", "$options": "i"}})
        return _sanitize_mongo_doc(doc)

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = ?", (clean_username.lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Retrieve user record by user_id (int or string)."""
    if user_id is None:
        return None

    if is_mongodb_active():
        db = get_mongo_db()
        # Try finding by numeric id first, then fallback
        try:
            uid_int = int(user_id)
            doc = db["users"].find_one({"id": uid_int})
            if doc:
                return _sanitize_mongo_doc(doc)
        except (ValueError, TypeError):
            pass
        doc = db["users"].find_one({"id": user_id})
        return _sanitize_mongo_doc(doc)

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_password(email, new_password_hash):
    """Update password hash for a user during password reset."""
    clean_email = email.lower().strip()
    now = datetime.now(timezone.utc).isoformat()

    if is_mongodb_active():
        db = get_mongo_db()
        res = db["users"].update_one(
            {"email": clean_email},
            {"$set": {"password_hash": new_password_hash, "updated_at": now}}
        )
        return res.modified_count > 0 or res.matched_count > 0

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET password_hash = ?, updated_at = ?
        WHERE LOWER(email) = ?
    """, (new_password_hash, now, clean_email))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def email_or_username_exists(email, username, phone=None):
    """Check if email, username, or phone is already taken."""
    return check_user_credentials_exist(email, username, phone)


def check_user_credentials_exist(email, username, phone=None):
    """Check if email, username, or phone is already registered in DB."""
    import re
    clean_email = email.lower().strip() if email else ""
    clean_username = username.strip() if username else ""
    clean_phone = re.sub(r"[\s\-\+]", "", str(phone or "")).strip() if phone else ""

    if is_mongodb_active():
        db = get_mongo_db()
        if clean_phone:
            phone_match = db["users"].find_one({"phone": clean_phone})
            if phone_match:
                return "This phone number is already registered."
        if clean_email:
            email_match = db["users"].find_one({"email": clean_email})
            if email_match:
                return "An account with this email already exists."
        if clean_username:
            user_match = db["users"].find_one({"username": {"$regex": f"^{re_escape(clean_username)}$", "$options": "i"}})
            if user_match:
                return "This username is already taken."
        return None

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    if clean_phone:
        cursor.execute("""
            SELECT email, username, phone FROM users
            WHERE LOWER(email) = ? OR LOWER(username) = ? OR phone = ?
        """, (clean_email, clean_username.lower(), clean_phone))
    else:
        cursor.execute("""
            SELECT email, username, phone FROM users
            WHERE LOWER(email) = ? OR LOWER(username) = ?
        """, (clean_email, clean_username.lower()))
    rows = cursor.fetchall()
    conn.close()
    for row in rows:
        if clean_phone and row["phone"] == clean_phone:
            return "This phone number is already registered."
        if row["email"] and row["email"].lower() == clean_email:
            return "An account with this email already exists."
        if row["username"] and row["username"].lower() == clean_username.lower():
            return "This username is already taken."
    return None


def get_all_users():
    """Retrieve list of all registered users (excluding sensitive password hashes)."""
    if is_mongodb_active():
        db = get_mongo_db()
        cursor = db["users"].find({}, {"password_hash": 0}).sort("id", DESCENDING)
        users = []
        for doc in cursor:
            users.append(_sanitize_mongo_doc(doc))
        return users

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, first_name, surname, age, phone, email, username, created_at, updated_at
        FROM users
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id):
    """Delete a user account by user_id."""
    if is_mongodb_active():
        db = get_mongo_db()
        try:
            uid_int = int(user_id)
            res = db["users"].delete_one({"id": uid_int})
            if res.deleted_count > 0:
                return True
        except (ValueError, TypeError):
            pass
        res = db["users"].delete_one({"id": user_id})
        return res.deleted_count > 0

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def count_users():
    """Return total number of registered users."""
    if is_mongodb_active():
        db = get_mongo_db()
        return db["users"].count_documents({})

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users")
    row = cursor.fetchone()
    conn.close()
    return row["count"] if row else 0


# ---------------------------------------------------------------------------
# Locality CRUD Operations
# ---------------------------------------------------------------------------

def update_locality_price(name, rate_per_sqft, rate_per_sqyd=None, yoy_percent=None,
                          projected_5yr=None, livability_score=None):
    """Manually update pricing and metrics for a specific locality."""
    clean_name = name.strip()
    now = datetime.now(timezone.utc).isoformat()

    if rate_per_sqyd is None:
        rate_per_sqyd = round(float(rate_per_sqft) * 9.0, 2)

    if is_mongodb_active():
        db = get_mongo_db()
        update_fields = {
            "rate_per_sqft": float(rate_per_sqft),
            "rate_per_sqyd": float(rate_per_sqyd),
            "updated_at": now
        }
        if yoy_percent is not None:
            update_fields["yoy_percent"] = float(yoy_percent)
        if projected_5yr is not None:
            update_fields["projected_5yr"] = float(projected_5yr)
        if livability_score is not None:
            update_fields["livability_score"] = float(livability_score)

        res = db["localities"].update_one(
            {"name": {"$regex": f"^{re_escape(clean_name)}$", "$options": "i"}},
            {"$set": update_fields}
        )
        return res.modified_count > 0 or res.matched_count > 0

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    updates = ["rate_per_sqft = ?", "rate_per_sqyd = ?", "updated_at = ?"]
    params = [float(rate_per_sqft), float(rate_per_sqyd), now]

    if yoy_percent is not None:
        updates.append("yoy_percent = ?")
        params.append(float(yoy_percent))
    if projected_5yr is not None:
        updates.append("projected_5yr = ?")
        params.append(float(projected_5yr))
    if livability_score is not None:
        updates.append("livability_score = ?")
        params.append(float(livability_score))

    params.append(clean_name.lower())
    query = f"UPDATE localities SET {', '.join(updates)} WHERE LOWER(name) = ?"

    cursor.execute(query, tuple(params))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def upsert_locality(name, zone, tier, rate_per_sqyd, rate_per_sqft, yoy_percent,
                    projected_5yr, note, landmarks, schools_hospitals, transit,
                    livability_score, data_source, price_explanation_en=None, price_explanation_hi=None):
    """Insert or update locality details in active database."""
    clean_name = name.strip()
    now = datetime.now(timezone.utc).isoformat()

    if is_mongodb_active():
        db = get_mongo_db()
        doc_data = {
            "name": clean_name,
            "zone": zone,
            "tier": tier,
            "rate_per_sqyd": float(rate_per_sqyd),
            "rate_per_sqft": float(rate_per_sqft),
            "yoy_percent": float(yoy_percent) if yoy_percent is not None else None,
            "projected_5yr": float(projected_5yr) if projected_5yr is not None else None,
            "note": note,
            "landmarks": landmarks,
            "schools_hospitals": schools_hospitals,
            "transit": transit,
            "livability_score": float(livability_score) if livability_score is not None else None,
            "data_source": data_source,
            "price_explanation_en": price_explanation_en,
            "price_explanation_hi": price_explanation_hi,
            "updated_at": now
        }
        db["localities"].update_one(
            {"name": {"$regex": f"^{re_escape(clean_name)}$", "$options": "i"}},
            {"$set": doc_data},
            upsert=True
        )
        return

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO localities (
            name, zone, tier, rate_per_sqyd, rate_per_sqft, yoy_percent,
            projected_5yr, note, landmarks, schools_hospitals, transit,
            livability_score, data_source, price_explanation_en, price_explanation_hi, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            zone=excluded.zone,
            tier=excluded.tier,
            rate_per_sqyd=excluded.rate_per_sqyd,
            rate_per_sqft=excluded.rate_per_sqft,
            yoy_percent=excluded.yoy_percent,
            projected_5yr=excluded.projected_5yr,
            note=excluded.note,
            landmarks=excluded.landmarks,
            schools_hospitals=excluded.schools_hospitals,
            transit=excluded.transit,
            livability_score=excluded.livability_score,
            data_source=excluded.data_source,
            price_explanation_en=coalesce(excluded.price_explanation_en, localities.price_explanation_en),
            price_explanation_hi=coalesce(excluded.price_explanation_hi, localities.price_explanation_hi),
            updated_at=excluded.updated_at
    """, (
        clean_name, zone, tier, rate_per_sqyd, rate_per_sqft, yoy_percent,
        projected_5yr, note, landmarks, schools_hospitals, transit,
        livability_score, data_source, price_explanation_en, price_explanation_hi, now
    ))
    conn.commit()
    conn.close()


def get_all_localities(zone_filter=None):
    """Get list of all localities sorted by name or filtered by zone."""
    if is_mongodb_active():
        db = get_mongo_db()
        query = {}
        if zone_filter:
            query["zone"] = {"$regex": f"^{re_escape(zone_filter.strip())}$", "$options": "i"}
        cursor = db["localities"].find(query).sort("name", ASCENDING)
        return [_sanitize_mongo_doc(doc) for doc in cursor]

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    if zone_filter:
        cursor.execute("SELECT * FROM localities WHERE LOWER(zone) = ? ORDER BY name ASC", (zone_filter.lower().strip(),))
    else:
        cursor.execute("SELECT * FROM localities ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_locality_by_name(name):
    """Get single locality with rich information."""
    if not name:
        return None
    clean_name = name.strip()

    if is_mongodb_active():
        db = get_mongo_db()
        doc = db["localities"].find_one({"name": {"$regex": f"^{re_escape(clean_name)}$", "$options": "i"}})
        return _sanitize_mongo_doc(doc)

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM localities WHERE LOWER(name) = ?", (clean_name.lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Historical Trends CRUD Operations
# ---------------------------------------------------------------------------

def add_historical_trend(locality_name, year, rate_per_sqft, rate_per_sqyd, source):
    """Insert or replace historical trend point."""
    clean_name = locality_name.strip()
    year_int = int(year)

    if is_mongodb_active():
        db = get_mongo_db()
        db["historical_trends"].update_one(
            {"locality_name": {"$regex": f"^{re_escape(clean_name)}$", "$options": "i"}, "year": year_int},
            {"$set": {
                "locality_name": clean_name,
                "year": year_int,
                "rate_per_sqft": float(rate_per_sqft),
                "rate_per_sqyd": float(rate_per_sqyd),
                "source": source
            }},
            upsert=True
        )
        return

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO historical_trends (locality_name, year, rate_per_sqft, rate_per_sqyd, source)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(locality_name, year) DO UPDATE SET
            rate_per_sqft=excluded.rate_per_sqft,
            rate_per_sqyd=excluded.rate_per_sqyd,
            source=excluded.source
    """, (clean_name, year_int, rate_per_sqft, rate_per_sqyd, source))
    conn.commit()
    conn.close()


def get_historical_trends(locality_name):
    """Get all historical trend points for a given locality ordered by year."""
    if not locality_name:
        return []
    clean_name = locality_name.strip()

    if is_mongodb_active():
        db = get_mongo_db()
        cursor = db["historical_trends"].find(
            {"locality_name": {"$regex": f"^{re_escape(clean_name)}$", "$options": "i"}}
        ).sort("year", ASCENDING)
        return [{"year": doc["year"], "rate_per_sqft": doc["rate_per_sqft"], "rate_per_sqyd": doc["rate_per_sqyd"], "source": doc.get("source", "")} for doc in cursor]

    conn = get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT year, rate_per_sqft, rate_per_sqyd, source
        FROM historical_trends
        WHERE LOWER(locality_name) = ?
        ORDER BY year ASC
    """, (clean_name.lower(),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_database_status():
    """Return dictionary with database status and record statistics."""
    active_engine = "MongoDB" if is_mongodb_active() else "SQLite"
    total_users = count_users()
    total_locs = len(get_all_localities())
    
    return {
        "engine": active_engine,
        "is_mongodb": is_mongodb_active(),
        "mongo_uri": MONGO_URI if is_mongodb_active() else None,
        "mongo_db_name": MONGO_DB_NAME if is_mongodb_active() else None,
        "sqlite_path": SQLITE_DB_PATH,
        "total_users": total_users,
        "total_localities": total_locs
    }


if __name__ == "__main__":
    init_db()
    status = get_database_status()
    print("=" * 60)
    print(" Vasudha Real Estate — Database Diagnostic")
    print("=" * 60)
    print(f" Active Engine:    {status['engine']}")
    if status['is_mongodb']:
        print(f" MongoDB URI:      {status['mongo_uri']}")
        print(f" Database Name:    {status['mongo_db_name']}")
    else:
        print(f" SQLite File:      {status['sqlite_path']}")
    print(f" Total Users:      {status['total_users']}")
    print(f" Total Localities: {status['total_localities']}")
    print("=" * 60)
