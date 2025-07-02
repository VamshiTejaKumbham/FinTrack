import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

# Initialize the database
with app.app_context():
    db.create_all()
    print("Database initialized successfully!")
