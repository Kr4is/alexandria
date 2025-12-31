from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Book, User
from api import search_books, get_book_details
from datetime import datetime, UTC
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration
app.config['APP_NAME'] = os.getenv('APP_NAME', 'Alexandria')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-key-for-dev')

# Database
basedir = os.path.abspath(os.path.dirname(__file__))
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith('sqlite:///'):
    # Handle both relative and absolute paths for SQLite
    db_path = db_url.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        db_path = os.path.join(basedir, db_path)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or f"sqlite:///{os.path.join(basedir, 'instance', 'alexandria.db')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    # Ensure instance folder exists
    instance_path = os.path.join(basedir, 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
        
    db.create_all()
    
    # Create Librarian (Admin) from environment variables
    admin_user = os.getenv('LIBRARIAN_USERNAME', 'admin')
    admin_pass = os.getenv('LIBRARIAN_PASSWORD', 'alexandria')
    
    existing_user = User.query.filter_by(username=admin_user).first()
    if not existing_user:
        admin = User(username=admin_user)
        admin.set_password(admin_pass)
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def index():
    reading_list = Book.query.filter_by(status='reading').order_by(Book.date_added.desc()).all()
    finished_list = Book.query.filter_by(status='finished').order_by(Book.date_finished.desc()).all()
    return render_template('index.html', reading=reading_list, finished=finished_list)

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template('book_detail.html', book=book)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q')
    results = []
    if query:
        results = search_books(query)
    return render_template('search.html', results=results, query=query)

@app.route('/add/<google_books_id>', methods=['POST'])
@login_required
def add_book(google_books_id):
    if not Book.query.filter_by(google_books_id=google_books_id).first():
        details = get_book_details(google_books_id)
        if details:
            new_book = Book(
                google_books_id=details['google_books_id'],
                title=details['title'],
                authors=details['authors'],
                thumbnail=details['thumbnail'],
                description=details['description'],
                categories=details['categories'],
                status='reading'
            )
            db.session.add(new_book)
            db.session.commit()
    return redirect(url_for('index'))

@app.route('/finish/<int:book_id>', methods=['POST'])
@login_required
def finish_book(book_id):
    book = Book.query.get_or_404(book_id)
    book.status = 'finished'
    book.date_finished = datetime.now(UTC)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
