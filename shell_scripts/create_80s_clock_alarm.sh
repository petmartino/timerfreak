#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.
set -x # Print commands and their arguments as they are executed.

# --- Parameters (Adjust these to fine-tune the sound) ---
BEEP_FREQ=1200           # Hz (Typical for digital clocks/radios)
BEEP_DURATION=0.15       # seconds (A solid, distinct beep)
SILENCE_DURATION=0.25    # seconds (Consistent pause between beeps)
NUM_BEATS=10             # Total number of beeps for the alarm (adjust for total duration)

# --- Emulation Parameters ---
# For a typical 80s digital alarm, less aggressive filtering than a watch.
# A mild high-pass might still be good to prevent it from sounding too "full"
# or to remove any potential low-end hum.
HIGHPASS_FREQ=500        # Hz (Optional: cut low frequencies for a "thin" sound)
NORM_LEVEL=-6            # dB (Normalize volume for consistency)


# --- Create Temporary Sound Components ---

echo "Creating individual sound components..."

# 1. Create a single digital-style square wave beep
#    `fade 0.005` for a clean attack/decay
sox -n temp_single_beep.wav synth ${BEEP_DURATION} square ${BEEP_FREQ} fade 0.005

# 2. Create a silence of desired duration
sox -n temp_silence.wav trim 0.0 ${SILENCE_DURATION}


# --- Assemble One Full Cycle (Beep + Silence) ---

echo "Assembling one full alarm cycle (beep + silence)..."
sox temp_single_beep.wav temp_silence.wav temp_alarm_cycle.wav


# --- Create the Final Alarm by Repeating the Cycle ---

echo "Repeating cycles to create final alarm..."
FULL_ALARM_FILES=""
for i in $(seq 1 $NUM_BEATS); do
    FULL_ALARM_FILES="${FULL_ALARM_FILES} temp_alarm_cycle.wav"
done

# Check if FULL_ALARM_FILES is empty, which would cause sox to hang
if [ -z "$FULL_ALARM_FILES" ]; then
    echo "Error: FULL_ALARM_FILES is empty. Check NUM_BEATS parameter."
    exit 1
fi

# --- Emulate 80s Digital Alarm Sound Characteristics ---

# Step 1: Concatenate all alarm cycles into a single intermediate WAV file
echo "Concatenating alarm cycles into a single intermediate WAV for processing..."
sox ${FULL_ALARM_FILES} temp_final_alarm_unprocessed.wav

# Step 2: Apply emulation effects (highpass for thinness, normalize for volume)
# Removed `lowpass` as 80s alarms often had a slightly fuller high-end than small buzzers.
echo "Applying emulation effects: highpass ${HIGHPASS_FREQ}Hz (optional), normalize ${NORM_LEVEL}dB..."
# Use `temp_final_alarm_unprocessed.wav` as input and `digital_alarm_80s.wav` as output
sox temp_final_alarm_unprocessed.wav digital_alarm_80s.wav highpass ${HIGHPASS_FREQ} norm ${NORM_LEVEL}


# --- Convert to MP3 ---

echo "Converting to MP3..."
ffmpeg -i digital_alarm_80s.wav digital_alarm_80s.mp3


# --- Clean Up Temporary Files ---

echo "Cleaning up temporary files..."
rm -f temp_single_beep.wav temp_silence.wav temp_alarm_cycle.wav \
   temp_final_alarm_unprocessed.wav digital_alarm_80s.wav

echo "80s Digital Alarm sound created: digital_alarm_80s.mp3"

# --- Play the sound (Optional - requires ffplay) ---
# ffplay -nodisp -autoexit digital_alarm_80s.mp3