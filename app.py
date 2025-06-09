"""
TimerFreak Flask Application
Copyright (c) 2025 - Pet Martino

This software is licensed under the MIT License.
See the LICENSE file for more details.

"""
from pytz import timezone as pytz_timezone
from flask import Flask, render_template, request, redirect, url_for, jsonify, g
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import secrets
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Integer, String, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from flask_migrate import Migrate
from datetime import datetime, timedelta, timezone
from __version__ import __version__ as APP_VERSION 


## app.py

from datetime import datetime, timedelta, timezone # Ensure timezone is imported
from pytz import timezone as pytz_timezone # Ensure this is imported for display
from sqlalchemy.types import TypeDecorator, DateTime # NEW IMPORT
from dateutil import parser # Add this import if not already there, for robust parsing in process_result_value

class UTCDateTime(TypeDecorator):
    """
    A DateTime type that handles timezone conversion for SQLite.
    Stores naive UTC datetime objects in the database,
    and returns timezone-aware UTC datetime objects in Python.
    """
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """
        Processes the Python datetime object before sending it to the database.
        Converts aware datetimes to naive UTC datetimes.
        """
        print(f"DEBUG: process_bind_param - input value: {value}, type: {type(value)}")
        if value is None:
            return value # If value is None (e.g., if column is nullable and not set), return None.

        if value.tzinfo is None:
            # If the datetime object is naive, we assume it's already in UTC.
            # We return it directly, and the underlying DateTime impl will format it.
            naive_utc_dt = value
            print(f"DEBUG: process_bind_param - input naive (assumed UTC): {naive_utc_dt}")
        else:
            # If the datetime object is timezone-aware, convert it to UTC and remove tzinfo.
            # This creates a naive datetime that represents UTC.
            naive_utc_dt = value.astimezone(timezone.utc).replace(tzinfo=None)
            print(f"DEBUG: process_bind_param - converted to naive UTC: {naive_utc_dt}")
        
        # This is the CRUCIAL CHANGE: Return the datetime object, not a string.
        # The `self.impl` (SQLAlchemy's built-in DateTime type) will handle the final string conversion for SQLite.
        return naive_utc_dt

    def process_result_value(self, value, dialect):
        """
        Processes the string value retrieved from the database.
        Converts it into a timezone-aware UTC datetime object.
        """
        print(f"DEBUG: process_result_value - raw value from DB: {value}, type: {type(value)}")
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
                        print(f"DEBUG: process_result_value - parsed with dateutil.parser: {dt}")
                    except Exception as e:
                        print(f"ERROR: process_result_value - failed to parse string '{value}': {e}")
                        # If parsing fails, return original value to avoid crashing, though it's not ideal.
                        return value
        elif isinstance(value, datetime):
            # If the value is already a datetime object (unlikely for SQLite strings)
            dt = value
            print(f"DEBUG: process_result_value - value is already datetime object: {dt}")
        else:
            # Handle any other unexpected types (e.g., int, float, etc.) by attempting to parse its string rep
            try:
                dt = parser.parse(str(value))
                print(f"DEBUG: process_result_value - parsed from non-string/datetime: {dt}")
            except Exception as e:
                print(f"ERROR: process_result_value - failed to parse non-string/datetime value '{value}': {e}")
                return value # Return original value if parsing truly fails

        # Attach UTC timezone info to the parsed naive datetime object
        if dt and dt.tzinfo is None:
            aware_dt = dt.replace(tzinfo=timezone.utc)
            print(f"DEBUG: process_result_value - successfully attached UTC: {aware_dt}")
            return aware_dt
        elif dt: # If it's already timezone-aware (shouldn't happen for SQLite typically)
            print(f"DEBUG: process_result_value - dt is already timezone-aware: {dt}")
            return dt
        
        # Fallback if parsing results in None or a non-datetime object unexpectedly
        print(f"DEBUG: process_result_value - returned original value as final fallback: {value}")
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
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or 'your_default_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timerfreak.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Suppress a warning

# --- Application Defaults & Configuration ---
DEFAULT_TIMER_COLOR = "#0cd413" # Default color for new timers (a green shade)
# DEFAULT_ALARM_SOUND_FILENAME is now determined from DB.
# Keep a fallback in case no sound is marked as default in the DB.
FALLBACK_ALARM_SOUND_FILENAME = "alarm.mp3" 

db = SQLAlchemy(app)
migrate = Migrate(app, db)

