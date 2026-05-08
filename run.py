"""
Entry point for the Vidyarthi Mitra web application.

Usage:
    python run.py
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
