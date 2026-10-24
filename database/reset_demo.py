"""Reset to a clean, repeatable demo state. Wipes users, orders, trips, payments, wallets and assistant history, rebuilds the Jaipur demo data,
and recreates your admin login. Next app start re-creates the demo ride fleet and the Rs 500 wallet credit. ML models are kept."""
import os, sys, sqlite3, subprocess, pathlib, argparse
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import config

ap = argparse.ArgumentParser()
ap.add_argument("--name", default=os.getenv("ADMIN_NAME", "Sami Khan")); ap.add_argument("--email", default=os.getenv("ADMIN_EMAIL", "samikhan75706@gmail.com"))
ap.add_argument("--show", action="store_true", help="show the admin password while typing")
a = ap.parse_args()

EXTRA = ["assistant_actions", "coupon_uses", "wallet_txns", "payments", "parcels", "meta"]
if config.DB_PATH.exists():
    c = sqlite3.connect(config.DB_PATH)
    c.execute("PRAGMA foreign_keys=OFF")
    for t in EXTRA:
        try:
            c.execute(f"DELETE FROM {t}")
        except sqlite3.OperationalError:
            pass
    c.commit(); c.close()
py = sys.executable
subprocess.check_call([py, str(ROOT / "database" / "seed.py"), "--reset"])
cmd = [py, str(ROOT / "database" / "create_admin.py"), "--name", a.name, "--email", a.email, "--retire-demo-admin"] + (["--show"] if a.show else [])
if subprocess.call(cmd) != 0:
    print("\nDemo data was reset, but your admin login was NOT created.")
    print("Create it now (type the password visibly):")
    print(f'  "%LOCALAPPDATA%\\RouteNexVenv\\Scripts\\python.exe" database\\create_admin.py --name "{a.name}" --email {a.email} --retire-demo-admin --show')
    sys.exit(1)
print("\nDemo data reset. Start the app (start.bat): the demo fleet and wallet credit are created on startup.")
