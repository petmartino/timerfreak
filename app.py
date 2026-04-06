"""
TimerFreak Flask Application
Copyright (c) 2025 - Pet Martino

This software is licensed under the MIT License.
See the LICENSE file for more details.

"""
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, session, send_file
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import secrets
import json
import logging
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Integer, String, ForeignKey, extract
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, joinedload
from flask_migrate import Migrate
from datetime import datetime, timedelta, timezone
from functools import wraps
from collections import defaultdict, OrderedDict
import time
from sqlalchemy.types import TypeDecorator, DateTime as SQLADateTime
from dateutil import parser
from __version__ import __version__ as APP_VERSION
import qrcode
import io

# Import models from models.py
from models import db, User, Sequence, Timer, Sound, CounterLog, UserActivityLog, OAuthAccount, SubscriptionTier, SequenceShare, PreviewTempData, TimerCategory

class UTCDateTime(TypeDecorator):
    """
    A DateTime type that handles timezone conversion for SQLite.
    Stores naive UTC datetime objects in the database,
    and returns timezone-aware UTC datetime objects in Python.
    """
    impl = SQLADateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """
        Processes the Python datetime object before sending it to the database.
        Converts aware datetimes to naive UTC datetimes.
        """
        if value is None:
            return value # If value is None (e.g., if column is nullable and not set), return None.

        if value.tzinfo is None:
            # If the datetime object is naive, we assume it's already in UTC.
            naive_utc_dt = value
        else:
            # If the datetime object is timezone-aware, convert it to UTC and remove tzinfo.
            # This creates a naive datetime that represents UTC.
            naive_utc_dt = value.astimezone(timezone.utc).replace(tzinfo=None)
        
        # Return the datetime object, not a string.
        return naive_utc_dt

    def process_result_value(self, value, dialect):
        """
        Processes the value retrieved from the database.
        Converts it into a timezone-aware UTC datetime object.
        """
        if value is None:
            return value

        dt = None
        if isinstance(value, str):
            # Attempt to parse with microseconds first
            try:
                dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                # Fallback to parsing without microseconds if not found
                try:
                    dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # If still fails, use dateutil.parser as a last resort for robustness
                    try:
                        dt = parser.parse(value)
                    except Exception:
                        return value
        elif isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = parser.parse(str(value))
            except Exception:
                return value

        # Attach UTC timezone info to the parsed naive datetime object
        if dt and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        elif dt: 
            return dt
        
        return value
    
class ScriptNameMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            if script_name.startswith('/'):
                script_name = script_name[1:]
            environ['SCRIPT_NAME'] = '/' + script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith('/' + script_name):
                environ['PATH_INFO'] = path_info[len(script_name)+1:]
        return self.app(environ, start_response)

app = Flask(__name__, static_url_path='/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_prefix=1)
app.wsgi_app = ScriptNameMiddleware(app.wsgi_app)

# Security: Require FLASK_SECRET_KEY to be set in production
secret_key = os.environ.get('FLASK_SECRET_KEY')
if not secret_key:
    # Generate a random secret key for development only
    secret_key = secrets.token_hex(32)
    app.logger.warning("FLASK_SECRET_KEY not set. Using auto-generated random key (NOT for production).")
app.secret_key = secret_key

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))

# Support both instance/ and root-level database paths
# (local dev uses instance/, some deployments use root level)
if os.path.exists(os.path.join(basedir, 'instance', 'timerfreak.db')):
    db_path = os.path.join(basedir, 'instance', 'timerfreak.db')
elif os.path.exists(os.path.join(basedir, 'timerfreak.db')):
    db_path = os.path.join(basedir, 'timerfreak.db')
else:
    # Default to instance/ for new deployments
    db_path = os.path.join(basedir, 'instance', 'timerfreak.db')
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_TIME_LIMIT'] = 3600

# Log database path on startup
app.logger.info(f"Using database: {db_path}")

# Session configuration for "Remember Me" functionality
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# OAuth configuration
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')
app.config['GITHUB_CLIENT_ID'] = os.environ.get('GITHUB_CLIENT_ID')
app.config['GITHUB_CLIENT_SECRET'] = os.environ.get('GITHUB_CLIENT_SECRET')

# Initialize database with app
db.init_app(app)
migrate = Migrate(app, db)

# Application defaults
DEFAULT_TIMER_COLOR = "#0cd413"
FALLBACK_ALARM_SOUND_FILENAME = "alarm.mp3"

# Initialize authentication
from auth import init_auth, login_manager, log_user_activity, owner_required
init_auth(app)


@app.context_processor
def inject_global_data():
    from flask_login import current_user
    return dict(
        current_year=datetime.now().year,
        app_version=APP_VERSION,
        current_user=current_user if current_user.is_authenticated else None
    )