class Sequence(db.Model):
    id = db.Column(String(20), primary_key=True)
    name = db.Column(String(100))
    theme = db.Column(String(50), nullable=True)
    featured = db.Column(Integer, default=0, nullable=False)
    # Change 1: timezone=True tells SQLAlchemy to treat it as timezone-aware
    # Change 2: default=lambda: datetime.now(timezone.utc) makes Python generate UTC timestamp
    created_at = db.Column(UTCDateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    timers = relationship('Timer', backref='sequence', cascade="all, delete-orphan", order_by="Timer.timer_order")

    def __repr__(self):
        return f'<Sequence {self.id}>'

class Timer(db.Model):
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False)
    timer_name = db.Column(String(100))
    duration = db.Column(Integer, nullable=False)
    timer_order = db.Column(Integer, nullable=False) # 0-based index
    color = db.Column(String(7), default=DEFAULT_TIMER_COLOR)
    # alarm_sound will default to whatever the app determines is the default from DB
    alarm_sound = db.Column(String(100)) # Removed hardcoded default here, will be set on creation

    def __repr__(self):
        return f'<Timer {self.id}>'

class Sound(db.Model):
    id = db.Column(Integer, primary_key=True)
    filename = db.Column(String(100), nullable=False, unique=True)
    name = db.Column(String(100), nullable=False)
    # --- ADDED: New 'default' column ---
    default = db.Column(Integer, default=0, nullable=False) # 0 for not default, 1 for default

    # Method to convert Sound object to a dictionary for JSON serialization
    def to_dict(self):
        return {"filename": self.filename, "name": self.name, "default": self.default}

    def __repr__(self):
        return f'<Sound {self.name} ({self.filename})>'

class CounterLog(db.Model):
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False)
    timer_order = db.Column(Integer, nullable=True)
    event_type = db.Column(String(50), nullable=False)
    # Change 1: timezone=True
    # Change 2: default=lambda: datetime.now(timezone.utc)
    timestamp = db.Column(UTCDateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sequence_rel = relationship('Sequence', backref='logs')

    def __repr__(self):
        return f'<CounterLog {self.id} - {self.event_type} - Seq: {self.sequence_id} - Timer: {self.timer_order}>'
    
with app.app_context():
    db.create_all()




@app.context_processor
def inject_global_data():
    return dict(current_year=datetime.now().year, app_version=APP_VERSION)

@app.route("/")
def index():
    # Fetch available sounds from the database
    available_sounds_raw = Sound.query.order_by(Sound.name).all()
    available_sounds_for_template = [s.to_dict() for s in available_sounds_raw]

    # --- MODIFIED: Determine default sound filename from DB ---
    default_sound_obj = Sound.query.filter_by(default=1).first()
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
    ).outerjoin(sequence_start_counts, Sequence.id == sequence_start_counts.c.sequence_id)\
    .outerjoin(sequence_timer_info, Sequence.id == sequence_timer_info.c.sequence_id)\
    .order_by(sequence_start_counts.c.start_count.desc().nulls_last())\
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

    return render_template("index.html",
                           available_sounds=available_sounds_for_template,
                           most_used_sequences=most_used_sequences,
                           DEFAULT_TIMER_COLOR=DEFAULT_TIMER_COLOR,
                           # --- MODIFIED: Pass the determined default sound filename ---
                           DEFAULT_ALARM_SOUND_FILENAME=default_alarm_sound_filename)

@app.route("/timer", methods=["POST"])
def start_timer():
    if request.form.get('website'):
        app.logger.warning("Honeypot field filled. Bot detected, redirecting to index.")
        return redirect(url_for('index', error="Bot activity detected."))

    sequence_name = request.form.get("sequence_name")
    timer_names = request.form.getlist("timer_name[]")
    hours = request.form.getlist("hours[]")
    minutes = request.form.getlist("minutes[]")
    seconds = request.form.getlist("seconds[]")
    colors = request.form.getlist("color[]")
    alarm_sounds = request.form.getlist("alarm_sound[]")

    timers_data = []

    num_timers = len(hours)
    if not (num_timers == len(minutes) == len(seconds) == len(colors) == len(alarm_sounds)):
        app.logger.error("Error: Inconsistent list lengths for timer parameters.")
        return redirect(url_for('index', error="Inconsistent timer data provided."))

    # Get the default alarm sound from the database for new timer creation if needed
    default_sound_obj = Sound.query.filter_by(default=1).first()
    if default_sound_obj:
        default_alarm_sound_for_db_save = default_sound_obj.filename
    else:
        default_alarm_sound_for_db_save = FALLBACK_ALARM_SOUND_FILENAME


    for i in range(num_timers):
        try:
            h = int(hours[i] or 0)
            m = int(minutes[i] or 0)
            s = int(seconds[i] or 0)
            total_seconds = h * 3600 + m * 60 + s

            if total_seconds <= 0:
                app.logger.warning(f"Timer {i+1} has non-positive duration ({total_seconds}s). Skipping this timer.")
                continue

            timers_data.append({
                'name': timer_names[i] if i < len(timer_names) else None,
                'duration': total_seconds,
                'color': colors[i] if i < len(colors) else DEFAULT_TIMER_COLOR,
                # Use the submitted alarm sound, or the determined default if not provided
                'alarm_sound': alarm_sounds[i] if alarm_sounds[i] else default_alarm_sound_for_db_save
            })
        except ValueError as e:
            app.logger.error(f"Error parsing timer duration for timer {i+1}: {e}")
            return redirect(url_for('index', error="Invalid timer duration provided."))

    if not timers_data:
        app.logger.warning("No valid timers submitted after parsing. All timers had zero or negative duration.")
        return redirect(url_for('index', error="No valid timers submitted. Please ensure at least one timer has a duration greater than 0."))

    sequence_id = secrets.token_urlsafe(8)

    sequence = Sequence(id=sequence_id, name=sequence_name)
    db.session.add(sequence)

    for i, data in enumerate(timers_data):
        timer = Timer(
            sequence_id=sequence_id,
            timer_name=data['name'],
            duration=data['duration'],
            timer_order=i,
            color=data['color'],
            alarm_sound=data['alarm_sound'] # This now correctly uses the determined default or submitted value
        )
        db.session.add(timer)
    db.session.commit()

    log = CounterLog(sequence_id=sequence_id, event_type='sequence_start')
    db.session.add(log)
    db.session.commit()

    app.logger.info(f"Created sequence {sequence_id} with {len(timers_data)} timers.")
    return redirect(url_for('show_timer', sequence_id=sequence_id))

