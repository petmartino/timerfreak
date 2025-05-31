from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import secrets
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Integer, String, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from flask_migrate import Migrate

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

# Store alarm sounds in app.config for robust access
app.config['ALARM_SOUNDS'] = ["alarm.mp3", "beep.mp3", "bell.mp3"] # Add more sounds here

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Define the models
class Sequence(db.Model):
    id = db.Column(String(20), primary_key=True)
    name = db.Column(String(100))
    created_at = db.Column(DateTime(timezone=False), server_default=func.now())
    timers = relationship('Timer', backref='sequence', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Sequence {self.id}>'

class Timer(db.Model):
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False)
    timer_name = db.Column(String(100))
    duration = db.Column(Integer, nullable=False)
    timer_order = db.Column(Integer, nullable=False)
    color = db.Column(String(7), default="#4caf50")  # New field for color
    alarm_sound = db.Column(String(100), default="alarm.mp3") # New field for alarm sound

    def __repr__(self):
        return f'<Timer {self.id}>'

class CounterLog(db.Model):
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False)
    timer_id = db.Column(Integer, ForeignKey('timer.id'), nullable=True)  # Can be null if sequence-level
    event_type = db.Column(String(20), nullable=False)
    timestamp = db.Column(DateTime(timezone=False), server_default=func.now())

    def __repr__(self):
        return f'<CounterLog {self.id} - {self.event_type}>'

# Create the database tables
with app.app_context():
    db.create_all()

@app.route("/")
def index():
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
        # Format total duration (seconds) into human-readable H:M:S
        total_seconds = seq.total_sequence_duration if seq.total_sequence_duration is not None else 0
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        duration_display = ""
        if hours > 0:
            duration_display += f"{hours}h "
        if minutes > 0 or (hours > 0 and seconds > 0) or (hours == 0 and minutes == 0 and seconds == 0 and total_seconds == 0): # Handle zero duration sequences
            duration_display += f"{minutes:02}m "
        duration_display += f"{seconds:02}s" if total_seconds > 0 or (hours == 0 and minutes == 0) else ""

        if not duration_display: # Edge case for purely 0 duration timers
            duration_display = "0s"


        most_used_sequences.append({
            'id': seq.id,
            'name': seq.name if seq.name else f'Unnamed Sequence',
            'use_count': seq.start_count,
            'timer_count': seq.timer_count if seq.timer_count is not None else 0, # Handle sequences with no timers
            'total_duration_display': duration_display.strip() # Remove trailing space if any
        })

    return render_template("index.html", 
                           alarm_sounds=app.config['ALARM_SOUNDS'],
                           most_used_sequences=most_used_sequences)

@app.route("/timer", methods=["POST"])
def start_timer():
    sequence_name = request.form.get("sequence_name")
    timer_names = request.form.getlist("timer_name[]")
    hours = request.form.getlist("hours[]")
    minutes = request.form.getlist("minutes[]")
    seconds = request.form.getlist("seconds[]")
    colors = request.form.getlist("color[]")  # Get colors from the form
    alarm_sounds = request.form.getlist("alarm_sound[]") # Get alarm sounds from the form

    timers = []
    if len(hours) == len(minutes) == len(seconds):
        for h, m, s in zip(hours, minutes, seconds):
            try:
                total_seconds = int(h or 0) * 3600 + int(m or 0) * 60 + int(s or 0)
                timers.append(total_seconds)
            except ValueError:
                # Handle invalid input (e.g., non-numeric values)
                timers = []
                break  # Stop processing if there's an error
    else:
        # Handle inconsistent list lengths (e.g., log an error or display a message)
        print("Error: Inconsistent list lengths for hours, minutes, and seconds.")
        timers = []  # Return an empty list of timers
    
    # Generate a unique sequence ID
    sequence_id = secrets.token_urlsafe(8)

    # Save the sequence to the database
    sequence = Sequence(id=sequence_id, name=sequence_name)
    db.session.add(sequence)
    for i, duration in enumerate(timers):
        timer_name = timer_names[i] if i < len(timer_names) else None
        color = colors[i] if i < len(colors) else "#4caf50"  # Get color or use default
        alarm_sound = alarm_sounds[i] if i < len(alarm_sounds) else "alarm.mp3" # Get alarm sound or use default
        timer = Timer(sequence_id=sequence_id, timer_name=timer_name, duration=duration, timer_order=i, color=color, alarm_sound=alarm_sound)
        db.session.add(timer)
    db.session.commit()

    # Log the sequence start
    log = CounterLog(sequence_id=sequence_id, event_type='sequence_start')
    db.session.add(log)
    db.session.commit()

    print("Timers:", timers)  # Add this line for debugging
    return redirect(url_for('show_timer', sequence_id=sequence_id))

@app.route("/timer/<sequence_id>")
def show_timer(sequence_id):
    sequence = Sequence.query.get_or_404(sequence_id)
    timers = [timer.duration for timer in sequence.timers]
    timer_names = [timer.timer_name for timer in sequence.timers]
    timer_colors = [timer.color for timer in sequence.timers]  # Get timer colors
    timer_alarm_sounds = [timer.alarm_sound for timer in sequence.timers] # Get timer alarm sounds
    return render_template("timer.html", timers=timers, timer_names=timer_names, sequence_name=sequence.name, sequence_id=sequence_id, timer_colors=timer_colors, alarm_sounds=app.config['ALARM_SOUNDS'], timer_alarm_sounds=timer_alarm_sounds)

# --- NEW REDIRECT ROUTE ---
@app.route("/<string:sequence_id>")
def redirect_to_timer(sequence_id):
    """
    Redirects /<sequence_id> to /timer/<sequence_id>.
    """
    # Check if a sequence with this ID exists before redirecting, to avoid Flask's 404
    # The show_timer route will handle the 404 if the sequence ID is truly invalid after redirect.
    sequence = Sequence.query.get(sequence_id)
    if sequence:
        return redirect(url_for('show_timer', sequence_id=sequence_id))
    else:
        # If the ID doesn't exist, you might want to render a custom 404 page,
        # or redirect to the index with a message, instead of relying on Flask's default 404
        # after a successful redirect to a non-existent timer route.
        # For simplicity, returning a direct 404 here for invalid IDs captured by this shorter route.
        return "Sequence not found", 404


@app.route("/log_activity", methods=["POST"])
def log_activity():
    data = request.get_json()
    sequence_id = data.get('sequence_id')
    timer_id = data.get('timer_id')
    event_type = data.get('event_type')

    if not sequence_id or not event_type:
        return jsonify({'message': 'Missing data'}), 400

    try:
        # Find the Timer object if timer_id is provided
        timer = None
        if timer_id:
            sequence = Sequence.query.get(sequence_id)
            if sequence:
                # Find the timer by its order within the sequence
                # Note: timer_id from JS is 1-based, timer_order in DB is 0-based
                timer = next((t for t in sequence.timers if t.timer_order == timer_id - 1), None)

        # Create the log entry
        # Ensure timer.id is accessed only if timer is not None
        log = CounterLog(sequence_id=sequence_id, timer_id=timer.id if timer else None, event_type=event_type)
        db.session.add(log)
        db.session.commit()
        return jsonify({'message': 'Activity logged successfully'}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error logging activity: {e}")
        return jsonify({'message': 'Failed to log activity'}), 500

@app.route("/logs/<sequence_id>")
def show_logs(sequence_id):
    logs = CounterLog.query.filter_by(sequence_id=sequence_id).all()
    return render_template("logs.html", logs=logs, sequence_id=sequence_id)

if __name__ == "__main__":
    app.run(debug=True, host='127.0.0.1', port=5001)