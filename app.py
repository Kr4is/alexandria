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
                published_year=details.get('published_year'),
                language=details.get('language'),
                average_rating=details.get('average_rating'),
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
    
    # helper for safe division
    def safe_div(n, d): return n / d if d > 0 else 0

    # --- 1. VOLUME METRICS ---
    total_books_read = len(finished_books)
    total_pages_read = sum(b.page_count for b in finished_books if b.page_count)
    avg_pages_per_book = int(safe_div(total_pages_read, total_books_read))
    
    # Monthly/Yearly Averages
    if finished_books:
        first_finish = min(b.date_finished for b in finished_books)
        days_active = (datetime.now(UTC) - first_finish.replace(tzinfo=UTC)).days + 1
        months_active = max(days_active / 30, 1)
        years_active = max(days_active / 365, 1)
    else:
        months_active = 1
        years_active = 1
        
    avg_pages_per_month = int(total_pages_read / months_active)
    avg_pages_per_year = int(total_pages_read / years_active)
    
    # Pages per Month (History) -> Tuple list sorted by date
    # We aggregate by YYYY-MM for sorting, then format label
    pm_history = {}
    for b in finished_books:
        if b.page_count:
            key = b.date_finished.strftime('%Y-%m') 
            pm_history[key] = pm_history.get(key, 0) + b.page_count
            
    sorted_keys = sorted(pm_history.keys())
    pages_history_labels = [datetime.strptime(k, '%Y-%m').strftime('%b %Y') for k in sorted_keys]
    pages_history_data = [pm_history[k] for k in sorted_keys]

    # Records (Longest/Shortest)
    books_with_pages = [b for b in finished_books if b.page_count is not None]
    longest_book = max(books_with_pages, key=lambda b: b.page_count) if books_with_pages else None
    shortest_book = min(books_with_pages, key=lambda b: b.page_count) if books_with_pages else None

    # --- 2. TIME & SPEED METRICS ---
    # Velocity (Days to finish)
    # Filter out weird data where finished < added
    valid_intervals = []
    book_velocities = [] # (book, days)
    
    for b in finished_books:
        if b.date_added and b.date_finished:
            # Ensure timezone awareness match or ignore if naive
            # SQLite default is naive, usually. 
            # safe subtraction:
            start = b.date_added
            end = b.date_finished
            days = (end - start).days
            if days >= 0:
                valid_intervals.append(days)
                book_velocities.append((b, days))
    
    avg_days_per_book = int(safe_div(sum(valid_intervals), len(valid_intervals)))
    
    fastest_book = min(book_velocities, key=lambda x: x[1])[0] if book_velocities else None
    slowest_book = max(book_velocities, key=lambda x: x[1])[0] if book_velocities else None
    fastest_days = min(valid_intervals) if valid_intervals else 0
    slowest_days = max(valid_intervals) if valid_intervals else 0

    # Total Reading Time (approx 2 mins per page)
    total_reading_hours = int(total_pages_read * 2 / 60)
    
    completion_rate = int(safe_div(total_books_read, len(all_books)) * 100)

    # --- 3. TRENDS & HABITS ---
    # Seasonal Reading
    def get_season(date):
        # Northern hemisphere
        month = date.month
        if month in [12, 1, 2]: return 'Winter'
        elif month in [3, 4, 5]: return 'Spring'
        elif month in [6, 7, 8]: return 'Summer'
        else: return 'Autumn'
        
    seasons = {'Winter': 0, 'Spring': 0, 'Summer': 0, 'Autumn': 0}
    for b in finished_books:
        seasons[get_season(b.date_finished)] += 1
        
    # Genre Diversity (Category Count)
    unique_categories = set()
    for b in all_books:
        if b.categories:
            for cat in b.categories.split(','):
                unique_categories.add(cat.strip())
    diversity_count = len(unique_categories)

    # Re-use existing lists for backwards compatibility if needed, but we have new specific ones
    # Books by Year/Month table data
    books_by_year_month = {}
    for book in finished_books:
        year = book.date_finished.strftime('%Y')
        month = book.date_finished.strftime('%B')
        if year not in books_by_year_month: books_by_year_month[year] = {}
        books_by_year_month[year][month] = books_by_year_month[year].get(month, 0) + 1


    # --- 4. CRAZY STATS & CURIOSITIES ---
    
    # 1. The Tower (height in meters, approx 0.05mm per page)
    tower_height = round(total_pages_read * 0.00005, 2)
    
    # 2. Ink Consumed (guesstimate 1 drop per 100 pages? Let's say ml)
    # Average book page is 250-300 words. 
    # Let's be playful: "Litres of Ink" -> maybe 1ml per 50 pages?
    ink_litres = round(total_pages_read / 50000, 3) 

    # 3. Time Traveler (Most read decade)
    decade_counts = {}
    for b in finished_books:
        if b.published_year and b.published_year.isdigit():
            decade = f"{b.published_year[:3]}0s"
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
    most_read_decade = max(decade_counts.items(), key=lambda x: x[1])[0] if decade_counts else "N/A"

    # 4. Favorite Day to Finish
    day_counts = {}
    for b in finished_books:
        day = b.date_finished.strftime('%A')
        day_counts[day] = day_counts.get(day, 0) + 1
    favorite_day = max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else "Unknown"

    # 5. Polyglot (Language breakdown)
    lang_counts = {}
    for b in finished_books:
        if b.language:
            lang_counts[b.language] = lang_counts.get(b.language, 0) + 1
    # Just passing the dict for now, or finding most common
    num_languages = len(lang_counts)

    # 6. Critic's Choice (Avg Public Rating)
    ratings = [b.average_rating for b in finished_books if b.average_rating]
    avg_public_rating = round(sum(ratings) / len(ratings), 1) if ratings else "N/A"

    # 7. Solo vs Co-op (Author Count)
    solo_count = 0
    coop_count = 0
    for b in finished_books:
        if b.authors:
            if ',' in b.authors: coop_count += 1
            else: solo_count += 1
    solo_ratio = int((solo_count / total_books_read * 100)) if total_books_read else 0

    # 8. Word Count (Millionaire Club)
    # Approx 250 words per page
    total_words = total_pages_read * 250
    words_million = round(total_words / 1000000, 2)

    # 9. Golden Era (Oldest Book Read)
    # Filter valid years
    valid_years = [b for b in finished_books if b.published_year and b.published_year.isdigit()]
    oldest_book = min(valid_years, key=lambda b: int(b.published_year)) if valid_years else None

    # 10. The Marathon (Eye distance)
    # Avg line length 10cm, 30 lines/page -> 3m per page
    distance_km = round(total_pages_read * 3 / 1000, 2)

    # RESTORED: Categories Data for Pie Chart
    category_counts = {}
    for book in finished_books: 
        if book.categories:
            cats = [c.strip() for c in book.categories.split(',')]
            for cat in cats:
                category_counts[cat] = category_counts.get(cat, 0) + 1
    
    # Sort for chart
    sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    # Top 5 + Others
    if len(sorted_cats) > 5:
        top_cats_labels = [c[0] for c in sorted_cats[:5]] + ['Others']
        top_cats_data = [c[1] for c in sorted_cats[:5]] + [sum(c[1] for c in sorted_cats[5:])]
    else:
        top_cats_labels = [c[0] for c in sorted_cats]
        top_cats_data = [c[1] for c in sorted_cats]

    return render_template('stats.html',
                           # Volume
                           total_books=total_books_read,
                           total_pages=total_pages_read,
                           avg_pages=avg_pages_per_book,
                           avg_pages_month=avg_pages_per_month,
                           avg_pages_year=avg_pages_per_year,
                           pages_history_labels=pages_history_labels,
                           pages_history_data=pages_history_data,
                           longest_book=longest_book,
                           shortest_book=shortest_book,
                           
                           # Time
                           avg_days=avg_days_per_book,
                           fastest_book=fastest_book,
                           fastest_days=fastest_days,
                           slowest_book=slowest_book,
                           slowest_days=slowest_days,
                           reading_hours=total_reading_hours,
                           completion_rate=completion_rate,
                           
                           # Trends
                           seasons=seasons,
                           diversity=diversity_count,
                           books_by_year_month=books_by_year_month,
                           cat_labels=top_cats_labels,
                           cat_data=top_cats_data,

                           # Crazy Stats
                           tower_height=tower_height,
                           ink_litres=ink_litres,
                           most_read_decade=most_read_decade,
                           favorite_day=favorite_day,
                           num_languages=num_languages,
                           avg_public_rating=avg_public_rating,
                           solo_ratio=solo_ratio,
                           words_million=words_million,
                           oldest_book=oldest_book,
                           distance_km=distance_km
                           )

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
