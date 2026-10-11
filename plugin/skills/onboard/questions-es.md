# Onboard questions in Spanish (`language: es`)

Same order as [SKILL.md](SKILL.md). Answers map to the same English values in `profile.md`.

**Folder**
- Already set up: "Ya tienes todo preparado. ¿Repetimos tus respuestas o las dejamos como están?"
- New: "¿Uso esta carpeta como tu carpeta de entrenamiento? ({cwd})"
- Privacy: "Tus datos de entrenamiento se quedan en esta carpeta. Pasan por tu propia sesión de Claude, así que
  Anthropic los procesa según las condiciones de tu cuenta. Nada va a un servidor de CoAIch: no existe. Hevy o
  Apple Health solo intervienen si los activas."

**Settings**
1. "¿Inglés o español?"
2. "¿Kilos o libras?"
3. "¿Dónde están tus entrenos anteriores?" Strong (exportación CSV) · Hevy (necesita Hevy Pro y el servidor MCP
   de Hevy) · Apple Health (archivo exportado) · En ningún sitio todavía

**Age:** "¿Qué edad tienes?" Menos de 16 · 16 o 17 · De 18 a 59 · 60 o más

**Training**
1. "¿Cuánto tiempo llevas entrenando con pesas? Cuenta solo las épocas en que ibas 2 o más veces por semana."
   Nunca, o menos de 6 meses en total · De 6 meses a 2 años · Más de 2 años
2. "¿Cuándo fue la última vez que entrenaste así durante al menos un mes?" En los últimos 3 meses · Hace entre 3
   y 12 meses · Hace más de un año
3. "¿Sabes qué peso usas normalmente en sentadilla y en press de banca para unas 8 repeticiones?" Sí (kg ×
   repeticiones de cada uno) · No lo sé o no hago esos ejercicios
4. "¿Cuántos días a la semana vas a entrenar de verdad? Elige lo que puedas mantener un mes." 2 · 3 · 4 · 5 · 6
5. "¿Cuánto tiempo tienes por sesión, contando el calentamiento?" Unos 30 min · 45 · 60 · 75 o más
6. Home: "Los planes para entrenar en casa llegarán en una versión posterior."

**Placement**
- "¿Puedes levantarte de una silla 5 veces seguidas sin usar las manos?" Sí · No
- "¿Qué quieres más?" Más fuerza · Más músculo · Las dos cosas
- "¿Quieres dar prioridad a una zona?" Ninguna · Pecho · Espalda · Hombros · Brazos · Cuádriceps · Glúteos y
  femorales · Gemelos
- Line: "Te pongo en **Intermedio**: entre 6 meses y 2 años de pesas, y has entrenado en los últimos 3 meses."

**Nutrition (8a)**
- Under 18: "Los objetivos de nutrición son para mayores de 18 años."
1. "¿Quieres ayuda también con la comida: calorías diarias, proteína y un día de comidas de ejemplo?" Sí · Ahora no
2. "¿Has tenido alguna vez un trastorno de la conducta alimentaria, o te han tratado por uno?" No · Sí · Prefiero
   no decirlo
3. "¿Cuántos años tienes?"
4. "Para la fórmula de energía: ¿hombre, mujer o prefieres no decirlo?"
5. "¿Cuánto mides?" (cm, o pies y pulgadas)
6. "¿Cuánto pesas ahora?" (kg o lb)
7. "¿Cómo de activa es una semana normal, contando el gimnasio?" Casi todo sentado, poco ejercicio · Casi todo
   sentado, entreno 1–3 días · Entreno 3–5 días, o paso mucho tiempo de pie · Entreno 6–7 días, o trabajo físico y
   entreno · Trabajo físico duro y entreno duro casi todos los días
8. "¿Qué quieres que haga tu peso?" Mantenerse más o menos igual · Subir poco a poco, para ganar músculo · Bajar,
   para perder grasa. Bajar: "¿Sabes más o menos tu porcentaje de grasa? Un rango vale, como 16–20 %. O sáltalo."
   · "Empezamos con un 0,5 % de tu peso a la semana. Lo más rápido que vamos depende de tu grasa corporal."
9. "¿Comes de todo, sin carne, sin carne ni pescado, o nada de origen animal?" · "¿Alguna alergia o intolerancia
   alimentaria?" · "¿Algo que no comas?"
10. "¿Puede CoAIch leer tus pesajes (`data/body.csv`) cada semana para ver tu tendencia y corregir las calorías?
    Se quedan en esta carpeta." Sí · No

**Photos and ideal physique (8b)** (draft, lawyer review pending)
1. "¿Quieres usar fotos de progreso? Valoraría cómo va cada grupo muscular, las compararía con el tiempo y te
   ayudaría a elegir qué entrenar más. Tu ordenador recorta tu cara de cada foto antes de que yo la vea, y solo
   se guarda esa copia, en esta carpeta, sin la ubicación ni los datos de la cámara. Puedes desactivarlo cuando
   quieras." Sí · No
2. "¿Buscas un físico concreto? Descríbelo en pocas palabras, o di que no. (Por ejemplo: hombros más anchos,
   brazos más grandes, piernas más fuertes.)"
