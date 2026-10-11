# SimDemocracy

An observer simulation of an invented polity. Three hundred algorithmic citizens start with preferences, circumstances, and personalities, and with no party, ideology, or political role. Parties, leaders, coalitions, breaches, and splits appear only when those agents have a reason to create them.

You do not play the citizens. You run a seeded history, read the event ledger, and change the rules to see which patterns move.

One tick is one week. Elections are every 12 weeks. The default run is 120 weeks.

## Run

```bash
pip install -e ".[dev]"
PYTHONPATH=src python3 -m pytest
PYTHONPATH=src python3 -m simdemocracy run --seed 3 --out runs/seed3
PYTHONPATH=src python3 -m simdemocracy explain runs/seed3/history.json --event 274
PYTHONPATH=src python3 -m simdemocracy batch --seeds 10 --out runs/batch
PYTHONPATH=src python3 -m simdemocracy serve
```

`serve` opens the observer at `http://127.0.0.1:8000`. The page asks the API to run seed 3 for 120 weeks. The browser displays that record. It does not allocate seats, score alliances, or invent events.

Useful switches on `run` and `batch`: `--ticks`, `--population`, `--seats`, `--system dhondt|sainte_lague`, `--threshold`, `--formation-cost`, `--relationship-influence`, `--ambition-scale`, `--preference-adaptation`, `--election-interval`.

## What seed 3 actually did