@app.route("/")
def index():
    # Fetch available sounds from the database
    available_sounds_raw = Sound.query.order_by(Sound.name).all()
    available_sounds_for_template = [s.to_dict() for s in available_sounds_raw]

    # --- MODIFIED: Determine default sound filename from DB ---
    default_sound_obj = next((s for s in available_sounds_raw if s.default == 1), None)
    if default_sound_obj:
        default_alarm_sound_filename = default_sound_obj.filename
    else:
        # Fallback if no sound is marked as default
        app.logger.warning(f"No default sound found in database (default=1). Falling back to {FALLBACK_ALARM_SOUND_FILENAME}.")
        default_alarm_sound_filename = FALLBACK_ALARM_SOUND_FILENAME
    # --- END MODIFIED ---

    # Fetch most used sequences from the database (EXISTING CODE)
    sequence_start_counts = db.session.query(
        CounterLog.sequence_id,
        func.count(CounterLog.id).label('start_count')
    ).filter(CounterLog.event_type == 'sequence_start')\
    .group_by(CounterLog.sequence_id).subquery()

    sequence_timer_info = db.session.query(
        Timer.sequence_id,
        func.count(Timer.id).label('timer_count'),
        func.sum(Timer.duration).label('total_sequence_duration')
    ).group_by(Timer.sequence_id).subquery()

    most_used_sequences_query = db.session.query(
        Sequence.id,
        Sequence.name,
        sequence_start_counts.c.start_count,
        sequence_timer_info.c.timer_count,
        sequence_timer_info.c.total_sequence_duration
    ).join(sequence_start_counts, Sequence.id == sequence_start_counts.c.sequence_id)\
    .outerjoin(sequence_timer_info, Sequence.id == sequence_timer_info.c.sequence_id)\
    .order_by(sequence_start_counts.c.start_count.desc())\
    .limit(35)

    most_used_sequences_raw = most_used_sequences_query.all()

    most_used_sequences = []
    for seq in most_used_sequences_raw:
        total_seconds = seq.total_sequence_duration if seq.total_sequence_duration is not None else 0
        start_count = seq.start_count if seq.start_count is not None else 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        duration_parts = []
        if hours > 0:
            duration_parts.append(f"{hours}h")
        if minutes > 0:
            duration_parts.append(f"{minutes}m")
        if seconds > 0 or (total_seconds == 0 and not duration_parts):
            duration_parts.append(f"{seconds}s")

        duration_display = " ".join(duration_parts) if duration_parts else "0s"

        most_used_sequences.append({
            'id': seq.id,
            'name': seq.name if seq.name else f'Unnamed Sequence',
            'use_count': start_count,
            'timer_count': seq.timer_count if seq.timer_count is not None else 0,
            'total_duration_display': duration_display.strip()
        })

    # Division by zero protection for avg_timers calculation in template context
    total_sequences_count = Sequence.query.count()
    total_timers_count = Timer.query.count()
    avg_timers_per_sequence = total_timers_count / total_sequences_count if total_sequences_count > 0 else 0

    # Initialize prefilled data variables
    prefilled_timers = None
    prefilled_sequence_name = None
    prefilled_loop_default = False
    prefilled_loop_count = None

    # Priority 1: URL-based prefill_token (survives server restarts)
    prefill_token = request.args.get('prefill_token', '')
    if prefill_token:
        temp_data = PreviewTempData.query.filter_by(preview_token=prefill_token).first()
        if temp_data:
            try:
                prefilled_timers = json.loads(temp_data.timers_data) if temp_data.timers_data else None
                prefilled_sequence_name = temp_data.sequence_name
                prefilled_loop_default = bool(temp_data.loop_default)
                prefilled_loop_count = temp_data.loop_count
            except (json.JSONDecodeError, TypeError):
                pass

    # Priority 2: Session-based prefilled data (only if no URL token found data)
    if prefilled_timers is None:
        prefilled_timers = session.pop('preview_timers', None)
        prefilled_sequence_name = session.pop('preview_sequence_name', None)
        prefilled_loop_default = session.pop('preview_loop_default', False)
        prefilled_loop_count = session.pop('preview_loop_count', None)

    # Priority 3: Session-based DB lookup (legacy fallback) - get most recent entry
    if prefilled_timers is None and 'session_id' in session:
        temp_data = PreviewTempData.query.filter_by(session_id=session['session_id']).order_by(PreviewTempData.created_at.desc()).first()
        if temp_data:
            try:
                prefilled_timers = json.loads(temp_data.timers_data) if temp_data.timers_data else None
                prefilled_sequence_name = temp_data.sequence_name
                prefilled_loop_default = bool(temp_data.loop_default)
                prefilled_loop_count = temp_data.loop_count
            except (json.JSONDecodeError, TypeError):
                pass

    return render_template("index.html",
                           available_sounds=available_sounds_for_template,
                           most_used_sequences=most_used_sequences,
                           DEFAULT_TIMER_COLOR=DEFAULT_TIMER_COLOR,
                           DEFAULT_ALARM_SOUND_FILENAME=default_alarm_sound_filename,
                           prefilled_timers=prefilled_timers,
                           prefilled_sequence_name=prefilled_sequence_name,
                           prefilled_loop_default=prefilled_loop_default,
                           prefilled_loop_count=prefilled_loop_count,
                           prefill_token=prefill_token or '')

