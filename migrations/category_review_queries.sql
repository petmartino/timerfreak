-- ============================================================
-- Timer Category Analysis - Manual Review Helper
-- Run this AFTER running add_timer_categories.sql
-- ============================================================

-- 1. Category distribution overview
SELECT 
    tc.name AS category,
    COUNT(s.id) AS sequence_count,
    ROUND(COUNT(s.id) * 100.0 / (SELECT COUNT(*) FROM sequence), 1) AS percentage
FROM timer_category tc
LEFT JOIN sequence s ON tc.id = s.category_id
GROUP BY tc.id, tc.name, tc.sort_order
ORDER BY tc.sort_order;

-- 2. Sequences NOT categorized (category_id IS NULL)
-- These need manual review and assignment
SELECT id, name, created_at
FROM sequence
WHERE category_id IS NULL
ORDER BY created_at DESC;

-- 3. Sample sequences by category (for verification)
-- Change the category name to check different categories
SELECT s.id, s.name, s.created_at
FROM sequence s
JOIN timer_category tc ON s.category_id = tc.id
WHERE tc.name = 'Fitness'
ORDER BY s.created_at DESC
LIMIT 20;

-- 4. Update a specific sequence to a category (example)
-- UPDATE sequence SET category_id = 1 WHERE id = 'your_sequence_id';

-- 5. Bulk update unnamed sequences to General
-- UPDATE sequence SET category_id = 8 WHERE name = '' OR name IS NULL;

-- 6. Quick reference: category IDs
-- 1 = Work/Study
-- 2 = Fitness
-- 3 = Health/Wellness
-- 4 = Home/Chores
-- 5 = Kids/Education
-- 6 = Music/Creativity
-- 7 = Productivity
-- 8 = General
