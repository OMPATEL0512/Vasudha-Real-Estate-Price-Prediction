"""
Vasudha Real Estate — Standalone Manual Database CLI & CSV Exporter
Use this tool to view users, export tables to CSV/Excel, delete accounts, or migrate data
WITHOUT needing to start or open the web application.
"""

import os
import sys
import csv
import database

# Ensure UTF-8 output in Windows command prompt
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def list_users():
    users = database.get_all_users()
    db_status = database.get_database_status()

    print("\n" + "=" * 95)
    print(f" VASUDHA REAL ESTATE -- REGISTERED USERS DATABASE [{db_status['engine']}]")
    print("=" * 95)
    if not users:
        print("  No registered users found in the database.")
    else:
        # Sort users by ID ascending for nice display
        try:
            sorted_users = sorted(users, key=lambda x: int(x.get("id", 0)))
        except Exception:
            sorted_users = users
        print(f" {'ID':<6} | {'Full Name':<22} | {'Username':<16} | {'Email Address':<30} | {'Phone':<12}")
        print("-" * 95)
        for r in sorted_users:
            name = f"{r.get('first_name') or ''} {r.get('surname') or ''}".strip()
            uid = r.get('id', '')
            uname = r.get('username', '')
            uemail = r.get('email', '')
            uphone = r.get('phone') or 'N/A'
            print(f" #{str(uid):<5} | {name:<22} | @{uname:<15} | {uemail:<30} | {uphone:<12}")
    print("=" * 95 + "\n")


def export_to_csv():
    users = database.get_all_users()
    locs = database.get_all_localities()
    out_dir = os.path.dirname(__file__)

    # Export Users
    user_csv = os.path.join(out_dir, "users_export.csv")
    with open(user_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "First Name", "Surname", "Age", "Phone", "Email", "Username", "Created At"])
        for r in users:
            writer.writerow([
                r.get("id", ""),
                r.get("first_name", ""),
                r.get("surname", ""),
                r.get("age", ""),
                r.get("phone", ""),
                r.get("email", ""),
                r.get("username", ""),
                r.get("created_at", "")
            ])

    # Export Localities
    loc_csv = os.path.join(out_dir, "localities_export.csv")
    with open(loc_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Locality Name", "Zone", "Tier", "Rate (Rs/sq.yd)", "Rate (Rs/sq.ft)", "YoY Growth %", "5-Year Projected Rate", "Livability Score"])
        for r in locs:
            writer.writerow([
                r.get("name", ""),
                r.get("zone", ""),
                r.get("tier", ""),
                r.get("rate_per_sqyd", ""),
                r.get("rate_per_sqft", ""),
                r.get("yoy_percent", ""),
                r.get("projected_5yr", ""),
                r.get("livability_score", "")
            ])

    print(f"\n[+] Successfully exported database to CSV files:")
    print(f"    1. Users CSV:      {user_csv}")
    print(f"    2. Localities CSV: {loc_csv}\n")


def delete_user_by_id(user_id):
    user = database.get_user_by_id(user_id)
    if not user:
        print(f"[Error] User with ID #{user_id} not found.")
        return

    deleted = database.delete_user(user_id)
    if deleted:
        print(f"[+] User account '@{user.get('username')}' ({user.get('email')}) deleted from database.")
    else:
        print(f"[Error] Failed to delete user #{user_id}.")


def sync_sqlite_to_mongodb():
    print("\nStarting migration from SQLite to MongoDB...")
    res = database.migrate_sqlite_to_mongodb(verbose=True)
    if res:
        print("[SUCCESS] All data synced into MongoDB successfully!")
    else:
        print("[FAILED] Migration could not be completed.")


def main():
    database.init_db()
    while True:
        status = database.get_database_status()
        print("\n" + "=" * 60)
        print("  VASUDHA REAL ESTATE -- DATABASE MANAGER")
        print(f"  Active Engine: {status['engine']}")
        if status['is_mongodb']:
            print(f"  MongoDB URI:   {status['mongo_uri']}")
            print(f"  Database:      {status['mongo_db_name']}")
        else:
            print(f"  SQLite File:   {status['sqlite_path']}")
        print(f"  Total Users:   {status['total_users']} | Localities: {status['total_localities']}")
        print("=" * 60)
        print("  1. View All Registered Users (Table View)")
        print("  2. Export Database to CSV (Open in Excel)")
        print("  3. Delete User Account by ID")
        print("  4. Sync / Migrate SQLite data into MongoDB")
        print("  5. Exit")
        print("-" * 60)
        try:
            choice = input("Select an option (1-5): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting database manager.")
            break

        if choice == "1":
            list_users()
        elif choice == "2":
            export_to_csv()
        elif choice == "3":
            uid = input("Enter User ID to delete: ").strip()
            if uid:
                delete_user_by_id(uid)
            else:
                print("[Error] Please enter a valid user ID.")
        elif choice == "4":
            sync_sqlite_to_mongodb()
        elif choice == "5" or choice.lower() == "exit":
            print("Exiting database manager.")
            break
        else:
            print("Invalid option. Please choose 1, 2, 3, 4, or 5.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--export":
        database.init_db()
        export_to_csv()
    elif len(sys.argv) > 1 and sys.argv[1] == "--users":
        database.init_db()
        list_users()
    else:
        main()