@app.route("/browse")
def browse():
    """Browse public Timers - top 100 by usage, grouped by category"""
    # Fetch all public Timers with their stats using subqueries to avoid cartesian product
    timer_counts = db.session.query(
        Timer.sequence_id,
        db.func.count(Timer.id).label('timer_count'),
        db.func.sum(Timer.duration).label('total_duration')
    ).group_by(Timer.sequence_id).subquery()

    # Top 100 sequences by use count
    Timers_query = db.session.query(
        Sequence,
        db.func.count(CounterLog.id).label('start_count'),
        timer_counts.c.timer_count,
        timer_counts.c.total_duration
    ).outerjoin(CounterLog, Sequence.id == CounterLog.sequence_id)\
    .outerjoin(timer_counts, Sequence.id == timer_counts.c.sequence_id)\
    .filter(Sequence.is_public == True)\
    .group_by(Sequence.id, timer_counts.c.timer_count, timer_counts.c.total_duration)\
    .order_by(db.func.count(CounterLog.id).desc().nullslast())\
    .limit(100).all()

    # Fetch all categories
    categories = TimerCategory.query.filter_by(is_active=1).order_by(TimerCategory.sort_order).all()
    category_map = {c.id: c for c in categories}

    # Build timer list with category info (ordered by category sort_order)
    categorized = OrderedDict()
    for c in categories:
        categorized[c.id] = []
    uncategorized = []

    for seq, start_count, timer_count, total_duration in Timers_query:
        total_seconds = total_duration if total_duration else 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        duration_parts = []
        if hours > 0:
            duration_parts.append(f"{hours}h")
        if minutes > 0:
            duration_parts.append(f"{minutes}m")
        if seconds > 0 or not duration_parts:
            duration_parts.append(f"{seconds}s")

        duration_display = " ".join(duration_parts)

        timer_data = {
            'id': seq.id,
            'name': seq.name if seq.name else 'Unnamed Timer',
            'use_count': start_count or 0,
            'timer_count': timer_count or 0,
            'total_duration_display': duration_display.strip()
        }

        if seq.category_id and seq.category_id in category_map:
            categorized[seq.category_id].append(timer_data)
        else:
            uncategorized.append(timer_data)

    return render_template("browse.html",
                           categories=categorized,
                           uncategorized=uncategorized,
                           category_map=category_map)

