
# TimerFreak - Your Custom Sequence Timer
Try at [https://timerfreak.xyz](https://timerfreak.xyz)

![TimerFreak](https://timerfreak.xyz/static/logotimerfreak.svg "TimerFreak")

TimerFreak is a simple yet powerful web application designed to help you manage timed sequences. 
Whether you're following a workout routine, a cooking recipe, or any activity that requires a series of timed steps, 
TimerFreak ensures you stay on track with visual progress bars and custom alarms for each segment.

Easily create custom sequences with multiple timers, name them, set unique colors, and choose specific alarm sounds. 
You can loop sequences, jump to any timer, and track your progress with a global timeline. 
It's built to be straightforward and effective, helping you focus on the task at hand without distractions.

## Features

*   **Customizable Timers:** Define multiple timers within a sequence, each with its own duration, name, color, and alarm sound.
*   **Sequential Execution:** Timers run one after another automatically.
*   **Visual Progress:** See elapsed time for the current timer and overall sequence completion with intuitive progress bars.
*   **Looping Sequences:** Option to loop the entire sequence for repeated activities.
*   **Control & Navigation:** Start, stop, pause, resume, restart current or entire sequence, and jump to any timer in the sequence.
*   **Persistent Sequences:** Your created sequences have a unique URL for easy sharing and revisiting.
*   **Activity Logs:** Track when sequences and individual timers are started, paused, resumed, and ended.
*   **Most Used Sequences:** A quick overview of your frequently used sequences.
*   **Mobile-Friendly:** Designed to be easily added to your mobile device's home screen for quick access.
*   **Dark/Light Mode:** Toggle between themes for comfortable viewing.

## Setup and Development

1.  **Clone the repository:**
    ```bash
    git clone [your-repo-url]
    cd TimerFreak
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Download Alarm Sounds:**
    Navigate to the `static/` directory and download your desired MP3 alarm sounds. You can use `wget` or `curl`. Ensure the filenames match those referenced in the database migration (e.g., `alarm.mp3`, `beep.mp3`, etc.).
    Example:
    ```bash
    cd static/
    # Replace with actual direct download links to CC0 or public domain MP3 files
    # wget -O alarm.mp3 "https://example.com/alarm.mp3"
    # wget -O beep.mp3 "https://example.com/beep.mp3"
    # ... and so on for bell.mp3, chime.mp3, ding.mp3
    cd ..
    ```
    (Note: The default sounds from `app.py` are `alarm.mp3`, `beep.mp3`, `bell.mp3`, `chime.mp3`, `ding.mp3`. You need to ensure these files are present.)

5.  **Initialize and apply database migrations:**
    ```bash
    flask db init
    flask db migrate -m "Initial migration" # Only if this is the first time running migrations
    flask db upgrade
    # After adding the Sound table and initial data migration (see instructions from your collaborator), run:
    flask db migrate -m "Add Sound table and initial data" # This will create a new migration script
    # IMPORTANT: You MUST manually edit the newly created migration file to insert initial sound data.
    # Follow the instructions provided by your collaborator for editing the upgrade/downgrade functions.
    flask db upgrade # Apply the updated migration
    ```
6.  **Run the application:**
    ```bash
    flask run --host=127.0.0.1 --port=5001
    ```
    Open your browser to `http://127.0.0.1:5001/`


# License
Software is released under the MIT license, refer to file LICENSE for more information. 

# Special thanks to audio file authors
Special thanks and aknowledgment to creators of audio files: 

- Large Wind Chime - iainmccurdy
- CHIMES - SamuelGremaud
- Chime C#.wav - wormletter
- 4-tone chime WESTMINSTER - mpaol2023
- Bells 1.wav - gevaroy
- Applause & cheer - peridactyloptrix
- Explosion.mp3 - WaveAdventurer
- notification1-freesound.wav - Thoribass
- Alarm Door Chime 2.wav - kwahmah_02
- Dorrbell_Chimes_001_48Hz_24bit - Helmer88


# V.0.2.1
YO - Mejorar las  barras con mini bordes y tentativamente con algun shade. 
- base de datos con timestamps mios


# V.0.2.2.

- FIX GLITCH ULTIMA CAMPANA en desktop (con un nuevo evento). 
- Display timer duration compact (04:30).
- Display total duration at bottom
- Columnas visits, completions, en sequence con updates en timer load, finished. 
- Rename button jump correcto (go to 1 no go to timer 1). 
- Query utilizando la lógica rapida, y dejar el query actual comentado para mi. 
- El botón de install que no salga como popup

# # V.1.0.0 MINI MARKETING 

### **Marketing Assets: Visual Content Ideas**

**I. High-Impact Animated GIFs (10-30 seconds, looping, no sound):**

1.  **"Quick Setup & Go":**
    *   Show user quickly setting up a simple "5 min Work, 1 min Rest" timer (digits flying in).
    *   Brief flash of the running timer with colored bar filling.
    *   End with the "Ding!" (sound indicated by animation, no actual sound).

2.  **"Daily Grind Helper":**
    *   Seamless transition showing setup of:
        *   "Deep Work" timer.
        *   "Quick Chores" timer.
        *   "Workout Round" timer.
    *   Minimal text overlays on screen.

3.  **"From Blank to Brilliance":**
    *   Starts on an empty timer form.
    *   Digits, name, color, sound selection change rapidly/magically into a custom routine (e.g., "Study Focus", "Yoga Flow").
    *   Quick "Create!" button press and transition to running timer.

4.  **"Routine Mastered":**
    *   Show a longer sequence being created (e.g., 4 Pomodoro cycles).
    *   Quick scroll/fast-forward through sections, highlight "Total Duration."
    *   Hint at auto-looping (if enabled) but keep it concise.

5.  **"Colorful Control":**
    *   Rapid-fire animation showcasing diverse sequences with their vibrant custom colors and suggestive alarm sounds.
    *   Visually engaging with splashes of color corresponding to alarms.


*   **Reddit (Targeted Niche Subreddits):**
    *   **Curated Posts:** Craft unique, value-driven posts for `/r/productivity`, `/r/ADHD`, `/r/bodyweightfitness`, `/r/meditation`, `/r/students`, `/r/simpleliving`, `/r/homeorganization`.
    *   **Visuals:** Include the most relevant GIF/screenshot for each community.
    *   **Authenticity:** Position as "I built this..." or "Thought this might help..." – avoid overt sales.

*   **Hacker News ("Show HN" or "Launch HN"):**
    *   **Post Content:** Write a concise, technical/problem-solving narrative explaining *why* and *how* you built it, not just *what* it is.
    *   **Engage:** Be present to respond to comments and questions quickly.

*   **Twitter / X:**
    *   **Daily/Weekly:** Consistent posts using varied GIFs, screenshots, short tips on using timers for productivity/wellness.
    *   **Hashtags:** `#TimerFreak #Productivity #WorkoutTimer #StudyHacks #Meditation #WebDev #BuildInPublic #FreeTools`.
    *   **Engagement:** Tag relevant accounts, respond to trending discussions related to time management..

*   **Online Blogs/Forums/Directories (Guest Posting / Submissions):**
    *   **Research:** Find popular blogs listing productivity tools, open-source projects, web utilities.
    *   **Outreach:** Politely suggest TimerFreak for inclusion.
    *   **Submissions:** Submit to relevant free web tool directories (e.g., Alternativeto.net, Chrome Web Store if applicable, similar simple app lists).

# V.1.0.1
- MAXIMIZE CURRENT
- AUTOCOMPACT-EXPAND 
- Extra bar with lines on segment finalization 
- Visitors logging and statistics w/o cookies
- Loop counter/indicator
- Browse all


# V.2
- Looping, vueltas, y tema desde creación,
- Looping en gui. 
- ORDENAR
- Crear un logo para about
- Update db para que tenga url (current id) y id es autoincrement
- Create a copy to modify, (clone and modify)
- ¿Users can upload sounds?
- ¿SAY SOMETHING?
- ¿Temas? 


sudo journalctl -k --priority=err --since "2 days ago" | grep -i "oom"

## LICENSE
- &copy; Copyright All Rights Reserved by author.