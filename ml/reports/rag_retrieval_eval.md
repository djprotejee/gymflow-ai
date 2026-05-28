# RAG Retrieval Evaluation

- Method: BM25-style lexical retrieval over GymFlow chunks
- Queries: 6
- Hit@1: 0.8333
- Hit@3: 1.0
- Hit@6: 1.0
- MRR: 0.9167

| Query | Expected source | Relevant rank | Top hit |
|---|---:|---:|---|
| bench press technique | exercise_library | 1 | Close Grip Bench Press (exercise_library) |
| lat pulldown common mistakes | exercise_library | 1 | Machine Lat Pulldown (exercise_library) |
| my recent workout progress | workout_history | 1 | Recent workout history (workout_history) |
| saved workout template | workout_template | 2 | Recent workout history (workout_history) |
| preferred quiet training time | user_preferences | 1 | Training preferences (user_preferences) |
| scheduled workouts this week | scheduled_workouts | 1 | Scheduled workouts (scheduled_workouts) |

Note: This evaluates the current non-vector RAG retrieval layer; it is not a fine-tuned model evaluation.
