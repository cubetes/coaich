# Spanish glossary (Spain, tú)

Draft for the owner's review (issue #10). Used by `TEXT["es"]` in `plugin/scripts/progression.py`.

| English | Spanish | Why |
|---|---|---|
| reps left | te quedaban N (repeticiones) | How people say it at the gym; avoids "repeticiones en reserva". |
| keep 2 reps in the tank | que te queden 2 repeticiones | Same idea as "te quedaban", one phrase everywhere. |
| easy week | semana suave | Plain; the calendar parser already reads "suave". Never "descarga". |
| travel week | semana de viaje | Literal and clear. |
| log (a set, a session) | apuntar | What people do with a notebook or app. |
| target | objetivo | Plain. |
| set / rep | serie / repetición | Full words, no "reps". |
| miss (target not reached) | no llegar / sin llegar | "Fallo" means muscle failure in the gym, so it is kept for that only. |
| failure (nothing left) | llegar al fallo | The usual gym phrase. |
| not graded | no cuenta | Short; "evaluar" sounds like school. |
| top of the range | arriba del rango | Short. |
| load step | salto de peso | Says what it is. |
| re-anchor | lo ajustamos a lo que levantaste | No jargon. |
| compound lift | ejercicio compuesto | Clear; "básico" is the gym slang (see doubts). |
| needs your OK | necesita tu visto bueno | Natural in Spain. |
| time off / break | parón | Spain gym word for a break. |
| rep record | récord de repeticiones | Plain. |

## Doubts for the owner

- "repeticiones" in full, or "reps" as many gyms in Spain say?
- "ejercicio compuesto" or "básico"?
- Numbers print with a dot ("2.5 kg"). `fmt_kg` is shared with file output, so the comma was not changed.
