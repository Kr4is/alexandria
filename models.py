from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_books_id = db.Column(db.String(50), unique=True, nullable=True)
    title = db.Column(db.String(200), nullable=False)
    authors = db.Column(db.String(200))
    thumbnail = db.Column(db.String(500))
    description = db.Column(db.Text)
    categories = db.Column(db.String(200))
    status = db.Column(db.String(20), default='reading')  # 'reading', 'finished'
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    date_finished = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'authors': self.authors,
            'thumbnail': self.thumbnail,
            'description': self.description,
            'categories': self.categories,
            'status': self.status,
            'date_finished': self.date_finished.strftime('%Y-%m-%d') if self.date_finished else None
        }