@app.route("/timer", methods=["POST"])
def start_timer():
    if request.form.get('website'):
        app.logger.warning("Honeypot field filled. Bot detected, redirecting to index.")
        return redirect(url_for('index', error="Bot activity detected."))

    sequence_name = request.form.get("Timer_name") or request.form.get("sequence_name")
    timer_names = request.form.getlist("timer_name[]")
    hours = request.form.getlist("hours[]")
    minutes = request.form.getlist("minutes[]")
    seconds = request.form.getlist("seconds[]")
    colors = request.form.getlist("color[]")
    alarm_sounds = request.form.getlist("alarm_sound[]")

    timers_data = []

    num_timers = len(hours)

    # Pad alarm_sounds with default if fewer than num_timers (handles missing select values)
    default_sound_obj = Sound.query.filter_by(default=1).first()
    if default_sound_obj:
        default_alarm_sound_for_db_save = default_sound_obj.filename
    else:
        default_alarm_sound_for_db_save = FALLBACK_ALARM_SOUND_FILENAME

    original_sound_count = len(alarm_sounds)
    while len(alarm_sounds) < num_timers:
        alarm_sounds.append(default_alarm_sound_for_db_save)

    # Log for debugging
    if original_sound_count < num_timers:
        app.logger.warning(f"Padded alarm_sounds from {original_sound_count} to {num_timers} with default sound")

    if not (num_timers == len(minutes) == len(seconds) == len(colors)):
        app.logger.error(f"Error: Inconsistent list lengths for timer parameters. hours={len(hours)}, minutes={len(minutes)}, seconds={len(seconds)}, colors={len(colors)}, names={len(timer_names)}")
        return redirect(url_for('index', error="Inconsistent timer data provided."))

    # Get all valid sound filenames from database for validation
    valid_sound_filenames = {s.filename for s in Sound.query.all()}
    valid_sound_filenames.add(FALLBACK_ALARM_SOUND_FILENAME)  # Always allow fallback


    for i in range(num_timers):
        try:
            h = int(hours[i] or 0)
            m = int(minutes[i] or 0)
            s = int(seconds[i] or 0)
            total_seconds = h * 3600 + m * 60 + s

            if total_seconds <= 0:
                app.logger.warning(f"Timer {i+1} has non-positive duration ({total_seconds}s). Skipping this timer.")
                continue

            # Validate sound filename against database
            submitted_sound = alarm_sounds[i] if alarm_sounds[i] else default_alarm_sound_for_db_save
            if submitted_sound not in valid_sound_filenames:
                app.logger.warning(f"Invalid sound filename '{submitted_sound}' for timer {i+1}. Using default.")
                submitted_sound = default_alarm_sound_for_db_save

            timers_data.append({
                'name': timer_names[i] if i < len(timer_names) else None,
                'duration': total_seconds,
                'color': colors[i] if i < len(colors) else DEFAULT_TIMER_COLOR,
                # Use the validated alarm sound
                'alarm_sound': submitted_sound
            })
        except ValueError as e:
            app.logger.error(f"Error parsing timer duration for timer {i+1}: {e}")
            return redirect(url_for('index', error="Invalid timer duration provided."))

    if not timers_data:
        app.logger.warning("No valid timers submitted after parsing. All timers had zero or negative duration.")
        return redirect(url_for('index', error="No valid timers submitted. Please ensure at least one timer has a duration greater than 0."))

    # Capture loop settings from form
    loop_default = request.form.get('loop_default') == 'on'
    loop_count_raw = request.form.get('loop_count')
    loop_count = None
    if loop_default and loop_count_raw:
        try:
            loop_count = int(loop_count_raw)
            if loop_count < 1:
                loop_count = None  # Treat invalid numbers as unlimited
        except (ValueError, TypeError):
            loop_count = None  # Empty or invalid = unlimited

    sequence_id = secrets.token_urlsafe(8)

    # Create sequence with owner if user is logged in
    from flask_login import current_user
    owner_id = current_user.id if current_user.is_authenticated else None

    sequence = Sequence(
        id=sequence_id,
        name=sequence_name,
        owner_id=owner_id,
        is_public=True  # Public by default for backward compatibility
    )
    db.session.add(sequence)

    for i, data in enumerate(timers_data):
        timer = Timer(
            sequence_id=sequence_id,
            timer_name=data['name'],
            duration=data['duration'],
            timer_order=i,
            color=data['color'],
            alarm_sound=data['alarm_sound'],
            loop_default=loop_default,
            loop_count=loop_count
        )
        db.session.add(timer)
    db.session.commit()

    # Log sequence start with owner info
    log = CounterLog(
        sequence_id=sequence_id,
        event_type='sequence_start',
        owner_id=owner_id
    )
    db.session.add(log)
    db.session.commit()

    # Log user activity if logged in
    if current_user.is_authenticated:
        log_user_activity('create_sequence', 'sequence', sequence_id=sequence_id)

    # Clean up temporary preview data since the form has been successfully created
    prefill_token_from_form = request.form.get('prefill_token', '')
    if prefill_token_from_form:
        temp_data = PreviewTempData.query.filter_by(preview_token=prefill_token_from_form).first()
        if temp_data:
            db.session.delete(temp_data)
            app.logger.info(f"Cleaned up temp data for prefill_token: {prefill_token_from_form[:20]}...")
    # Also clear session preview data and legacy session_id-based temp data
    session.pop('preview_timers', None)
    session.pop('preview_sequence_name', None)
    session.pop('preview_loop_default', None)
    session.pop('preview_loop_count', None)
    if 'session_id' in session:
        legacy_temp = PreviewTempData.query.filter_by(session_id=session['session_id']).first()
        if legacy_temp:
            db.session.delete(legacy_temp)
            app.logger.info(f"Cleaned up legacy temp data for session_id: {session['session_id'][:20]}...")
    db.session.commit()

    app.logger.info(f"Created sequence {sequence_id} with {len(timers_data)} timers.")
    return redirect(url_for('preview_sequence', sequence_id=sequence_id))

