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
@login_required
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
                page_count=details.get('page_count'),
                categories=details['categories'],
                status='reading'
            )
            db.session.add(new_book)
            db.session.commit()
    return redirect(url_for('index'))

@app.route('/stats')
def stats():
    # Base queries
    all_books = Book.query.all()
    finished_books = [b for b in all_books if b.status == 'finished' and b.date_finished]
    
    # 1. Overview Metrics
    total_books_read = len(finished_books)
    total_pages_read = sum(b.page_count for b in finished_books if b.page_count)
    avg_pages_per_book = int(total_pages_read / total_books_read) if total_books_read > 0 else 0
    
    # 2. Books by Year/Month
    # Structure: {'2024': {'Jan': 2, 'Feb': 1, ...}, '2023': ...}
    books_by_year_month = {}
    
    for book in finished_books:
        year = book.date_finished.strftime('%Y')
        month = book.date_finished.strftime('%B')
        
        if year not in books_by_year_month:
            books_by_year_month[year] = {}
        
        books_by_year_month[year][month] = books_by_year_month[year].get(month, 0) + 1
        
    # 3. Pages by Year (for a chart)
    pages_by_year = {}
    for book in finished_books:
        if book.page_count:
            year = book.date_finished.strftime('%Y')
            pages_by_year[year] = pages_by_year.get(year, 0) + book.page_count

    # 4. Top Authors
    author_counts = {}
    for book in finished_books:
        if book.authors:
            # Handle multiple authors if comma separated
            authors = [a.strip() for a in book.authors.split(',')]
            for author in authors:
                author_counts[author] = author_counts.get(author, 0) + 1
    
    # Sort and take top 5
    top_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # 5. Categories Distribution
    category_counts = {}
    for book in all_books: # Include reading books for categories
        if book.categories:
            cats = [c.strip() for c in book.categories.split(',')]
            for cat in cats:
                category_counts[cat] = category_counts.get(cat, 0) + 1
                
    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return render_template('stats.html', 
                           total_books=total_books_read,
                           total_pages=total_pages_read,
                           avg_pages=avg_pages_per_book,
                           books_by_year_month=books_by_year_month,
                           pages_by_year=pages_by_year,
                           top_authors=top_authors,
                           top_categories=top_categories)

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
