-- ============================================================
-- Timer Categories Migration
-- Date: 2026-04-05
-- Description: Adds category system to timer sequences
-- ============================================================

-- Step 1: Create the timer_category table
CREATE TABLE IF NOT EXISTS timer_category (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(200),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Step 2: Add category_id column to sequence table
ALTER TABLE sequence ADD COLUMN category_id INTEGER REFERENCES timer_category(id);

-- Step 3: Insert predefined categories
INSERT INTO timer_category (id, name, slug, description, sort_order, is_active) VALUES
    (1, 'Work/Study', 'work-study', 'Pomodoro, focused work, study blocks, learning, reading, writing', 10, 1),
    (2, 'Fitness', 'fitness', 'HIIT, cardio, strength training, boxing, running, workouts', 20, 1),
    (3, 'Health/Wellness', 'health-wellness', 'Yoga, meditation, mobility, sleep prep, breathing, mindfulness', 30, 1),
    (4, 'Home/Chores', 'home-chores', 'Cleaning, cooking, gardening, kitchen tasks, decluttering', 40, 1),
    (5, 'Kids/Education', 'kids-education', 'Kids activities, classroom rotation, toddler routines, bedtime', 50, 1),
    (6, 'Music/Creativity', 'music-creativity', 'Guitar practice, musical scales, creative flow, painting, digital art', 60, 1),
    (7, 'Productivity', 'productivity', 'Email batching, meetings, errands, budgeting, public speaking', 70, 1),
    (8, 'General', 'general', 'Custom timers, unnamed sequences, miscellaneous', 99, 1);

-- Step 4: Reset the autoincrement counter for timer_category
UPDATE sqlite_sequence SET seq = 8 WHERE name = 'timer_category';

-- ============================================================
-- Step 5: Auto-categorize existing sequences based on names
-- Review and adjust these as needed!
-- ============================================================

-- Work/Study (category_id = 1)
UPDATE sequence SET category_id = 1 WHERE name LIKE '%Pomodoro%' OR name LIKE '%Deep Work%' OR name LIKE '%Work/Study%' OR name LIKE '%Focused Learning%' OR name LIKE '%Active Recall%' OR name LIKE '%Reading%' OR name LIKE '%Writing Sprint%' OR name LIKE '%Memorization%' OR name LIKE '%Spaced Repetition%' OR name LIKE '%Speed Reading%' OR name LIKE '%Test Taking%' OR name LIKE '%Read Aloud%' OR name LIKE '%Focused Task%';

-- Fitness (category_id = 2)
UPDATE sequence SET category_id = 2 WHERE name LIKE '%HIIT%' OR name LIKE '%Boxing%' OR name LIKE '%Workout%' OR name LIKE '%Running%' OR name LIKE '%Cardio%' OR name LIKE '%Strength%' OR name LIKE '%Sprint Interval%' OR name LIKE '%Full Body%' OR name LIKE '%Core Crusher%' OR name LIKE '%Bodyweight%' OR name LIKE '%Seven Minute%';

-- Health/Wellness (category_id = 3)
UPDATE sequence SET category_id = 3 WHERE name LIKE '%Yoga%' OR name LIKE '%Meditation%' OR name LIKE '%Mobility%' OR name LIKE '%Flexibility%' OR name LIKE '%Sleep%' OR name LIKE '%Power Nap%' OR name LIKE '%Breath%' OR name LIKE '%Mindful%' OR name LIKE '%Visualization%' OR name LIKE '%PMR%' OR name LIKE '%Muscle Relaxation%' OR name LIKE '%Reflection%' OR name LIKE '%Gratitude%' OR name LIKE '%Positivity%' OR name LIKE '%Eye & Focus%';

-- Home/Chores (category_id = 4)
UPDATE sequence SET category_id = 4 WHERE name LIKE '%Clean%' OR name LIKE '%Cooking%' OR name LIKE '%Kitchen%' OR name LIKE '%Garden%' OR name LIKE '%Declutter%' OR name LIKE '%Batch Cooking%' OR name LIKE '%Simmering%' OR name LIKE '%Chores%' OR name LIKE '%Gardening%';

-- Kids/Education (category_id = 5)
UPDATE sequence SET category_id = 5 WHERE name LIKE '%Kids%' OR name LIKE '%Toddler%' OR name LIKE '%Classroom%' OR name LIKE '%Bedtime%' OR name LIKE '%Play Time%' OR name LIKE '%Station Rotation%';

-- Music/Creativity (category_id = 6)
UPDATE sequence SET category_id = 6 WHERE name LIKE '%Guitar%' OR name LIKE '%Musical Scales%' OR name LIKE '%Piano%' OR name LIKE '%Creative%' OR name LIKE '%Painting%' OR name LIKE '%Drawing%' OR name LIKE '%Digital Art%' OR name LIKE '%Idea Burst%' OR name LIKE '%Storyboard%' OR name LIKE '%Creative Flow%';

-- Productivity (category_id = 7)
UPDATE sequence SET category_id = 7 WHERE name LIKE '%Email%' OR name LIKE '%Admin%' OR name LIKE '%Meeting%' OR name LIKE '%Errand%' OR name LIKE '%Budgeting%' OR name LIKE '%Financial%' OR name LIKE '%Public Speaking%' OR name LIKE '%Brew Timer%' OR name LIKE '%Walk%' OR name LIKE '%Fasting%' OR name LIKE '%Hydration%';

-- ============================================================
-- Verification queries (run these to check results)
-- ============================================================

-- Check category distribution:
-- SELECT tc.name, COUNT(s.id) as sequence_count FROM timer_category tc LEFT JOIN sequence s ON tc.id = s.category_id GROUP BY tc.id, tc.name ORDER BY tc.sort_order;

-- Check uncategorized sequences (should be empty if auto-categorization worked):
-- SELECT id, name FROM sequence WHERE category_id IS NULL;