@app.route("/timer/<sequence_id>")
def show_timer(sequence_id):
    sequence = Sequence.query.options(joinedload(Sequence.timers)).get_or_404(sequence_id)

    timers_in_order = sequence.timers

    timers_durations = [timer.duration for timer in timers_in_order]
    timer_names = [timer.timer_name if timer.timer_name else f"Timer {timer.timer_order + 1}" for timer in timers_in_order]
    timer_colors = [timer.color for timer in timers_in_order]
    timer_alarm_sounds = [timer.alarm_sound for timer in timers_in_order]

    # Get loop settings from the first timer (they're the same for all timers in a sequence)
    # Handle NULL values for existing timers created before migration
    loop_default = bool(timers_in_order[0].loop_default) if timers_in_order else False
    loop_count = timers_in_order[0].loop_count if (timers_in_order and timers_in_order[0].loop_count is not None) else None

    all_available_sounds_db = Sound.query.order_by(Sound.name).all()
    all_available_sound_filenames = [s.filename for s in all_available_sounds_db]

    sequence_name_for_logs = sequence.name if sequence.name else f"Timer {sequence_id}"

    # Generate or get share token
    share = SequenceShare.query.filter_by(sequence_id=sequence_id).first()
    if not share:
        share = SequenceShare(
            sequence_id=sequence_id,
            share_token=secrets.token_urlsafe(16),
            is_public=sequence.is_public,
            allow_copy=True
        )
        db.session.add(share)
        db.session.commit()

    # Generate share URL
    share_url = url_for('show_timer', sequence_id=sequence_id, _external=True)
    qr_code_url = url_for('qr_code', sequence_id=sequence_id)

    return render_template("timer.html",
                           timers=timers_durations,
                           timer_names=timer_names,
                           sequence_name=sequence.name,
                           sequence_id=sequence_id,
                           timer_colors=timer_colors,
                           alarm_sounds=all_available_sound_filenames,
                           timer_alarm_sounds=timer_alarm_sounds,
                           sequence_name_for_logs=sequence_name_for_logs,
                           base_url=request.host_url.rstrip('/'),
                           share_url=share_url,
                           share_token=share.share_token,
                           qr_code_url=qr_code_url,
                           loop_default=loop_default,
                           loop_count=loop_count)