@app.route("/timer/<sequence_id>")
def show_timer(sequence_id):
    sequence = Sequence.query.get_or_404(sequence_id)

    timers_in_order = sequence.timers

    timers_durations = [timer.duration for timer in timers_in_order]
    timer_names = [timer.timer_name if timer.timer_name else f"Timer {timer.timer_order + 1}" for timer in timers_in_order]
    timer_colors = [timer.color for timer in timers_in_order]
    timer_alarm_sounds = [timer.alarm_sound for timer in timers_in_order]

    all_available_sounds_db = Sound.query.order_by(Sound.name).all()
    all_available_sound_filenames = [s.filename for s in all_available_sounds_db]

    sequence_name_for_logs = sequence.name if sequence.name else f"Sequence {sequence_id}"

    return render_template("timer.html",
                           timers=timers_durations,
                           timer_names=timer_names,
                           sequence_name=sequence.name,
                           sequence_id=sequence_id,
                           timer_colors=timer_colors,
                           alarm_sounds=all_available_sound_filenames,
                           timer_alarm_sounds=timer_alarm_sounds,
                           sequence_name_for_logs=sequence_name_for_logs,
                           base_url=request.host_url.rstrip('/'))

@app.route("/<string:sequence_id>")
def redirect_to_timer(sequence_id):
    sequence = Sequence.query.get(sequence_id)
    if sequence:
        return redirect(url_for('show_timer', sequence_id=sequence_id))
    else:
        return redirect(url_for('index', error=f"Sequence '{sequence_id}' not found."))

@app.route("/log_activity", methods=["POST"])
def log_activity():
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

        log = CounterLog(sequence_id=sequence_id, timer_order=timer_order_int, event_type=event_type)
        db.session.add(log)
        db.session.commit()
        app.logger.info(f"Activity logged successfully: Seq={sequence_id}, TimerOrder={timer_order_int}, Event={event_type}")
        return jsonify({'message': 'Activity logged successfully'}), 201
    except Exception as e:
        db.session.rollback()
        app.logger.exception(f"Database error logging activity: {data}")
        return jsonify({'message': 'Failed to log activity', 'error': str(e)}), 500

@app.route("/logs/<sequence_id>")
def show_logs(sequence_id):
    sequence = Sequence.query.get_or_404(sequence_id)

    logs_raw = db.session.query(CounterLog, Timer)\
                     .outerjoin(Timer, (CounterLog.sequence_id == Timer.sequence_id) & (CounterLog.timer_order == Timer.timer_order))\
                     .filter(CounterLog.sequence_id == sequence_id)\
                     .order_by(CounterLog.timestamp).all()

    logs_formatted = []
    # Define the target display timezone (e.g., America/Chicago for CDT/CST)
    # You can make this configurable if users need to choose their timezone.
    display_timezone = pytz_timezone('America/Chicago') # Use 'America/New_York' for EDT/EST etc.

    # In app.py, inside show_logs function:
    for log_entry, timer_info in logs_raw:
        utc_timestamp = log_entry.timestamp
        print(f"DEBUG: Retrieved timestamp (utc_timestamp): {utc_timestamp}")
        print(f"DEBUG: Type of utc_timestamp: {type(utc_timestamp)}")
        print(f"DEBUG: tzinfo of utc_timestamp: {utc_timestamp.tzinfo}")
        print(f"DEBUG: utcoffset of utc_timestamp: {utc_timestamp.utcoffset()}")


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
@app.route("/about")
def about():
    return render_template("about.html")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='127.0.0.1', port=5001)
