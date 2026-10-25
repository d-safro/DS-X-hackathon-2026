# ResiliNet

**Simulating how epidemics affect hospitals — and what happens when the healthcare network is pushed beyond its limits.**

Different neighborhoods get different amounts of illness. Some of the sick people in each neighborhood need a hospital bed, and every hospital has only so many beds. When one hospital fills up, new patients have to go somewhere else, and that can push the next hospital closer to its limit. ResiliNet is a simulation that shows how this chain reaction could play out across Boston-area hospitals and the neighborhoods they serve.

- Live Demo: (LIVE_DEMO_URL)
- Demo Video: (DEMO_VIDEO_URL)
- Hackachusetts Submission: (SUBMISSION_URL)

> **This project is a research simulation, not a medical decision-making system.**
> It does not give emergency, triage, dispatch, or hospital-planning advice.

## Contents

[The problem](#the-problem) · [Our solution](#our-solution) · [How it works](#how-it-works) · [Screenshots](#screenshots-and-visual-walkthrough) · [Features](#features) · [Try ResiliNet](#try-resilinet) · [Architecture](#project-architecture) · [Tech stack](#technology-stack) · [Built with Kiro](#built-with-kiro) · [Data and limits](#data-assumptions-and-limitations) · [Testing](#testing-and-evaluation) · [Team](#team-and-acknowledgments) · [Submission](#demo-and-submission)

## The problem

Imagine a hospital with 100 beds. An outbreak causes 140 people to need care. What happens to the extra 40?

The answer depends on things that go beyond one building:

- Are other hospitals nearby, and how far away are they?
- Do those hospitals have empty beds right now?
- Which neighborhoods normally rely on the overloaded hospital?
- Are the nearby hospitals already under strain themselves?

An overloaded hospital is not only a problem for the street it sits on. Its extra patients land on other hospitals, and the neighborhoods that depended on it may lose easy access to care. ResiliNet makes that chain of effects visible so people can ask "what if?" questions and compare the answers.

ResiliNet does not tell anyone where real patients should go.

## Our solution

ResiliNet works in four steps, one simulated week at a time:

1. **Simulate how an outbreak spreads** through each neighborhood (here, each census tract in Suffolk County, Massachusetts).
2. **Estimate how many people need hospital care** each week.
3. **Allocate those patients** to nearby hospitals, and redirect extra patients to hospitals that still have room.
4. **Evaluate stress and access.** Score how strained each hospital is, and how easy it is for each neighborhood to reach care.

What makes it useful: you can change a hypothetical condition, such as closing a hospital or cutting its beds, and then compare the results with and without that change.

```text
Districts and hospitals (data)
          |
          v
   SEIR epidemic model            one week at a time
          |
          v
 New hospital admissions needed
          |
          v
 Patient allocation to nearby hospitals
          |
          v
 Network stress score, pass 1     (FDNA-based)
          |
          v
 Overflow rerouting to hospitals with free beds
          |
          v
 Network stress score, pass 2     (FDNA-based)
          |
          v
 Before/after comparison
          |
          v
 Interactive results (Streamlit app)
```

Scenario changes (a closure or a bed cut) are applied at the hospital step, so they affect everything after it. The result for each week also becomes the starting point for the next week.

## How it works

### 1. SEIR: how an outbreak spreads

SEIR sorts every person in a neighborhood into one of four groups:

| Letter | Group | Plain meaning |
|---|---|---|
| S | Susceptible | Healthy, and could catch the disease |
| E | Exposed | Caught it, but not contagious yet |
| I | Infectious | Sick and able to spread it |
| R | Recovered | Better, and protected for now |

People move from S to E to I to R. Every person is in exactly one group, so the four groups always add up to the neighborhood's population. The model checks that this stays true.

### 2. Hospital demand: who needs care

A small share of the people who finish being infectious are assumed to need a hospital bed (the default is 3%, and you can change it). Neighborhoods can also differ in how likely their residents are to need care.

The result is a number of **new people per week who need a bed**. This is a demand signal. It is not a count of occupied beds.

### 3. Patient allocation: where patients go

Each neighborhood has preferred hospitals. By default, the nearest five hospitals within 10 km are eligible, and closer hospitals get a larger share. The share drops with distance by the formula `exp(-distance / 3 km)`.

If a hospital does not have enough free beds, the extra new patients are offered to other eligible hospitals that have room. Anything that still cannot be placed is counted as **unmet need**. Unmet need is a number of people who could not be placed in the model. It is not a count of deaths.

Only new admission requests are redirected. Patients who are already in a bed stay where they are. The model does not move hospitalized patients between hospitals.

### 4. FDNA: how problems spread through a network

FDNA stands for **Functional Dependency Network Analysis**. The idea is that connected systems depend on each other, so a problem in one place can spread to the places that rely on it. Think of a power outage: when one substation fails, the neighborhoods it feeds lose power too.

In ResiliNet, each hospital gets a 0–100 "operability" score based on how loaded it is. Hospitals that are close to each other pass some of their stress along. Each neighborhood's access score then blends the scores of the hospitals it depends on.

We call our version **FDNA-based**, not classical FDNA. We made specific adaptations (for example, a fixed-point solver for hospitals that depend on each other, and share-weighted neighborhood scores), and we have not yet checked our equations against the original FDNA publication. The weights are assumptions, not measurements. Details: [docs/mathematical-model.md](docs/mathematical-model.md).

The scores are computed twice for each week: once before rerouting and once after. The scores never change the number of beds.

### 5. Scenario testing: what if something changes?

In the Streamlit app you can add two kinds of events at a chosen hospital and week range:

- **Close a hospital.** Its effective capacity drops to zero. Patients already inside are not deleted. They are reported as an "inherited deficit."
- **Set capacity.** Reduce a hospital's beds to a fraction of normal, such as 60%.

The app then shows the results next to a run with no events, so you can see what the change did.

## Screenshots and visual walkthrough

Screenshots have not been added yet. Each reserved image path below is shown as a placeholder. See [docs/assets/images/README.md](docs/assets/images/README.md) for what to capture.

(IMAGE: docs/assets/images/dashboard-overview.png — Interactive dashboard overview)

(IMAGE: docs/assets/images/epidemic-timeline.png — Epidemic timeline: weekly pressure on hospitals across the simulated weeks)

(IMAGE: docs/assets/images/hospital-network.png — Hospital network: load, capacity, and network score for one hospital)

(IMAGE: docs/assets/images/rerouting-before-after.png — Rerouting before and after a hospital closure)

(IMAGE: docs/assets/images/scenario-comparison.png — Scenario comparison against the no-event baseline)

(IMAGE: docs/assets/images/architecture-diagram.png — Architecture diagram, optional until the real asset exists)

## Features

Each item below is covered by the automated tests or by the offline demo scripts listed in [Testing and evaluation](#testing-and-evaluation).

- **Weekly epidemic simulation.** An SEIR epidemic scaled to each census tract's population, with a population-conservation check every week.
- **Three datasets.** `synthetic` (invented demo, 24 tracts and 6 hospitals), `real` (230 populated Suffolk County tracts and 9 hospitals, with a simulated epidemic), and `golden` (a 3-tract, 3-hospital test case).
- **Hospital load and capacity tracking.** Requested load, committed beds, effective capacity, and inherited deficit for each hospital and week.
- **Overflow rerouting.** Extra new admissions are redirected to hospitals with free capacity, with a row-by-row ledger of what moved where.
- **Dependency analysis.** FDNA-based hospital and neighborhood scores, before and after rerouting.
- **Scenario events.** Close a hospital or reduce its capacity, then reset to the baseline.
- **What would help (website).** For the current scenario, the website tries a few fixes (25% more beds at the most overloaded hospitals, slower spread, a shorter or cancelled closure, restored beds), reruns the model for each, and ranks them by how many more people get a bed. One click adds a fix to the scenario. These are model what-ifs, not advice.
- **Before/after and baseline comparison.** Four headline numbers: overloaded hospitals, unmet need, people rerouted, and tracts below an access score of 70.
- **Interactive app.** Sidebar controls for R0 (how contagious), hospitalization share, starting infections, distance decay, dependency strengths, and number of weeks. Map, hospital, tract, ledger, validation, and data tabs.
- **Downloads.** `hospital_week.csv`, `district_week.csv`, `reroute_week.csv`, and `run.json`.
- **Reproducible runs.** The same inputs give the same results. The app runs from small committed data snapshots and needs no internet connection for the model itself.
- **Historical backtest.** A comparison against real hospital reporting data (see [Testing and evaluation](#testing-and-evaluation)). The model does not beat the simple baseline.

The repository also contains a SvelteKit website and an earlier daily model. See [Project architecture](#project-architecture).

## Try ResiliNet

### Requirements

- Python 3.12 (the version the project targets). The automated tests also passed on Python 3.13.14.
- `git` and `pip`.
- No API keys and no account.

### Installation

macOS or Linux:

```bash
git clone https://github.com/Velzewu1/outbreak-hackachussets.git
cd outbreak-hackachussets
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
git clone https://github.com/Velzewu1/outbreak-hackachussets.git
cd outbreak-hackachussets
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

(TODO: Confirm the repository is public at this URL before submission.)

### Run locally

```bash
python -m streamlit run app/streamlit_app.py
```

Then open the address Streamlit prints, normally <http://localhost:8501>.

You should see a page titled "ResiliNet | Boston Hospital Cascade" with a banner that says `SYNTHETIC / ILLUSTRATIVE`, a sidebar of controls, a week slider, four headline numbers, and tabs for Map, Hospitals, Districts, Reroute ledger, Validation, Data & methods, and How it works.

### Try a scenario

1. In the sidebar, leave **Dataset** on `synthetic`, or switch to `real` for Suffolk County geography. The banner always says which kind of data you are looking at.
2. Move the **Week** slider to the middle of the run. The slider only changes what you view. The model has already run all the weeks.
3. Under **Scenario events**, choose `close_hospital`, pick a hospital, and click **Add event**.
4. Switch **Phase** between `before` and `after` to see the week before and after patients are redirected.
5. Read the four headline numbers. The unmet-need number shows its change compared with the no-event run.
6. Open **Reroute ledger** to see which neighborhood's patients were redirected from which hospital to which hospital.
7. Click **Reset to baseline** to remove all events.

<details>
<summary>Developer commands</summary>

```bash
python -m pytest                      # automated tests
ruff check .                          # lint
ruff format --check .                 # format check
PYTHONPATH=. python scripts/smoke_demo.py     # offline smoke run
PYTHONPATH=. python scripts/verify_demo.py    # checks the worked example in docs
PYTHONPATH=. python scripts/run_backtest.py   # historical backtest, writes artifacts/evaluation.json
PYTHONPATH=. python scripts/benchmark.py      # timing and memory benchmark
```

On Windows PowerShell, set the variable first: `$env:PYTHONPATH="."`.

The SvelteKit website (`frontend/`) has its own steps in [frontend/README.md](frontend/README.md).
(TODO: Re-run and confirm the website build commands on a clean machine before listing them as supported.)

</details>

## Project architecture

The code is split into one module per pipeline stage. The Streamlit app talks to the model through a single front door, `pipeline/api.py`, and contains no model math of its own.

```text
app/streamlit_app.py     Streamlit interface
pipeline/                the model, one module per stage
validation/              historical backtests against real data
data/raw/                small committed public-data snapshots + MANIFEST.json
scripts/                 smoke test, verification, backtest, benchmark
tests/                   automated tests
contracts/               written definitions of every object passed between stages
docs/                    math, state machine, decisions, walkthrough
config.yaml              adjustable settings
frontend/                SvelteKit website + FastAPI wrapper over the same model
seir/                    separate, earlier daily model used by the website
.kiro/                   Kiro steering files and spec
```

| Module | What it does |
|---|---|
| `pipeline/data.py`, `pipeline/data_real.py` | Load and check the synthetic fixtures and the real Suffolk data |
| `pipeline/seir.py` | Runs one week of the epidemic and produces the weekly hospital need |
| `pipeline/accessibility.py` | Computes distances and each neighborhood's share toward each hospital |
| `pipeline/il2.py`, `pipeline/hospital_state.py` | Turns need into admission requests and tracks patients already in beds |
| `pipeline/fdna.py` | Computes the hospital and neighborhood scores |
| `pipeline/analysis.py` | Places requests and redirects overflow to hospitals with free beds |
| `pipeline/injections.py` | Applies hospital closures and capacity cuts |
| `pipeline/il3.py`, `pipeline/runner.py` | Packages each week's results and runs the week loop |
| `pipeline/api.py` | The public interface the app uses |
| `validation/` | Backtests the model against real hospital data |

Deeper documentation:

- [architecture.md](architecture.md): the nine-stage pipeline and who owns what
- [docs/mathematical-model.md](docs/mathematical-model.md): every equation and unit
- [docs/weekly-state-machine.md](docs/weekly-state-machine.md): exactly what happens in a week
- [docs/end-to-end-walkthrough.md](docs/end-to-end-walkthrough.md): a worked two-week example with synthetic numbers
- [contracts/README.md](contracts/README.md): the object definitions
- [docs/architecture-decisions.md](docs/architecture-decisions.md): design choices and why

Authority order when documents disagree is listed in [AGENTS.md](AGENTS.md). The older [docs/project-brief.md](docs/project-brief.md) and the `.kiro/specs/` files carry notices that the newer documents above replace them.

## Technology stack

All versions are pinned in [requirements.txt](requirements.txt).

| Component | Technology | Purpose |
|---|---|---|
| Language | Python 3.12 | Model, app, tests |
| Numerics | NumPy, SciPy | Epidemic equations (`solve_ivp`) and parameter fitting |
| Tables | pandas | Tables and charts in the app |
| Configuration | PyYAML | Reads `config.yaml` |
| App | Streamlit | Interactive interface |
| Map | pydeck | Map of tracts and hospitals |
| Distance | Python standard library | Straight-line (haversine) distance between tracts and hospitals |
| Quality | pytest, Ruff, psutil | Tests, linting and formatting, benchmark memory use |
| CI | GitHub Actions | Runs lint, format check, tests, and demo scripts ([ci.yml](.github/workflows/ci.yml)) |
| Website (optional) | SvelteKit, FastAPI | A second interface over the same model, in `frontend/` |

`requirements.txt` also pins Shapely, NetworkX, Pydantic, and Requests. The current Python code does not import them, so they are not listed above.

## Built with Kiro

ResiliNet was planned and organized around Kiro. The repository's own rule, in [AGENTS.md](AGENTS.md), is that all project code is authored through Kiro, and the data manifest records the public-data snapshots as copied in through Kiro.

What the repository shows:

- **Planning and specifications.** A Kiro spec for the project lives in `.kiro/specs/epidemic-hospital-mvp/` (requirements, design, and task list). It is the first draft. Its own headers say it was later superseded by a reconciled specification.
- **Steering.** Four steering files in `.kiro/steering/` tell Kiro the product goal, folder layout, technology choices, and modeling rules, so each session starts with the same ground rules.
- **Reconciliation pass.** Several source plans disagreed with each other. A Kiro prompt (`Addiotional Info 1.txt`) asked for them to be reconciled into one specification: [architecture.md](architecture.md), [docs/mathematical-model.md](docs/mathematical-model.md), [docs/weekly-state-machine.md](docs/weekly-state-machine.md), and [contracts/](contracts/README.md). The decisions are logged in [docs/architecture-decisions.md](docs/architecture-decisions.md).
- **Agent rules and parallel workstreams.** [AGENTS.md](AGENTS.md) defines rules for every agent and divides the work into five workstreams with file ownership. [docs/agent-prompts/](docs/agent-prompts/README.md) holds one implementation prompt per workstream: epidemic model, dependency network, data and accessibility, hospital allocation and scenarios, and integration with the app.
- **Implementation and checks.** [architecture.md](architecture.md) and [docs/architecture-decisions.md](docs/architecture-decisions.md) record that the approval gate opened on 2026-10-24 and that the engine, loaders, validation, tests, benchmarks, and Streamlit app were then implemented.

(TODO: Describe how Kiro was used to implement the SEIR module.)
(TODO: Describe how Kiro was used to implement the FDNA module.)
(TODO: Describe how Kiro was used to implement the data, accessibility, and validation modules.)
(TODO: Describe how Kiro was used to implement the hospital allocation and scenario modules.)
(TODO: Describe how Kiro was used for debugging, testing, and integration, and whether the five workstreams actually ran in parallel.)
(TODO: Confirm which parts of `frontend/` and `seir/` were authored through Kiro. The git history lists other authors for those commits.)

### Kiro Development Artifacts

| Path | What it is |
|---|---|
| [.kiro/steering/product.md](.kiro/steering/product.md) | Product goal and constraints |
| [.kiro/steering/structure.md](.kiro/steering/structure.md) | Folder layout and architecture rules |
| [.kiro/steering/tech.md](.kiro/steering/tech.md) | Technology choices and quality commands |
| [.kiro/steering/modeling-guardrails.md](.kiro/steering/modeling-guardrails.md) | Modeling invariants and defaults |
| [.kiro/specs/epidemic-hospital-mvp/requirements.md](.kiro/specs/epidemic-hospital-mvp/requirements.md) | Spec: requirements |
| [.kiro/specs/epidemic-hospital-mvp/design.md](.kiro/specs/epidemic-hospital-mvp/design.md) | Spec: design |
| [.kiro/specs/epidemic-hospital-mvp/tasks.md](.kiro/specs/epidemic-hospital-mvp/tasks.md) | Spec: task list (not checked off; see the note at its top) |
| [AGENTS.md](AGENTS.md) | Rules for every Kiro agent |
| [docs/agent-prompts/](docs/agent-prompts/README.md) | One implementation prompt per workstream |

The `.kiro/` directory is tracked by git and is not excluded by `.gitignore`.

## Data, assumptions, and limitations

**This project is a research simulation, not a medical decision-making system.**

### What is real and what is not

| Dataset | What is real | What is invented or assumed |
|---|---|---|
| `synthetic` | Nothing. | Everything. It is an invented stress test, not an observation of any actual Boston hospital. The app labels it `SYNTHETIC / ILLUSTRATIVE`. |
| `golden` | Nothing. | A tiny made-up case used for unit tests. |
| `real` | Tract outlines and populations (2020 Census, via MassGIS). Hospital locations and licensed bed counts (MassGIS). | The epidemic is simulated. Hospital capacity uses licensed beds as a stand-in for staffed beds. The app labels it `MIXED ASSUMPTIONS`. |

Sources, licenses, and checksums are in [data/raw/MANIFEST.json](data/raw/MANIFEST.json). Only public, aggregate data is used. No patient-level records are used.

### Limitations

- **Straight-line distance.** It ignores real travel time, traffic, transit, insurance, language access, hospital systems, and transport barriers.
- **Beds only.** Capacity is a bed count. Staff, ICU strain, and equipment are not modeled.
- **Licensed beds are not staffed beds.** The real dataset uses licensed beds as a proxy.
- **Nine hospitals in the real dataset.** Only general adult acute-care hospitals in Suffolk County are included. Children's, specialty, and rehabilitation hospitals are left out, as documented in `pipeline/data_real.py`.
- **One county.** Suffolk County is not a closed system. Patients and transfers across county lines are not modeled.
- **Simple epidemic.** All tracts follow one shared epidemic curve. There is no neighborhood-to-neighborhood spread and no behavior change.
- **Unmet need is a modeling gap.** It means "the model had no bed for these people." It is not a death count and not a prediction of real events.
- **Assumed weights.** The dependency strengths in the network scores are assumptions, set in `config.yaml`.
- **Proximity is not a referral rule.** Being close does not mean two hospitals actually transfer patients.
- **A synthetic scenario is not validation.** Only the historical backtest below compares the model with real observations.

## Testing and evaluation

Results below were produced by running the commands in this repository on 2026-10-24 (Windows, Python 3.13.14, pinned dependencies).

| Check | Result |
|---|---|
| `python -m pytest` | 73 passed |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 61 files already formatted |
| `scripts/smoke_demo.py` | Passed (offline, conservation checks pass) |
| `scripts/verify_demo.py` | Passed (worked example and determinism checks) |

The tests cover SEIR population conservation, patient conservation (`accepted + unmet = need`), capacity bounds, FDNA-based score checks, hospital closures, invalid inputs, identical results across repeated runs, no use of future data in rolling forecasts, and an offline start-up of the Streamlit app.

### Historical backtest (real data)

The backtest compares the model's forecast of COVID inpatient beds in use at each hospital with real federal hospital reporting data (HHS, Suffolk County, weeks from 2020-10-04 to 2021-05-30). The simple baseline says "next week will equal this week." Both are scored on the same held-out weeks. Lower error is better.

| Strategy | Model error (beds) | Baseline error (beds) | Forecast pairs |
|---|---|---|---|
| Fixed-origin rollout | 11.47 | 2.49 | 88 |
| Rolling one-week-ahead | 18.76 | 2.49 | 88 |

Error is the mean absolute error in beds per hospital-week, over 8 matched hospitals. The training period is 23 weeks and the held-out period is 12 weeks.

**The model does not beat the simple baseline.** We report that as measured and did not tune the model on the held-out weeks. A single shared epidemic curve is too simple to track real hospital counts week to week. The synthetic scenarios shown in the app are demonstrations of the mechanism, not evidence of forecasting accuracy.

To reproduce, run `scripts/run_backtest.py` (see Developer commands).

## Team and acknowledgments

| Name | Role |
|---|---|
| (TEAM_MEMBER_1) | (ROLE) |
| (TEAM_MEMBER_2) | (ROLE) |
| (TEAM_MEMBER_3) | (ROLE) |
| (TEAM_MEMBER_4) | (ROLE) |

(TODO: Human review needed. The repository defines five development workstreams in AGENTS.md, but Hackachusetts rules supplied to us allow at most four registered teammates. Confirm who is registered before submitting, and do not list anyone who is not.)

Thanks to:

- [Hackachusetts](https://www.cics.umass.edu/events/hackachusetts) and its organizers
- The [Massachusetts AI Coalition](https://linkedin.com/company/massaicoalition)
- [Sundai](https://www.sundai.club/)
- [Kiro](https://kiro.dev/)
- MassGIS and the U.S. Department of Health and Human Services for the public data used here

## Demo and submission

| Item | Link |
|---|---|
| Public repository | (REPOSITORY_URL) |
| Demo video (under 3 minutes) | (DEMO_VIDEO_URL) |
| Live application | (LIVE_DEMO_URL) |
| Hackachusetts submission | (SUBMISSION_URL) |

None of these have been confirmed yet. A suggested three-minute demo outline is in [docs/demo-script.md](docs/demo-script.md).

(TODO: License. No license file exists in the repository. Add one before making the repository public if the rules require it.)