@app.route("/qr/<sequence_id>.png")
def qr_code(sequence_id):
    """Generate and serve QR code for timer sequence"""
    from flask import make_response
    sequence = db.session.get(Sequence, sequence_id) or abort(404)
    share_url = url_for('show_timer', sequence_id=sequence_id, _external=True)

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(share_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Save to bytes
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    response = make_response(send_file(img_io, mimetype='image/png'))
    # Cache QR code for 30 days
    response.headers['Cache-Control'] = 'public, max-age=2592000'
    return response

@app.route("/preview/<sequence_id>")
def preview_sequence(sequence_id):
    """Preview page showing timers in order with arrows before starting"""
    sequence = Sequence.query.options(joinedload(Sequence.timers)).get_or_404(sequence_id)

    timers_in_order = sequence.timers

    timers_data = []
    for timer in timers_in_order:
        timer_name = timer.timer_name if timer.timer_name else f"Timer {timer.timer_order + 1}"
        hours = timer.duration // 3600
        minutes = (timer.duration % 3600) // 60
        seconds = timer.duration % 60
        duration_parts = []
        if hours > 0:
            duration_parts.append(f"{hours}h")
        if minutes > 0:
            duration_parts.append(f"{minutes}m")
        duration_parts.append(f"{seconds}s")
        duration_display = " ".join(duration_parts)

        timers_data.append({
            'order': timer.timer_order,
            'name': timer_name,
            'duration': duration_display,
            'color': timer.color,
            'total_seconds': timer.duration
        })

    # Get loop settings
    # Handle NULL values for existing timers created before migration
    loop_default = bool(timers_in_order[0].loop_default) if timers_in_order else False
    loop_count = timers_in_order[0].loop_count if (timers_in_order and timers_in_order[0].loop_count is not None) else None

    # Generate a URL-based preview token that survives server restarts
    preview_token = secrets.token_urlsafe(32)

    # Store timer data in session for backward compatibility (cookie-based, may break on restart)
    session['preview_timers'] = [
        {
            'name': t.timer_name,
            'duration': t.duration,
            'color': t.color,
            'alarm_sound': t.alarm_sound
        }
        for t in timers_in_order
    ]
    session['preview_sequence_name'] = sequence.name
    session['preview_loop_default'] = loop_default
    session['preview_loop_count'] = loop_count

    # Persist form data to database with the preview_token for reliable back-button restoration
    timers_json = json.dumps([
        {
            'name': t.timer_name,
            'duration': t.duration,
            'color': t.color,
            'alarm_sound': t.alarm_sound
        }
        for t in timers_in_order
    ])

    temp_data = PreviewTempData(
        preview_token=preview_token,
        session_id=session.get('session_id'),
        sequence_name=sequence.name,
        timers_data=timers_json,
        loop_default=loop_default,
        loop_count=loop_count
    )
    db.session.add(temp_data)
    db.session.commit()

    return render_template("preview.html",
                           sequence=sequence,
                           sequence_id=sequence_id,
                           timers=timers_data,
                           loop_default=loop_default,
                           loop_count=loop_count,
                           preview_token=preview_token)

@app.route("/preview_back")
def preview_back():
    """Redirect to index with prefilled form data from preview"""
    token = request.args.get('token', '')
    if token:
        return redirect(url_for('index', prefill_token=token))
    return redirect(url_for('index'))

@app.route("/clone/<sequence_id>")
def clone_timer(sequence_id):
    """Clone a timer sequence - store data and redirect to index with prefilled form"""
    sequence = Sequence.query.options(joinedload(Sequence.timers)).get_or_404(sequence_id)
    timers_in_order = sequence.timers

    # Generate a new preview_token for the cloned data
    preview_token = secrets.token_urlsafe(32)

    # Get loop settings
    loop_default = bool(timers_in_order[0].loop_default) if timers_in_order else False
    loop_count = timers_in_order[0].loop_count if (timers_in_order and timers_in_order[0].loop_count is not None) else None

    # Clean up any existing temp data for this session to avoid conflicts
    current_session_id = session.get('session_id')
    if current_session_id:
        old_temp = PreviewTempData.query.filter_by(session_id=current_session_id).all()
        for old in old_temp:
            db.session.delete(old)

    # Store timer data in database
    timers_json = json.dumps([
        {
            'name': t.timer_name,
            'duration': t.duration,
            'color': t.color,
            'alarm_sound': t.alarm_sound
        }
        for t in timers_in_order
    ])

    temp_data = PreviewTempData(
        preview_token=preview_token,
        session_id=current_session_id,
        sequence_name=sequence.name,
        timers_data=timers_json,
        loop_default=loop_default,
        loop_count=loop_count
    )
    db.session.add(temp_data)
    db.session.commit()

    # Redirect to index with the new prefill_token
    return redirect(url_for('index', prefill_token=preview_token))

@app.route("/<string:sequence_id>")
def redirect_to_timer(sequence_id):
    sequence = db.session.get(Sequence, sequence_id)
    if sequence:
        return redirect(url_for('show_timer', sequence_id=sequence_id))
    else:
        return redirect(url_for('index', error=f"Sequence '{sequence_id}' not found."))

@app.route("/log_activity", methods=["POST"])
@csrf.exempt
def log_activity():
    # Rate limiting check
    client_ip = get_client_ip()
    if not check_rate_limit(client_ip):
        app.logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return jsonify({'message': 'Rate limit exceeded. Try again later.'}), 429
    
    data = request.get_json()
    sequence_id = data.get('sequence_id')
    timer_order = data.get('timer_order')
    event_type = data.get('event_type')

    app.logger.debug(f"Received log activity: sequence_id={sequence_id}, timer_order={timer_order}, event_type={event_type}")

    if not sequence_id or not event_type:
        app.logger.error(f"Missing data for log activity. Received: {data}")
        return jsonify({'message': 'Missing data (sequence_id or event_type)'}), 400

    try:
        timer_order_int = None
        if timer_order is not None:
            try:
                timer_order_int = int(timer_order)
            except (ValueError, TypeError):
                app.logger.error(f"Invalid timer_order format: {timer_order} (type: {type(timer_order)})")
                return jsonify({'message': 'Invalid timer_order format'}), 400

        # Get owner info from sequence if available
        sequence = db.session.get(Sequence, sequence_id)
        owner_id = sequence.owner_id if sequence else None

        log = CounterLog(
            sequence_id=sequence_id,
            timer_order=timer_order_int,
            event_type=event_type,
            owner_id=owner_id
        )
        db.session.add(log)
        db.session.commit()
        app.logger.info(f"Activity logged successfully: Seq={sequence_id}, TimerOrder={timer_order_int}, Event={event_type}")
        
        # Log user activity if logged in
        from flask_login import current_user
        if current_user.is_authenticated:
            log_user_activity(event_type, 'timer', sequence_id=sequence_id, timer_order=timer_order_int)
        
        return jsonify({'message': 'Activity logged successfully'}), 201
    except Exception as e:
        db.session.rollback()
        app.logger.exception(f"Database error logging activity: {data}")
        return jsonify({'message': 'Failed to log activity', 'error': str(e)}), 500

@app.route("/logs/<sequence_id>")
def show_logs(sequence_id):
    sequence = db.session.get(Sequence, sequence_id) or abort(404)

    logs_raw = db.session.query(CounterLog, Timer)\
                     .outerjoin(Timer, (CounterLog.sequence_id == Timer.sequence_id) & (CounterLog.timer_order == Timer.timer_order))\
                     .filter(CounterLog.sequence_id == sequence_id)\
                     .order_by(CounterLog.timestamp).all()

    logs_formatted = []
    # Define the target display timezone. UTC is safer than hardcoded local time.
    # Ideally, this should be handled on the client side based on their browser settings.
    display_timezone = timezone.utc

    # In app.py, inside show_logs function:
    for log_entry, timer_info in logs_raw:
        utc_timestamp = log_entry.timestamp
        # Ensure the timestamp is timezone-aware as UTC
        if utc_timestamp.tzinfo is None:
            utc_timestamp = utc_timestamp.replace(tzinfo=timezone.utc)


        # Convert to the desired display timezone
        display_timestamp = utc_timestamp.astimezone(display_timezone)

        log_dict = {
            'id': log_entry.id,
            'sequence_id': log_entry.sequence_id,
            'timer_order': log_entry.timer_order,
            'event_type': log_entry.event_type,
            # Pass the converted timestamp to the template
            'timestamp': display_timestamp,
            'timer_name': timer_info.timer_name if timer_info else None
        }
        logs_formatted.append(log_dict)

    sequence_name_display = sequence.name if sequence.name else f"Sequence {sequence_id}"
    return render_template("logs.html", logs=logs_formatted, sequence_id=sequence_id, sequence_name_for_logs=sequence_name_display)
# Rate limiting for /log_activity endpoint
_rate_limit_store = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 100  # max requests per window

def check_rate_limit(client_ip):
    """Check if client has exceeded rate limit. Returns True if allowed, False if limited."""
    current_time = time.time()
    # Clean old entries
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip]
        if current_time - t < _RATE_LIMIT_WINDOW
    ]
    # Check limit
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        return False
    # Record this request
    _rate_limit_store[client_ip].append(current_time)
    return True

