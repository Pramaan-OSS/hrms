"""Prepare only the local site in this compose project's private volumes."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path("/app")
BENCH = ROOT / ".runtime/bench"
SITES = BENCH / "sites"
SITE = os.environ.get("HRMS_SITE_NAME", "hrms.localhost")
if not SITE or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in SITE):
    raise SystemExit("The local site name must contain only lowercase letters, numbers, dots and hyphens.")
for folder in [SITES, BENCH / "apps", BENCH / "logs"]:
    folder.mkdir(parents=True, exist_ok=True)
for target, source in [
    (BENCH / "env", ROOT / ".venv"),
    (BENCH / "apps/frappe", ROOT / "vendor/framework"),
    (BENCH / "apps/erpnext", ROOT / "vendor/erp"),
    (BENCH / "apps/hrms", ROOT),
    (ROOT / "sites", SITES),
]:
    if not target.exists():
        target.symlink_to(source, target_is_directory=True)
(SITES / "apps.txt").write_text("frappe\nerpnext\nhrms\n")
(SITES / "common_site_config.json").write_text(json.dumps({
    "db_host": "database", "db_port": 3306, "use_mysqlclient": 0,
    "redis_cache": "redis://cache:6379/0", "redis_queue": "redis://cache:6379/1", "redis_socketio": "redis://cache:6379/2",
    "socketio_port": 9000, "socketio_same_origin": True,
    "socketio_client_port": int(os.environ.get("HRMS_LOCAL_PORT", "18021")), "webserver_port": 8000, "webserver_host": "0.0.0.0",
    "default_site": SITE, "serve_default_site": True, "developer_mode": 0, "allow_error_traceback": 0,
    "chromium_path": "/usr/bin/chromium",
    "server_script_enabled": 0, "enable_telemetry": False, "pause_scheduler": False, "disable_scheduler": False,
    "encryption_key": os.environ["HRMS_ENCRYPTION_KEY"],
}, indent=2))
(SITES / "common_site_config.json").chmod(0o600)


def bench(*args):
    result = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "frappe.utils.bench_helper", "frappe", *args], cwd=SITES)
    if result.returncode:
        raise SystemExit("Local site setup did not finish. Check the private container logs.")


config_path = SITES / SITE / "site_config.json"
if not config_path.exists():
    bench("new-site", SITE, "--db-type", "mariadb", "--db-host", "database", "--db-port", "3306",
          "--db-root-password", os.environ["LOCAL_DB_PASSWORD"], "--admin-password", os.environ["HRMS_ADMIN_PASSWORD"],
          "--mariadb-user-host-login-scope", "%", "--set-default")


def install_if_missing(app):
    config = json.loads(config_path.read_text())
    if app not in (config.get("installed_apps") or []):
        bench("--site", SITE, "install-app", app)
        config = json.loads(config_path.read_text())
    return config


install_if_missing("erpnext")
install_if_missing("hrms")
config = json.loads(config_path.read_text())
config.update(developer_mode=0, allow_error_traceback=0, host_name=f"http://localhost:{os.environ.get('HRMS_LOCAL_PORT', '18021')}")
config_path.write_text(json.dumps(config, indent=2)); config_path.chmod(0o600)
assets = SITES / "assets"; assets.mkdir(exist_ok=True)
for name, source in [
    ("hrms", ROOT / "hrms/public"),
    ("erpnext", ROOT / "vendor/erp/erpnext/public"),
    ("frappe", ROOT / "vendor/framework/frappe/public"),
]:
    link = assets / name
    if not link.exists():
        link.symlink_to(source, target_is_directory=True)
if not (assets / "assets.json").exists():
    (assets / "assets.json").write_text("{}")
desk_marker = ROOT / ".desk-assets-built"
if not desk_marker.exists():
    # Bundles are written into the app directories in this container. Only mark
    # completion after every build succeeds; a partial dist directory is not enough.
    bench("build", "--production", "--apps", "frappe,erpnext,hrms")
    desk_marker.touch()

bench("--site", SITE, "migrate")
bench("--site", SITE, "enable-scheduler")
from hrms.pramaan import PramaanClient
(BENCH / ".outside-configured").write_text("yes" if PramaanClient().configured else "no")
