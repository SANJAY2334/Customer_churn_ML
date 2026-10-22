"""
run_app.py
----------
One-Click Launcher for Telecom Customer Churn Prediction & Risk Analysis.
Automatically verifies models, starts Flask server, and opens web app in your browser.
"""

import os
import sys
import time
import threading
import webbrowser
import subprocess

def open_browser_later():
    time.sleep(1.5)
    print("\n[*] Opening Web Application in your browser at http://127.0.0.1:5000 ...")
    webbrowser.open("http://127.0.0.1:5000")

def main():
    print("=" * 65)
    print("  TELECOM CUSTOMER CHURN PREDICTION - ONE-CLICK LAUNCHER")
    print("=" * 65)

    # Change working directory to project root if script run from elsewhere
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    model_path = os.path.join("Models", "churn_model.pkl")
    metrics_path = os.path.join("Models", "model_metrics.json")

    # Check if model exists, if not train it
    if not os.path.exists(model_path) or not os.path.exists(metrics_path):
        print("\n[*] Training Machine Learning models (Logistic Regression, Decision Tree, Random Forest, XGBoost)...")
        result = subprocess.run([sys.executable, "train_model.py"])
        if result.returncode != 0:
            print("[-] Model training failed. Check output above.")
            sys.exit(1)
    else:
        print("\n[+] Trained model verified in Models/churn_model.pkl")

    # Start background thread to open browser
    threading.Thread(target=open_browser_later, daemon=True).start()

    print("\n[+] Starting Flask Server on http://127.0.0.1:5000 ...")
    print("    Press CTRL+C in this terminal to stop the server.\n")

    # Import and run Flask app
    try:
        from flask_app import app
        app.run(host="127.0.0.1", port=5000, debug=False)
    except Exception as e:
        print(f"[ERROR] Server launch error: {e}")

if __name__ == "__main__":
    main()
