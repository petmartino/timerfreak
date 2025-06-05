#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.
set -x # Print commands and their arguments as they are executed.

# --- Parameters (Adjust these to fine-tune the sound) ---
BEEP_FREQ=2800           # Hz (Still good, high-pitched)
BEEP_DURATION=0.06       # seconds (How long each individual beep lasts)
SHORT_SILENCE_DURATION=0.03 # seconds (Pause between beeps within a burst)
LONG_SILENCE_DURATION=0.6 # seconds (Pause between bursts of beeps)
BEATS_PER_BURST=4        # Number of beeps in one group (e.g., 3 or 4)
NUM_BURSTS=5             # How many times the full pattern repeats for the alarm duration

# --- Emulation Parameters ---
HIGHPASS_FREQ=1500 # Cut everything below this frequency (Hz)
LOWPASS_FREQ=4000  # Cut everything above this frequency (Hz)
NORM_LEVEL=-6      # dB (adjust to make it comfortably loud without clipping)


# --- Create Temporary Sound Components ---

echo "Creating individual sound components..."

# 1. Create a single high-pitched square wave beep
#    `fade 0.005` adds a very slight fade out to prevent clicks at the end of the short beep
sox -n temp_single_beep.wav synth ${BEEP_DURATION} square ${BEEP_FREQ} fade 0.005

# 2. Create a short silence (for between beeps in a burst)
sox -n temp_short_silence.wav trim 0.0 ${SHORT_SILENCE_DURATION}

# 3. Create a long silence (for between bursts)
sox -n temp_long_silence.wav trim 0.0 ${LONG_SILENCE_DURATION}


# --- Assemble One Burst of Beeps ---

echo "Assembling one burst of beeps..."

BURST_FILES=""
for i in $(seq 1 $BEATS_PER_BURST); do
    BURST_FILES="${BURST_FILES} temp_single_beep.wav"
    if [ $i -lt $BEATS_PER_BURST ]; then
        BURST_FILES="${BURST_FILES} temp_short_silence.wav"
    fi
done

# Check if BURST_FILES is empty, which would cause sox to hang
if [ -z "$BURST_FILES" ]; then
    echo "Error: BURST_FILES is empty. Check BEATS_PER_BURST parameter."
    exit 1
fi

sox ${BURST_FILES} temp_alarm_burst.wav


# --- Assemble One Full Cycle (Burst + Long Silence) ---

echo "Assembling one full alarm cycle..."
sox temp_alarm_burst.wav temp_long_silence.wav temp_alarm_cycle.wav


# --- Create the Final Alarm by Repeating the Cycle ---

echo "Repeating cycles to create final alarm..."
FULL_ALARM_FILES=""
for i in $(seq 1 $NUM_BURSTS); do
    FULL_ALARM_FILES="${FULL_ALARM_FILES} temp_alarm_cycle.wav"
done

# Check if FULL_ALARM_FILES is empty, which would cause sox to hang
if [ -z "$FULL_ALARM_FILES" ]; then
    echo "Error: FULL_ALARM_FILES is empty. Check NUM_BURSTS parameter."
    exit 1
fi

# --- Emulate Piezoelectric Buzzer Sound on Larger Speakers ---

# Step 1: Concatenate all alarm cycles into a single intermediate WAV file
echo "Concatenating alarm cycles into a single intermediate WAV for processing..."
sox ${FULL_ALARM_FILES} temp_final_alarm_unprocessed.wav

# Step 2: Apply the emulation effects (highpass, lowpass, norm) to the intermediate WAV
echo "Applying buzzer emulation effects: highpass ${HIGHPASS_FREQ}Hz, lowpass ${LOWPASS_FREQ}Hz, normalize ${NORM_LEVEL}dB..."
sox temp_final_alarm_unprocessed.wav casio_f91w_alarm.wav highpass ${HIGHPASS_FREQ} lowpass ${LOWPASS_FREQ} norm ${NORM_LEVEL}


# --- Convert to MP3 ---

echo "Converting to MP3..."
ffmpeg -i casio_f91w_alarm.wav casio_f91w_alarm.mp3


# --- Clean Up Temporary Files ---

echo "Cleaning up temporary files..."
rm -f temp_single_beep.wav temp_short_silence.wav temp_long_silence.wav \
   temp_alarm_burst.wav temp_alarm_cycle.wav temp_final_alarm_unprocessed.wav casio_f91w_alarm.wav

echo "Casio F-91W style alarm sound created: casio_f91w_alarm.mp3"

# --- Play the sound (Optional - requires ffplay) ---
# ffplay -nodisp -autoexit casio_f91w_alarm.mp3