These figures are from one deterministic run of the default configuration (300 citizens, 61 seats, D'Hondt, seed 3). A different seed is a different history.

| | |
|---|---|
| Parties founded | 4, in weeks 1–4: The Ash Assembly, The Lantern Covenant, The Orchard Assembly, The Willow Society |
| Splits | 2. The Stone Banner left The Willow Society over ecology in week 83. The Marble Banner left it over ecology in week 110. Seats stayed with the parent until the next election. |
| Active at week 120 | 6 |
| Elections | 11 (the scheduled ten, plus one early election in week 21) |
| Governments | 14, of which 7 were multi-party |
| Signature gap of those coalitions | 63 points on the three most disputed dimensions. All 7 count as distant (gap at least 40). |
| Broken commitments | 7, followed by 3 withdrawals and 3 losses of confidence |
| Preference shift | mean absolute move of 8.4 points; 78% of citizens moved more than 10 points on at least one axis |

The first government is the one that makes the mechanism visible. In week 12 The Orchard Assembly (24 seats) and The Lantern Covenant (16 seats) formed a majority. In week 13 The Orchard Assembly moved ecology to 30 and broke a promise of about 0 to The Lantern Covenant. The recorded private driver is `base_pressure`. The public claim is that the commitment no longer matched its mandate. In week 14 a second breach, on authority, led The Lantern Covenant to withdraw. The cabinet fell to 24 seats, short of 31, and lost confidence. The next arrangement brought The Ash Assembly in, and that one broke a distribution promise as well.

Week 72 is the other shape this seed produces: The Ash Assembly, The Lantern Covenant, and The Willow Society formed a majority that excluded the largest party. In week 76 The Ash Assembly broke an ecology promise of −61, The Willow Society withdrew, and the government fell to 19 seats. A minority Orchard Assembly government then took office with confidence from The Ash Assembly.

Nothing in the engine scheduled those weeks. The same seed reproduces them. Seed 1, under the same rules, does not: three parties, a largest vote share of 0.75, and ten single-party governments with no broken commitments.

Ten default seeds (1–10), each 300 citizens and 120 weeks:

| Seed | Active parties | Largest vote share | Multi-party governments | Signature gap | Breaches |
|---|---|---|---|---|---|
| 1 | 3 | 0.75 | 0 | — | 0 |
| 2 | 4 | 0.32 | 10 | 66 | 0 |
| 3 | 6 | 0.45 | 7 | 63 | 7 |
| 4 | 5 | 0.63 | 0 | — | 0 |
| 5 | 1 | 0.51 | 0 | — | 0 |
| 6 | 7 | 0.29 | 10 | 44 | 0 |
| 7 | 5 | 0.72 | 0 | — | 0 |
| 8 | 3 | 0.61 | 0 | — | 0 |
| 9 | 6 | 0.26 | 8 | 48 | 5 |
| 10 | 3 | 0.54 | 1 | 59 | 0 |

A world with more parties is not treated as more emergent. Seed 1 is a durable majority. Seed 2 is a fragmented parliament whose distant coalitions hold. Seed 3 and seed 9 are the ones where promises break and governments fall. Seed 5 ends with a single organisation after a merger.

## Rules, not a script

The Commonwealth has eight independent policy axes. A position runs from −100 to +100. Importance runs from 0 to 1. The positive pole of each axis is recorded in every history:

| Axis | +100 | −100 |
|---|---|---|
| Distribution | equal rewards | unequal rewards |
| Taxation | high taxation | low taxation |
| Public services | collective provision | private provision |
| Authority | centralised power | decentralised power |
| Liberty | individual autonomy | social control |
| Openness | open membership and exchange | restriction |
| Ecology | environmental protection | immediate production |
| Tradition | preservation of existing customs | rapid change |

Any combination is allowed. The axes are not a political compass, and the generator does not assign ideological labels.

Citizens also have circumstances (resources, service reliance) and a personality (ambition, loyalty, compromise, stubbornness, attentiveness, and the rest). Preferences say what someone wants. Circumstances say what they need. Personality says how they pursue it.

Bounded rationality is a set of switches: incomplete knowledge of platforms, rumours, recency-weighted memory, copying a trusted neighbour, stubborn refusal to update, overconfidence, and disengagement after disappointment.

A citizen considering a party compares policy alignment on the issues they actually prioritise, social connection, trust in the leadership, expected influence, and the cost of joining. Founding is stochastic and capped. Many would-be founders do nothing. Membership is stricter than voting: a citizen can vote for a party they would not join, because of trust, competence, or a neighbour.

Alliance value mixes agreement on the issues in the deal, the value of shared seats, trust between leaders, a shared threat, historical hostility, and the cost of offending supporters. The weights follow the leaders' personalities. A coalition records concessions. If a later platform move leaves a concession, the engine updates promise-keeping, reputation, the tie between the parties, the leaders' memories, and institutional trust, and it may withdraw the creditor. There is no betrayal scene.

Parliament is list proportional representation. The default allocator is D'Hondt; Sainte-Laguë is available. Seats belong to the party until the next election. A split does not move them. A merger does. A government is a majority cabinet, a minority with confidence-and-supply, or a caretaker. An early election is called only outside the post-election lock and only when no arrangement retains confidence.

Enacted policy moves a small set of social outcomes: material wellbeing, public-service quality, stability, environmental quality, institutional trust, and the treasury. Citizens then update satisfaction and, unless adaptation is switched off, their positions. Today's programme changes tomorrow's electorate.

## How a history is stored

Every meaningful action is an event with an id, a week, a type, a factual summary, recorded drivers, and the ids of earlier events that caused it. Major events must carry drivers. A cause must be an earlier event. The chronicle is generated from those records. It cannot add a betrayal, an election, or a negotiation that the ledger does not contain.

Randomness is split into named streams (`gen`, `social`, `names`, `decision`, `info`, `rumor`, `election`, `internal`, `coalition`) derived from the seed. Policy arithmetic does not draw random numbers. The same configuration and seed replay the same history, which the tests check.

Each run records the simulation version (`0.1.0`) and the full configuration, including the pole labels.

`coalition_diversity.mean_signature_gap` is the mean, in points, of the three largest absolute platform differences inside multi-party governments. `mean_platform_distance` is the diluted average across all eight axes, scaled to 0–1. A distant alliance is a signature gap of at least 40.

## Experiments already wired in

These are hypotheses, not expected magnitudes.

- `--ambition-scale 0` — nobody founds a party.
- `--relationship-influence 0` — voting trust uses reputation only.
- `--preference-adaptation 0` — positions stay at their initial values.
- `--formation-cost` — higher cost lowers the probability that a marginal organiser founds a party.
- `--system sainte-lague` and `--threshold` — change seat allocation without changing the rest of the engine.

## Layout

```
src/simdemocracy/
  config.py        versioned rules and pole labels
  generate.py      citizens, preferences, relationships
  utility.py       join, vote, founding, and alliance scores
  organisation.py  founding, recruitment, platforms, dissolution
  elections.py     turnout, D'Hondt, Sainte-Laguë
  parliament.py    cabinets, commitments, breaches, confidence
  conflict.py      factions, splits, mergers, leadership
  policy.py        outcomes and preference updates
  engine.py        tick order and invariants
  events.py        append-only ledger
  metrics.py       descriptive measures
  explain.py       causal walk and chronicle
  strategy.py      structured-action validation for a later strategist
  api.py           FastAPI observer
  observer/        the page the API serves
```

Strategic characters are the most ambitious citizens. They are flagged in the export and still follow the same rules. `strategy.py` can accept or reject a structured proposal (a coalition offer, a platform shift of at most 25 points, a withdrawal, and so on). The tick loop does not call a language model. Recorded decisions can be replayed later; the model must not edit world state, and narration must not invent events.

Not in this version: a network graph, political archaeology beyond parent and merger links, SQLite, and a separate Next.js app. The observer is the Commonwealth overview, party dossiers, the timeline with “Why did this happen?”, and a laboratory for seeds and rule changes.
