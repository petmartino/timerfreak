from flask import Flask, render_template, request, redirect, url_for, jsonify, g
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import secrets
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Integer, String, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from flask_migrate import Migrate
from datetime import datetime, timedelta

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
# You can change these values to set default behaviors.
DEFAULT_TIMER_COLOR = "#4caf50" # Default color for new timers (a green shade)
DEFAULT_ALARM_SOUND_FILENAME = "alarm.mp3" # Default sound for new timers
# You can add more defaults here, e.g., DEFAULT_BAR_HEIGHT = "100px"

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Define the models
class Sequence(db.Model):
    id = db.Column(String(20), primary_key=True)
    name = db.Column(String(100))
    created_at = db.Column(DateTime(timezone=False), server_default=func.now())
    # Order by timer_order to ensure consistency
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
    alarm_sound = db.Column(String(100), default=DEFAULT_ALARM_SOUND_FILENAME) # Stores filename string

    def __repr__(self):
        return f'<Timer {self.id}>'

class Sound(db.Model):
    id = db.Column(Integer, primary_key=True)
    filename = db.Column(String(100), nullable=False, unique=True)
    name = db.Column(String(100), nullable=False)

    def __repr__(self):
        return f'<Sound {self.name} ({self.filename})>'

class CounterLog(db.Model):
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False)
    # timer_order is the 0-based index from the frontend, used for clearer logging context
    timer_order = db.Column(Integer, nullable=True) # Renamed from timer_id to timer_order for clarity
    event_type = db.Column(String(50), nullable=False) # Increased length for more descriptive events
    timestamp = db.Column(DateTime(timezone=False), server_default=func.now())

    # Add a relationship to Sequence for easier access to sequence name in logs
    sequence_rel = relationship('Sequence', backref='logs')

    def __repr__(self):
        return f'<CounterLog {self.id} - {self.event_type} - Seq: {self.sequence_id} - Timer: {self.timer_order}>'

# Create the database tables
with app.app_context():
    db.create_all()

# Context processor to make current_year available in all templates
@app.context_processor
def inject_global_data():
    return dict(current_year=datetime.now().year)

@app.route("/")
def index():
    # Fetch available sounds from the database to populate dropdown
    available_sounds = Sound.query.order_by(Sound.name).all()
    if not available_sounds:
        # Fallback if no sounds are in DB, or provide an initial set
        app.logger.warning("No sounds found in database. Populating with defaults.")
        initial_sounds = [
            {'filename': 'alarm.mp3', 'name': 'Alarm'},
            {'filename': 'beep.mp3', 'name': 'Beep'},
            {'filename': 'bell.mp3', 'name': 'Bell'},
            {'filename': 'chime.mp3', 'name': 'Chime'},
            {'filename': 'ding.mp3', 'name': 'Ding'},
        ]
        for s_data in initial_sounds:
            if not Sound.query.filter_by(filename=s_data['filename']).first():
                db.session.add(Sound(filename=s_data['filename'], name=s_data['name']))
        db.session.commit()
        available_sounds = Sound.query.order_by(Sound.name).all()


    # Fetch most used sequences from the database
    # "Most used" sequences are those with the highest count of 'sequence_start' log entries.

    # Subquery to get sequence start counts
    sequence_start_counts = db.session.query(
        CounterLog.sequence_id,
        func.count(CounterLog.id).label('start_count')
    ).filter(CounterLog.event_type == 'sequence_start')\
    .group_by(CounterLog.sequence_id).subquery()

    # Query to get timer count and total duration per sequence
    sequence_timer_info = db.session.query(
        Timer.sequence_id,
        func.count(Timer.id).label('timer_count'),
        func.sum(Timer.duration).label('total_sequence_duration')
    ).group_by(Timer.sequence_id).subquery()

    # Main query: Join Sequence with the subqueries
    most_used_sequences_query = db.session.query(
        Sequence.id,
        Sequence.name,
        sequence_start_counts.c.start_count, # Count of starts for this sequence
        sequence_timer_info.c.timer_count,   # Count of timers in this sequence
        sequence_timer_info.c.total_sequence_duration # Sum of durations in this sequence
    ).join(sequence_start_counts, Sequence.id == sequence_start_counts.c.sequence_id)\
    .outerjoin(sequence_timer_info, Sequence.id == sequence_timer_info.c.sequence_id)\
    .order_by(sequence_start_counts.c.start_count.desc())\
    .limit(35) # Get top 35 most used sequences

    most_used_sequences_raw = most_used_sequences_query.all()

    most_used_sequences = []
    for seq in most_used_sequences_raw:
        total_seconds = seq.total_sequence_duration if seq.total_sequence_duration is not None else 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        duration_parts = []
        if hours > 0:
            duration_parts.append(f"{hours}h")
        if minutes > 0:
            duration_parts.append(f"{minutes}m")
        if seconds > 0 or (total_seconds == 0 and not duration_parts): # Show 0s if total is 0
            duration_parts.append(f"{seconds}s")

        duration_display = " ".join(duration_parts) if duration_parts else "0s"


        most_used_sequences.append({
            'id': seq.id,
            'name': seq.name if seq.name else f'Unnamed Sequence',
            'use_count': seq.start_count,
            'timer_count': seq.timer_count if seq.timer_count is not None else 0,
            'total_duration_display': duration_display.strip()
        })

    return render_template("index.html",
                           available_sounds=available_sounds,
                           most_used_sequences=most_used_sequences)

