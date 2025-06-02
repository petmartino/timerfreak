from flask import Flask, render_template, request, redirect, url_for, jsonify
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

# Store alarm sounds in app.config for robust access
app.config['ALARM_SOUNDS'] = [
    "alarm.mp3", 
    "beep.mp3", 
    "bell.mp3", 
    "ding.mp3", 
    "chime.mp3"
]

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
    color = db.Column(String(7), default="#4caf50")
    alarm_sound = db.Column(String(100), default="alarm.mp3")

    def __repr__(self):
        return f'<Timer {self.id}>'

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
                           alarm_sounds=app.config['ALARM_SOUNDS'],
                           most_used_sequences=most_used_sequences)

@app.route("/timer", methods=["POST"])
def start_timer():
    sequence_name = request.form.get("sequence_name")
    timer_names = request.form.getlist("timer_name[]")
    hours = request.form.getlist("hours[]")
    minutes = request.form.getlist("minutes[]")
    seconds = request.form.getlist("seconds[]")
    colors = request.form.getlist("color[]")
    alarm_sounds = request.form.getlist("alarm_sound[]")

    timers_data = [] # Store dicts for easier processing
    
    if not (len(hours) == len(minutes) == len(seconds) == len(colors) == len(alarm_sounds)):
        print("Error: Inconsistent list lengths for timer parameters.")
        # Redirect back to index with an error message
        return redirect(url_for('index', error="Inconsistent timer data provided."))

    for i in range(len(hours)):
        try:
            h = int(hours[i] or 0)
            m = int(minutes[i] or 0)
            s = int(seconds[i] or 0)
            total_seconds = h * 3600 + m * 60 + s
            
            # Frontend validation should catch this, but double-check for robustness
            if total_seconds <= 0: 
                print(f"Warning: Timer {i+1} has non-positive duration ({total_seconds}s). Skipping this timer.")
                continue # Skip this timer if duration is 0 or negative

            timers_data.append({
                'name': timer_names[i] if i < len(timer_names) else None,
                'duration': total_seconds,
                'color': colors[i] if i < len(colors) else "#4caf50",
                'alarm_sound': alarm_sounds[i] if i < len(alarm_sounds) else "alarm.mp3"
            })
        except ValueError as e:
            print(f"Error parsing timer duration for timer {i+1}: {e}")
            return redirect(url_for('index', error="Invalid timer duration provided."))
    
    if not timers_data:
        # If no valid timers were created after filtering
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

    print(f"Created sequence {sequence_id} with {len(timers_data)} timers.")
    return redirect(url_for('show_timer', sequence_id=sequence_id))

@app.route("/timer/<sequence_id>")
def show_timer(sequence_id):
    sequence = Sequence.query.get_or_404(sequence_id)
    
    # Retrieve timers ensuring they are ordered correctly
    # The relationship `timers` on Sequence is already ordered by `timer_order`
    timers_in_order = sorted(sequence.timers, key=lambda t: t.timer_order) 

    timers_durations = [timer.duration for timer in timers_in_order]
    timer_names = [timer.timer_name if timer.timer_name else f"Timer {timer.timer_order + 1}" for timer in timers_in_order]
    timer_colors = [timer.color for timer in timers_in_order]
    timer_alarm_sounds = [timer.alarm_sound for timer in timers_in_order]

    # Pass sequence name to logs template as well
    sequence_name_for_logs = sequence.name if sequence.name else f"Sequence {sequence_id}"

    return render_template("timer.html", 
                           timers=timers_durations, 
                           timer_names=timer_names, 
                           sequence_name=sequence.name, 
                           sequence_id=sequence_id, 
                           timer_colors=timer_colors, 
                           alarm_sounds=app.config['ALARM_SOUNDS'], # All available sounds
                           timer_alarm_sounds=timer_alarm_sounds, # Specific sounds for each timer
                           sequence_name_for_logs=sequence_name_for_logs)

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
        # If the ID doesn't exist, you might want to render a custom 404 page,
        # or redirect to the index with a message.
        return "Sequence not found", 404


@app.route("/log_activity", methods=["POST"])
def log_activity():
    data = request.get_json()
    sequence_id = data.get('sequence_id')
    timer_order = data.get('timer_order') # This is the 0-based order from JS
    event_type = data.get('event_type')

    # Basic logging of received data
    app.logger.debug(f"Received log activity: sequence_id={sequence_id}, timer_order={timer_order}, event_type={event_type}")

    if not sequence_id or not event_type:
        app.logger.error(f"Missing data for log activity. Received: {data}")
        return jsonify({'message': 'Missing data (sequence_id or event_type)'}), 400

    try:
        # Ensure timer_order is either an int or None
        # It comes from JS as a number, but JSON.stringify converts it to a JSON number.
        # Python's data.get() will return a Python int or float for JSON numbers, or None if not present.
        # If it's a float (e.g., from 0.0), convert it to int.
        # If it's literally not an integer when it should be (e.g., a string "0"), we should catch that.
        
        # Defensive conversion for timer_order
        if timer_order is not None:
            try:
                # Attempt to convert to int, handling potential floats or string numbers
                timer_order_int = int(timer_order) 
            except (ValueError, TypeError):
                app.logger.error(f"Invalid timer_order format: {timer_order} (type: {type(timer_order)})")
                return jsonify({'message': 'Invalid timer_order format'}), 400
        else:
            timer_order_int = None # If timer_order is explicitly None or missing from JSON

        log = CounterLog(sequence_id=sequence_id, timer_order=timer_order_int, event_type=event_type)
        db.session.add(log)
        db.session.commit()
        app.logger.info(f"Activity logged successfully: Seq={sequence_id}, TimerOrder={timer_order_int}, Event={event_type}")
        return jsonify({'message': 'Activity logged successfully'}), 201
    except Exception as e:
        db.session.rollback()
        # Log the full exception for debugging
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

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG) # Set logging level to DEBUG for full output
    app.run(debug=True, host='127.0.0.1', port=5001)
