# Nutrition rules and their evidence

The numbers `scripts/nutrition.py` uses, and why. Every study entry was checked against PubMed (authors, year,
journal, PMID/DOI). Grades as in [evidence.md](evidence.md): **SR/MA**, **RCT**, **Review**, **P** (practitioner
judgement, a position stand's recommendation, or **our rule**). A number with only P behind it says "our rule".

> The safeguards are a draft: **lawyer review pending**. CoAIch gives general wellness information, not medical
> or dietetic advice.

## Safeguards (enforced in code, tested in `tests/test_nutrition.py`)

| Rule | Code | Basis |
|---|---|---|
| Nutrition targets only from age 18. | `age` | Owner decision (plan §4). |
| One eating-disorder question. Anything but an explicit "no" switches calorie targets and fat-loss phases off and points to professional help. | `eating-disorder` | Owner decision. Physique sports carry a higher risk of disordered eating (Helms 2014; Roberts 2020 below). |
| `wellbeing_pause` (shared with the physique skill): a worrying remark mid-session pauses calorie targets, fat-loss phases and photo reviews until the user asks to lift it. | `wellbeing-pause` | Owner decision (coordination of the v0.2 lanes). |
| Pregnancy or birth < 3 months (safety item): no calorie targets. | `pregnancy` | Our rule: a deficit is not ours to set in pregnancy. |
| Calories never below estimated resting energy (Mifflin-St Jeor). | floor | Owner decision. |
| No fat-loss phase below BMI 18.5. | `bmi` | Owner decision (WHO underweight cut-off). |
| Weekly loss capped by body fat (below). | cap | Evidence + our rule. |
| No medical claims; the wording carries "lawyer review pending". | — | Owner decision. |

## Weekly loss cap (% of body weight a week)

| Body fat | Men | Women (and `unspecified`) | Cap | Default |
|---|---|---|---|---|
| Lean | < 15 % | < 23 % | **0.7 %** | 0.5 % |
| Moderate | 15–25 % | 23–33 % | **1.0 %** | 0.5 % |
| Higher | ≥ 25 % | ≥ 33 % | **1.5 %** | 0.5 % |
| Unknown | — | — | **0.7 %** (the lean cap until a range is given) | 0.5 % |

The band edges and the three caps are **our rule**, built from the evidence below. `unspecified` uses the women's
bands because they give the lower cap. Gaining: default 0.25 %, cap 0.5 % a week.

| Claim | Grade | Source | What CoAIch does with it |
|---|---|---|---|
| Lose about 0.5–1 % of body weight a week to keep the most muscle during contest prep; 2.3–3.1 g/kg lean mass protein; 15–30 % of calories from fat. Competitors should have access to mental-health professionals (eating and body-image disorders). | Review | Helms, Aragon & Fitschen 2014, *J Int Soc Sports Nutr* 11:20 · [PMID 24864135](https://pubmed.ncbi.nlm.nih.gov/24864135/) · [doi:10.1186/1550-2783-11-20](https://doi.org/10.1186/1550-2783-11-20) | Default 0.5 %; moderate cap 1.0 %; protein 2.3 g/kg lean mass when losing; fat 25 %. |
| Elite athletes losing 0.7 %/week gained lean mass and strength; 1.4 %/week kept lean mass flat. | RCT (n = 24) | Garthe et al. 2011, *Int J Sport Nutr Exerc Metab* 21(2):97–104 · [PMID 21558571](https://pubmed.ncbi.nlm.nih.gov/21558571/) · [doi:10.1123/ijsnem.21.2.97](https://doi.org/10.1123/ijsnem.21.2.97) | Lean cap 0.7 %. |
| "The higher the baseline body fat level, the more aggressively the caloric deficit may be imposed. Slower rates of weight loss can better preserve lean mass in leaner subjects." | Review (ISSN position stand) | Aragon et al. 2017, *J Int Soc Sports Nutr* 14:16 · [PMID 28630601](https://pubmed.ncbi.nlm.nih.gov/28630601/) · [doi:10.1186/s12970-017-0174-y](https://doi.org/10.1186/s12970-017-0174-y) | The cap scales with body fat. |
| The leaner a person, the larger the share of lost weight that is lean tissue (inverse curvilinear relation). | Review | Forbes 2000, *Ann N Y Acad Sci* 904:359–365 · [PMID 10865771](https://pubmed.ncbi.nlm.nih.gov/10865771/) · [doi:10.1111/j.1749-6632.2000.tb06482.x](https://doi.org/10.1111/j.1749-6632.2000.tb06482.x) | Lower caps when lean, higher when not. |
| In adults with obesity (BMI 30–45), losing 15 % over 12 weeks (≈ 1.25 %/week) was regained no faster over 144 weeks than losing it over 36 weeks. | RCT (n = 200) | Purcell et al. 2014, *Lancet Diabetes Endocrinol* 2(12):954–962 · [PMID 25459211](https://pubmed.ncbi.nlm.nih.gov/25459211/) · [doi:10.1016/S2213-8587(14)70200-1](https://doi.org/10.1016/S2213-8587(14)70200-1) | Supports a faster cap at higher body fat. The 1.5 % figure itself is the owner's decision (our rule); the resting-energy floor usually binds first. |
| Physique athletes in contest prep: ≤ 0.5 %/week preferred to keep lean mass; protein 1.8–2.7 g/kg; best-practice guidance for disordered eating. | Review | Roberts et al. 2020, *J Hum Kinet* 71:79–108 · [PMID 32148575](https://pubmed.ncbi.nlm.nih.gov/32148575/) · [doi:10.2478/hukin-2019-0096](https://doi.org/10.2478/hukin-2019-0096) | Default stays at 0.5 %. |
| Off-season: surplus ~10–20 %, gain ~0.25–0.5 % a week; protein 1.6–2.2 g/kg; fat 0.5–1.5 g/kg. | Review | Iraki et al. 2019, *Sports (Basel)* 7(7):154 · [PMID 31247944](https://pubmed.ncbi.nlm.nih.gov/31247944/) · [doi:10.3390/sports7070154](https://doi.org/10.3390/sports7070154) | Gain default 0.25 %, cap 0.5 %; fat floor 0.5 g/kg. |

## Energy

| Claim | Grade | Source | What CoAIch does with it |
|---|---|---|---|
| Resting energy = 10 × kg + 6.25 × cm − 5 × age + 5 (men) / − 161 (women). | Validation study (n = 498) | Mifflin et al. 1990, *Am J Clin Nutr* 51(2):241–247 · [PMID 2305711](https://pubmed.ncbi.nlm.nih.gov/2305711/) · [doi:10.1093/ajcn/51.2.241](https://doi.org/10.1093/ajcn/51.2.241) | Resting energy and the floor. `unspecified`: the midpoint constant −78 (our rule). |
| Activity multipliers 1.2 / 1.375 / 1.55 / 1.725 / 1.9. | P | Common practice (our rule). | A first estimate only: the weight trend replaces it. |
| 7700 kcal per kg of weight change fits people with more body fat; it overestimates the energy in weight lost by leaner people. | Model | Hall 2008, *Int J Obes* 32(3):573–576 (online 2007) · [PMID 17848938](https://pubmed.ncbi.nlm.nih.gov/17848938/) · [doi:10.1038/sj.ijo.0803720](https://doi.org/10.1038/sj.ijo.0803720) | 7700 kcal/kg for the phase deficit and the trend. Lean people may lose a little faster than planned; the weekly trend check catches it ("faster than the cap: eat more"). |
| Maintenance from the weight trend: intake − slope × 7700, over ≥ 14 days and ≥ 8 weigh-ins, used only when ±1 SE ≤ 200 kcal. | P | Our rule. | Replaces the formula once the data is good enough. |

## Protein and fat

| Claim | Grade | Source | What CoAIch does with it |
|---|---|---|---|
| Protein beyond ~1.62 g/kg/day gave no further gains in fat-free mass with training (breakpoint 95 % CI 1.03–2.20). | SR/MA (49 RCTs) | Morton et al. 2018, *Br J Sports Med* 52(6):376–384 (online 2017) · [PMID 28698222](https://pubmed.ncbi.nlm.nih.gov/28698222/) · [doi:10.1136/bjsports-2017-097608](https://doi.org/10.1136/bjsports-2017-097608) | Maintain/gain: 1.8 g/kg (between the plateau and the upper bound; our rule). Losing with body fat unknown: 2.0 g/kg (our rule). |
| 0.4 g/kg per meal over ≥ 4 meals reaches 1.6 g/kg; up to 0.55 g/kg per meal for 2.2. | Review | Schoenfeld & Aragon 2018, *J Int Soc Sports Nutr* 15:10 · [PMID 29497353](https://pubmed.ncbi.nlm.nih.gov/29497353/) · [doi:10.1186/s12970-018-0215-1](https://doi.org/10.1186/s12970-018-0215-1) | Default 4 meals; 3 or 5 on request. |
| In lean, resistance-trained athletes losing weight, protein needs are likely 2.3–3.1 g/kg of fat-free mass, higher with leaner bodies and bigger deficits. | SR (6 studies) | Helms, Zinn, Rowlands & Brown 2014, *Int J Sport Nutr Exerc Metab* 24(2):127–138 · [PMID 24092765](https://pubmed.ncbi.nlm.nih.gov/24092765/) · [doi:10.1123/ijsnem.2013-0054](https://doi.org/10.1123/ijsnem.2013-0054) | Losing with body fat known: 2.3 g/kg lean mass (the low end). |
| Fat 20–35 % of energy for athletes. | P (joint position) | Thomas, Erdman & Burke 2016, *J Acad Nutr Diet* 116(3):501–528 · [PMID 26920240](https://pubmed.ncbi.nlm.nih.gov/26920240/) · [doi:10.1016/j.jand.2015.12.006](https://doi.org/10.1016/j.jand.2015.12.006) | Fat 25 % of calories, never under 0.5 g/kg. Carbs = what is left. |
| Low-fat diets lowered total and free testosterone in men a little (SMD about −0.38; 6 studies, 206 men). | SR/MA | Whittaker & Wu 2021, *J Steroid Biochem Mol Biol* 210:105878 · [PMID 33741447](https://pubmed.ncbi.nlm.nih.gov/33741447/) · [doi:10.1016/j.jsbmb.2021.105878](https://doi.org/10.1016/j.jsbmb.2021.105878) | Why fat never goes under 0.5 g/kg. |
| Protein basis capped at the weight for BMI 30 when body fat is unknown. | P | Our rule (avoids very high protein targets for heavier people). | |

## Meal plan

Foods come from `data/foods.csv` (USDA FoodData Central, `data/SOURCE.md`). The script picks foods in a fixed order
per meal (`--prefer` first), keeps the user's diet, allergies and dislikes out, sizes protein on protein, fat on
fat and the starch on calories, rounds to 5 g or whole pieces, and reports the gap. On target (our rule): calories
within ±5 %, protein ≥ 95 % of the target.
