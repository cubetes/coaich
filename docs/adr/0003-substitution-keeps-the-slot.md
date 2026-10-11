# A substitution keeps the slot and is not graded as a miss

When equipment is taken, the athlete swaps the exercise inside the slot instead of skipping it and adding an extra. This keeps the session's structure and the coach's view intact. The workspace grades by routine title + exercise ID, so a substituted slot would otherwise grade as "not done".

## Consequences

- Native sets must carry the slot they were performed in, plus the substitute's exercise ID. The grading side needs to read that and mark the slot `excluded` (substitution), not `not_done`.
