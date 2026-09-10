"""
local_worker.py
===============
Home PC Worker Client for H1 Checker QA Tool.

Connects your Home PC to your Vercel cloud serverless deployment.
Polls Vercel for pending scan requests, executes them locally using your Home PC
(Selenium, NLP, Scraping), and posts the audit report back to Vercel.

Usage:
    python local_worker.py
"""

import os
import time
import base64
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
VERCEL_URL = os.getenv("VERCEL_URL", "").strip().rstrip("/")
WORKER_SECRET = os.getenv("WORKER_SECRET_KEY", "h1-checker-secret-key-2026")
LOCAL_FLASK_URL = os.getenv("LOCAL_FLASK_URL", "http://127.0.0.1:5000").rstrip("/")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3"))  # seconds

def prompt_vercel_url():
    global VERCEL_URL
    if not VERCEL_URL:
        print("\n=======================================================")
        print("  H1 CHECKER - REMOTE WORKER SETUP")
        print("=======================================================")
        print("Please enter your Vercel app URL (or press Enter for default):")
        print("Example: https://your-h1-checker.vercel.app")
        user_input = input("Vercel URL: ").strip().rstrip("/")
        if user_input:
            VERCEL_URL = user_input
        else:
            print("[WARN] No Vercel URL provided. Defaulting to http://localhost:3000 for local testing.")
            VERCEL_URL = "http://localhost:3000"
    print(f"\n[CONFIG] Target Vercel URL: {VERCEL_URL}")
    print(f"[CONFIG] Local Backend URL: {LOCAL_FLASK_URL}")

def check_local_backend():
    try:
        r = requests.get(f"{LOCAL_FLASK_URL}/api/history", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def sync_image_bank_to_vercel():
    """Syncs local SQLite image bank assets to Vercel so Vercel Image Bank UI matches local."""
    if not VERCEL_URL or "localhost" in VERCEL_URL:
        return
    try:
        resp = requests.get(f"{LOCAL_FLASK_URL}/api/image-bank?limit=300", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            assets = data.get("assets", [])
            if assets:
                sync_url = f"{VERCEL_URL}/api/image-bank/sync?key={WORKER_SECRET}"
                headers = {"X-Worker-Secret": WORKER_SECRET, "Content-Type": "application/json"}
                r_sync = requests.post(sync_url, json={"assets": assets}, headers=headers, timeout=15)
                if r_sync.status_code == 200:
                    print(f"   [IMAGE BANK] Synced {len(assets)} local vehicle image assets to Vercel.")
    except Exception as e:
        print(f"   [IMAGE BANK WARN] Could not sync Image Bank to Vercel: {e}")

def poll_and_process():
    pending_url = f"{VERCEL_URL}/api/jobs/pending?key={WORKER_SECRET}"
    complete_url = f"{VERCEL_URL}/api/jobs/complete?key={WORKER_SECRET}"
    headers = {
        "X-Worker-Secret": WORKER_SECRET,
        "User-Agent": "H1Checker-LocalWorker/1.0"
    }

    try:
        resp = requests.get(pending_url, headers=headers, timeout=10)
        if resp.status_code == 401:
            print("[ERROR] Unauthorized worker secret key. Check WORKER_SECRET_KEY in your .env file.")
            time.sleep(5)
            return

        if resp.status_code != 200:
            return

        data = resp.json()
        job_id = data.get("job_id")
        if not job_id:
            return  # No pending jobs

        endpoint = data.get("endpoint", "/api/extract-h1")
        payload = data.get("payload", {})
        target_url = payload.get("url", "unknown")

        print(f"\n⚡ [WORKER] New Job Received! ID: {job_id}")
        print(f"   Target URL: {target_url}")
        print(f"   Endpoint: {endpoint}")
        print("   Processing locally on Home PC...")

        # 1. Check if local app.py server is up
        if not check_local_backend():
            err_msg = f"Local Flask server (app.py) is NOT running on {LOCAL_FLASK_URL}. Please start 'python app.py' in your terminal!"
            print(f"   [ERROR] {err_msg}")
            try:
                requests.post(complete_url, json={"job_id": job_id, "error": err_msg}, headers=headers, timeout=15)
            except Exception:
                pass
            return

        # 2. Execute local request against Flask app
        local_target = f"{LOCAL_FLASK_URL}{endpoint}"
        try:
            local_resp = requests.post(local_target, json=payload, timeout=300)
            if local_resp.status_code == 200:
                content_type = local_resp.headers.get("content-type", "").lower()
                if "application/pdf" in content_type or endpoint.endswith("generate-pdf"):
                    pdf_b64 = base64.b64encode(local_resp.content).decode("utf-8")
                    case_num = payload.get("case_number", "").strip() if isinstance(payload, dict) else ""
                    filename = f"{case_num}.pdf" if case_num else "Bug-Report.pdf"
                    result_data = {
                        "pdf_base64": pdf_b64,
                        "filename": filename
                    }
                    print("   [SUCCESS] Local PDF report generated successfully!")
                else:
                    result_data = local_resp.json()
                    print("   [SUCCESS] Local scan completed successfully!")
                
                # 3. Post complete result back to Vercel
                post_body = {
                    "job_id": job_id,
                    "result": result_data
                }
                requests.post(complete_url, json=post_body, headers=headers, timeout=15)
                print(f"   [SYNCED] Audit results sent back to Vercel for Job {job_id}.\n")

                # 4. Sync harvested images to Vercel Image Bank
                sync_image_bank_to_vercel()
            else:
                err_msg = f"Local Flask returned status code {local_resp.status_code}: {local_resp.text[:200]}"
                print(f"   [FAIL] {err_msg}")
                requests.post(complete_url, json={"job_id": job_id, "error": err_msg}, headers=headers, timeout=15)

        except Exception as local_err:
            err_msg = f"Failed to execute local scan: {str(local_err)}"
            print(f"   [ERROR] {err_msg}")
            requests.post(complete_url, json={"job_id": job_id, "error": err_msg}, headers=headers, timeout=15)

    except requests.exceptions.RequestException as net_err:
        # Silently retry on transient network glitch
        pass
    except Exception as e:
        print(f"[WARN] Worker loop error: {e}")

def main():
    prompt_vercel_url()

    print("\n=======================================================")
    print("  QA WEB TOOL - HOME PC REMOTE WORKER IS RUNNING!")
    print("=======================================================")
    print(" Listening for remote scan requests from Vercel...")
    print(" Keep this window open while accessing the tool remotely.")
    print(" Press Ctrl+C to stop.\n")

    # Check local Flask backend
    if check_local_backend():
        print("[STATUS] Local Backend (Flask on :5000): ONLINE ✅")
        sync_image_bank_to_vercel()
    else:
        print("[STATUS] Local Backend (Flask on :5000): OFFLINE ❌")
        print("[STATUS] Local Backend (Flask on :5000): OFFLINE ⚠️")
        print("          Make sure start_app.bat is running on this PC!")

    print("-" * 55)

    while True:
        poll_and_process()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