def get_client_ip():
    """Get client IP address, considering proxy headers."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Security: Require ADMIN_STATS_TOKEN to be set in production
        admin_token = os.environ.get('ADMIN_STATS_TOKEN')
        if not admin_token:
            app.logger.error("ADMIN_STATS_TOKEN not set. Admin stats endpoint disabled.")
            abort(403)
        if request.args.get('token') != admin_token:
            app.logger.warning(f"Unauthorized admin stats access attempt from {get_client_ip()}")
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin/stats")
@admin_required
def admin_stats():
    # 1. Daily Sequence Creation (Last 14 Days)
    fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=14)
    daily_creation = db.session.query(
        func.date(Sequence.created_at).label('date'),
        func.count(Sequence.id)
    ).filter(Sequence.created_at >= fourteen_days_ago)\
    .group_by(func.date(Sequence.created_at))\
    .order_by(func.date(Sequence.created_at).desc()).all()

    # 2. Completion Funnel (Last 30 Days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    start_count = CounterLog.query.filter(
        CounterLog.event_type == 'sequence_start',
        CounterLog.timestamp >= thirty_days_ago
    ).count()
    end_count = CounterLog.query.filter(
        CounterLog.event_type == 'sequence_end',
        CounterLog.timestamp >= thirty_days_ago
    ).count()

    # 3. Hourly Activity (Peak Times) - Fixed: use column expression instead of string
    hourly_dist = db.session.query(
        extract('hour', CounterLog.timestamp).label('hour'),
        func.count(CounterLog.id)
    ).group_by(extract('hour', CounterLog.timestamp)).order_by(func.count(CounterLog.id).desc()).limit(5).all()

    # 4. Sound Popularity
    sound_popularity = db.session.query(
        Timer.alarm_sound,
        func.count(Timer.id)
    ).group_by(Timer.alarm_sound).order_by(func.count(Timer.id).desc()).limit(10).all()

    # 5. Most Engaged Sequences (Top 10)
    top_sequences = db.session.query(
        Sequence.id,
        Sequence.name,
        func.count(CounterLog.id).label('start_count')
    ).join(CounterLog, Sequence.id == CounterLog.sequence_id)\
    .filter(CounterLog.event_type == 'sequence_start')\
    .group_by(Sequence.id).order_by(func.count(CounterLog.id).desc()).limit(10).all()

    # Summary Stats
    total_sequences = Sequence.query.count()
    total_starts = CounterLog.query.filter_by(event_type='sequence_start').count()
    total_timers = Timer.query.count()
    avg_timers = total_timers / total_sequences if total_sequences > 0 else 0

    return render_template("admin_stats.html",
                           daily_creation=daily_creation,
                           start_count=start_count,
                           end_count=end_count,
                           hourly_dist=hourly_dist,
                           sound_popularity=sound_popularity,
                           top_sequences=top_sequences,
                           total_sequences=total_sequences,
                           total_starts=total_starts,
                           avg_timers=avg_timers)


# --- Sharing API Endpoints ---
@app.route("/api/share/<sequence_id>", methods=["POST"])
def manage_share(sequence_id):
    """Manage sharing settings for a timer"""
    from flask_login import current_user
    
    sequence = db.session.get(Sequence, sequence_id) or abort(404)
    
    # Check ownership
    if sequence.owner_id and (not current_user.is_authenticated or current_user.id != sequence.owner_id):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    share = SequenceShare.query.filter_by(sequence_id=sequence_id).first()
    
    if not share:
        share = SequenceShare(
            sequence_id=sequence_id,
            share_token=secrets.token_urlsafe(16),
            is_public=data.get('is_public', True),
            allow_copy=data.get('allow_copy', True)
        )
        db.session.add(share)
    else:
        if 'is_public' in data:
            share.is_public = data['is_public']
        if 'allow_copy' in data:
            share.allow_copy = data['allow_copy']
    
    db.session.commit()
    
    share_url = url_for('show_timer', sequence_id=sequence_id, _external=True)
    
    return jsonify({
        'share_token': share.share_token,
        'share_url': share_url,
        'is_public': share.is_public,
        'allow_copy': share.allow_copy,
        'view_count': share.view_count,
        'copy_count': share.copy_count
    })


@app.route("/api/share/<sequence_id>/copy", methods=["POST"])
def copy_shared_timer(sequence_id):
    """Copy a shared timer to user's account"""
    from flask_login import current_user, login_required
    
    if not current_user.is_authenticated:
        return jsonify({'error': 'Login required'}), 401
    
    sequence = Sequence.query.options(joinedload(Sequence.timers)).get_or_404(sequence_id)
    
    # Check if copying is allowed
    share = SequenceShare.query.filter_by(sequence_id=sequence_id).first()
    if share and not share.allow_copy:
        return jsonify({'error': 'Copying not allowed for this timer'}), 403
    
    # Create a copy
    new_sequence_id = secrets.token_urlsafe(8)
    new_sequence = Sequence(
        id=new_sequence_id,
        name=f"{sequence.name} (Copy)" if sequence.name else f"Timer Copy",
        owner_id=current_user.id,
        is_public=False,
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(new_sequence)
    
    # Copy all segments
    for timer in sequence.timers:
        new_timer = Timer(
            sequence_id=new_sequence_id,
            timer_name=timer.timer_name,
            duration=timer.duration,
            timer_order=timer.timer_order,
            color=timer.color,
            alarm_sound=timer.alarm_sound
        )
        db.session.add(new_timer)
    
    # Update copy count
    if share:
        share.copy_count += 1
    
    db.session.commit()
    
    # Log activity
    log = CounterLog(sequence_id=new_sequence_id, event_type='timer_copied', owner_id=current_user.id)
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        'message': 'Timer copied successfully',
        'new_sequence_id': new_sequence_id,
        'redirect_url': url_for('show_timer', sequence_id=new_sequence_id)
    })

