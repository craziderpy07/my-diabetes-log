"""My Diabetes Log: educational Flask/PostgreSQL web application."""
import os
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import select, text, inspect
from sqlalchemy.exc import IntegrityError

from algorithms import merge_events, date_range, category_index, glucose_rolling_averages

load_dotenv()
# CSS and other static files live in the public/ folder. Vercel serves that folder
# from its CDN, and this line makes Flask serve it the same way when running locally.
app = Flask(__name__, static_folder='public', static_url_path='')

# The secret key is used for login sessions and CSRF protection
secret_key = os.getenv('SECRET_KEY')
if not secret_key and os.getenv('FLASK_DEBUG') == '1':
    secret_key = 'dev-only-change-me'
if not secret_key:
    raise RuntimeError('Set SECRET_KEY in .env (see .env.example)')
app.config['SECRET_KEY'] = secret_key

# Database connection string from the .env file
url = os.getenv('DATABASE_URL')
if not url:
    raise RuntimeError('Set DATABASE_URL to your Neon PostgreSQL connection string')
if url.startswith('postgres://'):
    url = 'postgresql://' + url[len('postgres://'):]
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Check a database connection is still alive before using it (helps with serverless hosting like Vercel)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('COOKIE_SECURE') == '1'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024

# Set up the database, CSRF protection and login manager
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------- Database models ----------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    # Nullable so accounts created before usernames existed keep working. Stored lowercase.
    username = db.Column(db.String(30), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    value = db.Column(db.Float, nullable=True)
    notes = db.Column(db.String(500), nullable=False, default='')
    __table_args__ = (db.Index('ix_entry_user_kind_time', 'user_id', 'kind', 'timestamp'),)

# ---------- Settings and helper functions ----------

# Number of timeline records shown on each page
PER_PAGE = 5

# Record types: key -> (label shown to the user, unit of measurement)
KINDS = {
    'glucose': ('Glucose', 'mg/dL'),
    'meal': ('Meal', 'g carbs'),
    'exercise': ('Exercise', 'minutes'),
    'medication': ('Medication', ''),
}

# Records are entered and shown in Pacific time (labelled PST) and stored in UTC.
PT = ZoneInfo('America/Los_Angeles')

def parse_local_datetime(date_text, time_text, ampm=''):
    """Parse MM/DD/YYYY, HH:MM and AM/PM entered in Pacific time."""
    msg = 'Enter the date as MM/DD/YYYY and the time as HH:MM AM/PM.'
    # Put the time and AM/PM together, for example "08:05 PM"
    time_string = f"{time_text or ''} {ampm or ''}".strip().upper()
    m = re.fullmatch(r'(\d{1,2}):(\d{2})\s*([AP]M)', time_string)
    if not m:
        raise ValueError(msg)
    try:
        day = datetime.strptime((date_text or '').strip(), '%m/%d/%Y')
        clock = datetime.strptime(f'{m[1]}:{m[2]} {m[3]}', '%I:%M %p')
    except ValueError:
        raise ValueError(msg)
    if not 1900 <= day.year <= 2100:
        raise ValueError('Enter a year between 1900 and 2100.')
    return datetime.combine(day.date(), clock.time(), tzinfo=PT)

@app.template_filter('pst')
def pst_filter(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PT).strftime('%b %d, %Y · %I:%M %p')

USERNAME_RE = re.compile(r'^[a-z0-9_.-]{3,30}$')

def normalize_username(raw):
    return (raw or '').strip().lower()

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

def event_dict(e):
    return {'id': e.id, 'kind': e.kind, 'timestamp': e.timestamp, 'title': e.title, 'value': e.value, 'notes': e.notes}

def get_timeline():
    streams = []
    for kind in KINDS:
        entries = db.session.scalars(select(Entry).where(Entry.user_id == current_user.id, Entry.kind == kind).order_by(Entry.timestamp, Entry.id)).all()
        streams.append([event_dict(e) for e in entries])
    return merge_events(streams)

def parse_entry(form):
    kind = form.get('kind', '')
    if kind not in KINDS:
        raise ValueError('Select a valid record type.')
    title = form.get('title', '').strip()
    notes = form.get('notes', '').strip()
    if not title or len(title) > 120 or len(notes) > 500:
        raise ValueError('Provide a title (max 120 characters) and notes under 500 characters.')
    timestamp = parse_local_datetime(form.get('date', ''), form.get('time', ''), form.get('ampm', ''))
    value_text = form.get('value', '').strip()
    value = None
    if kind != 'medication':
        try:
            value = float(value_text)
        except ValueError:
            raise ValueError('Enter a numeric value.')
        if not (0 < value <= 1000 if kind == 'glucose' else 0 <= value <= 100000):
            raise ValueError('Enter a valid nonnegative value (glucose must be positive).')
    return kind, timestamp, title, value, notes

# ---------- Routes ----------

@app.route('/')
@login_required
def index():
    events = get_timeline()
    start_str = request.args.get('start', '')
    end_str = request.args.get('end', '')
    kind = request.args.get('kind', '')
    try:
        if start_str or end_str:
            # If one side is left empty, use the earliest/latest possible date
            start = datetime.min.replace(tzinfo=timezone.utc)
            end = datetime.max.replace(tzinfo=timezone.utc)
            if start_str:
                start = datetime.fromisoformat(start_str).replace(tzinfo=PT)
            if end_str:
                # Include everything up to the end of the chosen day
                end = datetime.fromisoformat(end_str).replace(tzinfo=PT) + timedelta(days=1, microseconds=-1)
            events = date_range(events, start, end)
    except ValueError:
        flash('Invalid date filter.', 'error')
    if kind in KINDS:
        events = category_index(events).get(kind, [])
    readings = [{'timestamp': e['timestamp'], 'value': e['value']} for e in events if e['kind'] == 'glucose']
    average = None
    if readings:
        average = round(sum(r['value'] for r in readings) / len(readings), 1)
    rolling = glucose_rolling_averages(readings)
    # Show only PER_PAGE records at a time, newest first
    total = len(events)
    pages = max(1, -(-total // PER_PAGE))
    page = min(max(request.args.get('page', 1, type=int), 1), pages)
    page_events = list(reversed(events))[(page - 1) * PER_PAGE: page * PER_PAGE]
    return render_template('index.html', events=page_events, kinds=KINDS, average=average, rolling=rolling, count=total, start=start_str, end=end_str, selected_kind=kind, page=page, pages=pages)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = normalize_username(request.form.get('username'))
        password = request.form.get('password', '')
        if '@' not in email or len(email) > 255 or len(password) < 12:
            flash('Use a valid email and a password of at least 12 characters.', 'error')
        elif not USERNAME_RE.match(username):
            flash('Username must be 3-30 characters: letters, numbers, dots, hyphens, or underscores.', 'error')
        elif db.session.scalar(select(User).where(User.email == email)):
            flash('An account with this email already exists.', 'error')
        elif db.session.scalar(select(User).where(User.username == username)):
            flash('That username is already taken.', 'error')
        else:
            user = User(email=email, username=username, password_hash=generate_password_hash(password))
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('That email or username is already taken.', 'error')
                return render_template('auth.html', mode='register', form_email=email, form_username=username)
            login_user(user)
            return redirect(url_for('index'))
        return render_template('auth.html', mode='register', form_email=email, form_username=username)
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip().lower()
        # Usernames can never contain '@', so the two are unambiguous.
        column = User.email if '@' in identifier else User.username
        user = db.session.scalar(select(User).where(column == identifier)) if identifier else None
        if user and check_password_hash(user.password_hash, request.form.get('password', '')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email/username or password.', 'error')
    return render_template('auth.html', mode='login')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def json_error(message, status=400):
    return jsonify(ok=False, message=message), status

@app.route('/account')
@login_required
def account():
    """Personal Information page (the forms on it save through the two routes below)."""
    return render_template('account.html')

@app.route('/account/update', methods=['POST'])
@login_required
def update_account():
    """Save a new username and/or email to the database."""
    email = request.form.get('email', '').strip().lower()
    username = normalize_username(request.form.get('username'))
    current_password = request.form.get('current_password', '')

    # Check everything before changing anything
    if not check_password_hash(current_user.password_hash, current_password):
        return json_error('Current password is incorrect.')
    if '@' not in email or len(email) > 255:
        return json_error('Enter a valid email address.')
    if not USERNAME_RE.match(username):
        return json_error('Username must be 3-30 characters: letters, numbers, dots, hyphens, or underscores.')
    if db.session.scalar(select(User).where(User.email == email, User.id != current_user.id)):
        return json_error('An account with this email already exists.')
    if db.session.scalar(select(User).where(User.username == username, User.id != current_user.id)):
        return json_error('That username is already taken.')

    current_user.email = email
    current_user.username = username
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return json_error('That email or username is already taken.')
    return jsonify(ok=True, message='Personal information updated.', username=username, email=email)

@app.route('/account/password', methods=['POST'])
@login_required
def change_password():
    """Replace the user's password with a new one."""
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not check_password_hash(current_user.password_hash, current_password):
        return json_error('Current password is incorrect.')
    if len(new_password) < 12:
        return json_error('New password must be at least 12 characters.')
    if new_password != confirm_password:
        return json_error('New password and confirmation do not match.')
    if new_password == current_password:
        return json_error('New password must be different from your current password.')

    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify(ok=True, message='Password changed.')

@app.route('/entry/new', methods=['GET', 'POST'])
@login_required
def new_entry():
    if request.method == 'POST':
        try:
            kind, timestamp, title, value, notes = parse_entry(request.form)
            db.session.add(Entry(user_id=current_user.id, kind=kind, timestamp=timestamp, title=title, value=value, notes=notes))
            db.session.commit()
            flash('Record added.', 'success')
            return redirect(url_for('index'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template('entry.html', entry=None, kinds=KINDS, form=request.form)

def owned_entry(entry_id):
    entry = db.session.scalar(select(Entry).where(Entry.id == entry_id, Entry.user_id == current_user.id))
    if entry is None:
        abort(404)
    return entry

@app.route('/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
    entry = owned_entry(entry_id)
    if request.method == 'POST':
        try:
            entry.kind, entry.timestamp, entry.title, entry.value, entry.notes = parse_entry(request.form)
            db.session.commit()
            flash('Record updated.', 'success')
            return redirect(url_for('index'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template('entry.html', entry=entry, kinds=KINDS, form=request.form)

@app.route('/entry/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_entry(entry_id):
    entry = owned_entry(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash('Record deleted.', 'success')
    return redirect(url_for('index'))

@app.cli.command('init-db')
def init_db():
    db.create_all()
    # create_all() does not alter existing tables, so add the username column to older databases.
    columns = [c['name'] for c in inspect(db.engine).get_columns('user')]
    if 'username' not in columns:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN username VARCHAR(30)'))
            conn.execute(text('CREATE UNIQUE INDEX ix_user_username ON "user" (username)'))
        print('Added username column to existing user table.')
    print('Database tables created. For production schema changes, use migrations.')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')