@app.route("/timer", methods=["POST"])
def start_timer():
    # Honeypot check: If the 'website' field is filled, it's likely a bot.
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

    timers_data = [] # Store dicts for easier processing

    # Basic length validation (form should prevent this, but for robustness)
    num_timers = len(hours)
    if not (num_timers == len(minutes) == len(seconds) == len(colors) == len(alarm_sounds)):
        app.logger.error("Error: Inconsistent list lengths for timer parameters.")
        return redirect(url_for('index', error="Inconsistent timer data provided."))

    for i in range(num_timers):
        try:
            h = int(hours[i] or 0)
            m = int(minutes[i] or 0)
            s = int(seconds[i] or 0)
            total_seconds = h * 3600 + m * 60 + s

            # Frontend validation should catch this, but double-check for robustness
            if total_seconds <= 0:
                app.logger.warning(f"Timer {i+1} has non-positive duration ({total_seconds}s). Skipping this timer.")
                continue # Skip this timer if duration is 0 or negative

            timers_data.append({
                'name': timer_names[i] if i < len(timer_names) else None,
                'duration': total_seconds,
                'color': colors[i] if i < len(colors) else DEFAULT_TIMER_COLOR,
                'alarm_sound': alarm_sounds[i] if i < len(alarm_sounds) else DEFAULT_ALARM_SOUND_FILENAME
            })
        except ValueError as e:
            app.logger.error(f"Error parsing timer duration for timer {i+1}: {e}")
            return redirect(url_for('index', error="Invalid timer duration provided."))

    if not timers_data:
        # If no valid timers were created after filtering
        app.logger.warning("No valid timers submitted after parsing. All timers had zero or negative duration.")
        return redirect(url_for('index', error="No valid timers submitted. Please ensure at least one timer has a duration greater than 0."))

    # Generate a unique sequence ID
    sequence_id = secrets.token_urlsafe(8)

    # Save the sequence to the database
    sequence = Sequence(id=sequence_id, name=sequence_name)
    db.session.add(sequence)

    for i, data in enumerate(timers_data):
        timer = Timer(
            sequence_id=sequence_id,
            timer_name=data['name'],
            duration=data['duration'],
            timer_order=i, # Use the explicit order
            color=data['color'],
            alarm_sound=data['alarm_sound']
        )
        db.session.add(timer)
    db.session.commit()

    # Log the sequence start
    log = CounterLog(sequence_id=sequence_id, event_type='sequence_start')
    db.session.add(log)
    db.session.commit()

    app.logger.info(f"Created sequence {sequence_id} with {len(timers_data)} timers.")
    return redirect(url_for('show_timer', sequence_id=sequence_id))