@app.route("/manifest/<sequence_id>.json")
def get_manifest(sequence_id):
    sequence = db.session.get(Sequence, sequence_id) or abort(404)
    name = sequence.name if sequence.name else f"Timer {sequence_id}"
    
    manifest = {
        "name": name,
        "short_name": name[:12],
        "start_url": url_for('show_timer', sequence_id=sequence_id),
        "display": "standalone",
        "background_color": "#00ffae",
        "theme_color": "#00ffae",
        "icons": [
            {
                "src": "/static/android-chrome-192x192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/android-chrome-512x512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ],
        "description": f"Custom Timer: {name}",
        "version": "1.0.0"
    }
    return jsonify(manifest)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/privacy")
def privacy():
    """Privacy policy page"""
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    """Terms of service page"""
    return render_template("terms.html")


# --- Error Handlers ---
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with a user-friendly redirect."""
    if request.is_json or request.path.startswith('/api'):
        return jsonify({'error': 'Resource not found', 'message': str(error)}), 404
    return redirect(url_for('index', error='The requested page was not found.'))

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with database rollback."""
    db.session.rollback()
    if request.is_json or request.path.startswith('/api'):
        return jsonify({'error': 'Internal server error', 'message': str(error)}), 500
    return redirect(url_for('index', error='An internal error occurred. Please try again.'))

@app.errorhandler(400)
def bad_request_error(error):
    """Handle 400 errors."""
    if request.is_json or request.path.startswith('/api'):
        return jsonify({'error': 'Bad request', 'message': str(error)}), 400
    return redirect(url_for('index', error='Bad request.'))

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors."""
    if request.is_json or request.path.startswith('/api'):
        return jsonify({'error': 'Forbidden', 'message': str(error)}), 403
    return render_template("index.html", error="Access denied."), 403


if __name__ == "__main__":
    # Production logging configuration
    # For development, set LOG_LEVEL environment variable if needed
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    app.logger.info(f"Starting TimerFreak in development mode (LOG_LEVEL={log_level})")
    app.run(debug=(os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'), host='127.0.0.1', port=5001)
