"""Create (or update) an admin login. The password is typed at the prompt, so it never sits in code or git.
Usage:  python database\\create_admin.py --name "Sami Khan" --email you@example.com [--retire-demo-admin] [--show]
  --show   type the password visibly (use this if the hidden prompt keeps rejecting you)
Note: `seed.py --reset` wipes all users, so run this again after a reset."""
import sys, os, argparse, getpass, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from security import hash_password
from db import init_db, tx

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True); ap.add_argument("--email", required=True)
ap.add_argument("--retire-demo-admin", action="store_true", help="deactivate the public demo login samikhan@routenex.in")
ap.add_argument("--show", action="store_true", help="show the password while typing")
a = ap.parse_args()


def ask_password():
    pw = os.getenv("ADMIN_PASSWORD")
    if pw:
        return pw
    print("\nChoose the password for this admin login (you are CREATING it, not entering an old one).")
    print("Type it twice, exactly the same." + ("" if a.show else " Typing is invisible: no dots or stars appear. Do not paste."))
    for attempt in range(1, 4):
        read = input if a.show else getpass.getpass
        p1, p2 = read("Password: "), read("Repeat password: ")
        if p1 != p2:
            print(f"  The two entries were different (try {attempt} of 3).\n" + ("  Tip: run again with --show to see what you type.\n" if not a.show else ""))
            continue
        if len(p1) < 6:
            print(f"  Use at least 6 characters (try {attempt} of 3).\n")
            continue
        return p1
    sys.exit("Could not set a password after 3 tries. Run:  python database\\create_admin.py --name \"...\" --email ... --show")


pw = ask_password()
if len(pw) < 10:
    print("Note: this password is short. Fine for a local demo; use 10+ characters if the app is reachable by a public link.")

init_db()
email = a.email.strip().lower()
with tx() as c:
    row = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if row:
        c.execute("UPDATE users SET name=?,password_hash=?,role='admin',active=1 WHERE id=?", (a.name, hash_password(pw), row["id"]))
        uid, verb = row["id"], "updated"
    else:
        uid = c.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?, 'admin')", (a.name, email, hash_password(pw))).lastrowid
        verb = "created"
    if a.retire_demo_admin:
        c.execute("UPDATE users SET active=0 WHERE email='samikhan@routenex.in' AND id!=?", (uid,))   # never retire the account we just made
    c.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)", (uid, "CREATE_ADMIN", "user", str(uid), "admin account " + verb))
print(f"\nAdmin {verb}: {a.name} <{email}>" + ("  | demo admin deactivated" if a.retire_demo_admin else "") + "\nYou can now log in with this email and the password you just chose.")