@app.route("/timer/<sequence_id>")
def show_timer(sequence_id):
    sequence = Sequence.query.get_or_404(sequence_id)

    # Retrieve timers ensuring they are ordered correctly
    # The relationship `timers` on Sequence is already ordered by `timer_order`
    timers_in_order = sequence.timers # This is already sorted by timer_order due to relationship config

    timers_durations = [timer.duration for timer in timers_in_order]
    timer_names = [timer.timer_name if timer.timer_name else f"Timer {timer.timer_order + 1}" for timer in timers_in_order]
    timer_colors = [timer.color for timer in timers_in_order]
    timer_alarm_sounds = [timer.alarm_sound for timer in timers_in_order]

    # All available sounds from the database (for debugging or future use)
    all_available_sounds_db = Sound.query.order_by(Sound.name).all()
    all_available_sound_filenames = [s.filename for s in all_available_sounds_db] # Only pass filenames

    sequence_name_for_logs = sequence.name if sequence.name else f"Sequence {sequence_id}"

    return render_template("timer.html",
                           timers=timers_durations,
                           timer_names=timer_names,
                           sequence_name=sequence.name,
                           sequence_id=sequence_id,
                           timer_colors=timer_colors,
                           alarm_sounds=all_available_sound_filenames, # All filenames
                           timer_alarm_sounds=timer_alarm_sounds, # Specific sounds for each timer
                           sequence_name_for_logs=sequence_name_for_logs,
                           base_url=request.host_url.rstrip('/')) # Correctly get base URL

# --- NEW REDIRECT ROUTE ---
@app.route("/<string:sequence_id>")
def redirect_to_timer(sequence_id):
    """
    Redirects /<sequence_id> to /timer/<sequence_id>.
    """
    sequence = Sequence.query.get(sequence_id)
    if sequence:
        return redirect(url_for('show_timer', sequence_id=sequence_id))
    else:
        # If the ID doesn't exist, redirect to the index with a message.
        return redirect(url_for('index', error=f"Sequence '{sequence_id}' not found."))


@app.route("/log_activity", methods=["POST"])
def log_activity():
    data = request.get_json()
    sequence_id = data.get('sequence_id')
    timer_order = data.get('timer_order') # This is the 0-based order from JS
    event_type = data.get('event_type')

    app.logger.debug(f"Received log activity: sequence_id={sequence_id}, timer_order={timer_order}, event_type={event_type}")

    if not sequence_id or not event_type:
        app.logger.error(f"Missing data for log activity. Received: {data}")
        return jsonify({'message': 'Missing data (sequence_id or event_type)'}), 400

    try:
        # Defensive conversion for timer_order
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

    # Eagerly load timers for efficient access to their names in the template.
    # Join CounterLog with Timer on sequence_id AND timer_order to get the specific timer's name.
    logs_raw = db.session.query(CounterLog, Timer)\
                     .outerjoin(Timer, (CounterLog.sequence_id == Timer.sequence_id) & (CounterLog.timer_order == Timer.timer_order))\
                     .filter(CounterLog.sequence_id == sequence_id)\
                     .order_by(CounterLog.timestamp).all()

    logs_formatted = []
    for log_entry, timer_info in logs_raw:
        log_dict = {
            'id': log_entry.id,
            'sequence_id': log_entry.sequence_id,
            'timer_order': log_entry.timer_order,
            'event_type': log_entry.event_type,
            'timestamp': log_entry.timestamp,
            'timer_name': timer_info.timer_name if timer_info else None # Get timer name if available
        }
        logs_formatted.append(log_dict)

    sequence_name_display = sequence.name if sequence.name else f"Sequence {sequence_id}"
    return render_template("logs.html", logs=logs_formatted, sequence_id=sequence_id, sequence_name_for_logs=sequence_name_display)

@app.route("/about")
def about():
    return render_template("about.html")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG) # Set logging level to DEBUG for full output
    app.run(debug=True, host='127.0.0.1', port=5001)