---
profile: 0.1
updated:
age_band:                # under-16 | 16-17 | 18-59 | 60+
health_items: []         # ids from the safety skill
pain: []                 # [{area: knee, red_flag: false, checked: }]
history:                 # never | 6m-2y | over-2y   (only periods of 2+ sessions a week)
last_trained:            # last-3m | 3-12m | over-1y
known_loads: []          # [{exercise: squat, kg: , reps: }]
chair_stand:             # 60+ beginners only: yes | no
days_per_week:
minutes_per_session:     # 30 | 45 | 60 | 75
equipment: gym           # gym only in v0.1
goal:                    # strength | muscle | both
priority: none           # advanced only: none | chest | back | shoulders | arms | quads | glutes-hamstrings | calves
exercise_swaps: []       # [{from: Romanian_Deadlift, to: Stiff-Legged_Dumbbell_Deadlift}] same slot only (monthly check-in)
# --- nutrition (v0.2, optional; onboard step 8a · skills/nutrition) ---
age_years:               # whole number; nutrition targets only from 18
sex:                     # male | female | unspecified  (energy formula only)
height:                  # 178 cm | 5 ft 10 in
weight:                  # 80 kg | 176 lb  (used until data/body.csv has weigh-ins)
activity:                # sedentary | light | moderate | very | extra
eating_disorder_history: # no | yes | prefer-not-to-say  (anything but "no": no calorie targets, no photo reviews)
wellbeing_pause:         # YYYY-MM-DD while paused (no calorie targets, no photo reviews); blank = not paused
nutrition_phase:         # maintain | gain | lose
rate_pct_week:           # optional: % of body weight a week (lose: capped by body fat; gain: max 0.5)
body_fat_pct:            # optional: a number or a range, e.g. 16-20
diet: omnivore           # omnivore | pescatarian | vegetarian | vegan
allergies: []            # milk | egg | fish | shellfish | peanut | tree-nut | soy | gluten | sesame | other words
foods_avoid: []          # food ids or words the user won't eat
weight_tracking:         # yes | no  (consent to read data/body.csv weigh-ins for the trend)
# --- end nutrition ---
# --- photos and ideal physique (v0.2, optional; onboard step 8b · skills/physique) ---
photos_opt_in:           # yes | no  (18+ only; physique skill; only an explicit yes counts)
ideal_physique:          # the user's words for the goal look ("wider shoulders, bigger arms")
long_term_priorities: [] # program regions ranked by the physique skill; used once Advanced
# --- end photos ---
---
# Profile

Notes from the intake go here.
