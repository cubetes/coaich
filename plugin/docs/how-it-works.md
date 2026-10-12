# How CoAIch works

Everything lives in one **athlete folder** on your computer. Skills read it, change it through small scripts,
and explain every number they write. Nothing goes to a CoAIch server: there isn't one.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="how-it-works-dark.svg">
  <img src="how-it-works.svg" alt="How CoAIch works: you start once (setup, a safety check, a program you approve), then a weekly loop imports your workouts and Apple Health data, grades last week and proposes next week for your OK; every four weeks a monthly check-in plans the next month. Strong, openGym and Apple Health send files in; progress photos (front, side, back) have the face removed by Apple Vision on your Mac before Claude or Anthropic see them; Hevy works both ways with your yes, and your Claude session runs on Anthropic. No CoAIch server.">
</picture>

## The skills

```mermaid
flowchart TD
    you(["You, in Claude Code"])

    subgraph start ["Getting started"]
        onboard["/onboard<br/>questions about you"]
        safety{"safety<br/>medical gate"}
        build["program-build<br/>picks and adapts a program"]
        audit["program-audit<br/>checks it against the rules"]
        roadmap["roadmap<br/>macro › phase › meso › micro"]
    end

    subgraph data ["Your data comes in"]
        strong["Strong CSV"]
        hevy["Hevy"]
        health["Apple Health"]
        import["import"]
    end

    folder[("Athlete folder<br/>profile · plan · sets · body · health · photos · check-ins")]

    subgraph loop ["Every week"]
        weekly["/weekly-review"]
        progression["progression<br/>next target + its reason"]
    end

    subgraph month ["Every month"]
        monthly["/monthly-check-in"]
        nutrition["nutrition<br/>targets + meal plan"]
        physique["physique<br/>photo review + priorities"]
        adapt["adapt<br/>injury · travel · short on time"]
    end

    you --> onboard
    onboard --> safety
    safety -- "go / warn" --> build
    safety -- "stop: see a doctor first" --> you
    build --> audit
    audit -- "passes" --> folder
    audit -- "fails: nothing written" --> build
    roadmap --> folder

    strong --> import
    hevy --> import
    health --> import
    import --> folder

    folder --> weekly
    weekly --> progression
    progression -- "you OK the changes" --> folder

    folder --> monthly
    monthly --> nutrition
    monthly --> physique
    monthly --> roadmap
    monthly --> build
    adapt --> build
```

## The training loop

```mermaid
sequenceDiagram
    autonumber
    actor A as You
    participant G as Gym (Strong, Hevy or the app)
    participant C as CoAIch in Claude Code
    participant F as Athlete folder

    A->>G: Train and log sets, with "how many more could you have done"
    A->>C: "Import my week"
    C->>F: Sessions, sets, body weight, sleep, steps
    A->>C: /weekly-review
    C->>F: Read last week's targets and what you did
    C-->>A: Grade per exercise + next week's targets, each with its reason
    A->>C: OK (spine lifts always need your explicit OK)
    C->>F: Freeze next week's targets
    Note over A,F: Every 4 weeks
    A->>C: /monthly-check-in
    C-->>A: Trends, did past changes work, next month's plan
    C->>F: Re-issued program, roadmap position, nutrition and photo notes
```

## How a next target is decided

```mermaid
flowchart LR
    s["Your sets this session"] --> top{"Every set at the<br/>top of the rep range?"}
    top -- "no" --> reps{"Reps up?"}
    reps -- "yes" --> addr["Same weight,<br/>more reps"]
    reps -- "no, missed twice" --> lighter["5 % lighter"]
    reps -- "no, first miss" --> repeat["Repeat the target"]
    top -- "yes" --> left{"How many more<br/>could you have done?"}
    left -- "0 (failure)" --> hold["Same weight,<br/>stop one rep earlier"]
    left -- "fewer than the target" --> hold2["Same weight"]
    left -- "on target" --> one["+1 step"]
    left -- "1 more" --> two["+2 steps"]
    left -- "2 or more" --> three["+3 steps"]
```

Steps are capped by your level and your equipment (a lower-body barbell never jumps more than 10 kg at once).
