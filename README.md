# ResiliNet

**A simulation and analysis tool for outbreak surges: it shows how strain spreads through a connected hospital network, and which neighborhoods lose access to care when one hospital fills up or closes.**

| | |
|---|---|
| Demo video | <https://youtu.be/zNkBcC58YjI> |
| Repository | <https://github.com/Velzewu1/outbreak-hackachussets> |
| Hackachusetts project page | <https://www.sundai.club/projects/6054f32f-e27c-4e84-b7ed-afc7b917a3fc> |
| Built at | BU Spark! DS+X Hackathon 2026 and Hackachusetts 2026 |

> **ResiliNet is a research simulation, not a medical decision-making system.**
> It does not give emergency, triage, dispatch, or hospital-planning advice, and it does not tell anyone where real patients should go.

## Contents

[Quick start](#quick-start) · [Try a scenario](#try-a-scenario) · [The problem](#the-problem) · [What it does](#what-it-does) · [How it works](#how-it-works) · [Data](#data) · [Validation](#validation) · [Assumptions and limitations](#assumptions-and-limitations) · [Ethics](#ethics-and-responsibility) · [Architecture](#architecture) · [Built with Kiro](#built-with-kiro) · [Team](#team)

## Quick start

You need **Python 3.12 or newer** and **git**. No API keys, no accounts, no internet connection once installed. The install takes one to three minutes.

### macOS or Linux

Copy and paste the whole block into a terminal:

```bash
git clone https://github.com/Velzewu1/outbreak-hackachussets.git
cd outbreak-hackachussets
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py
```

### Windows (PowerShell)

```powershell
git clone https://github.com/Velzewu1/outbreak-hackachussets.git
cd outbreak-hackachussets
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py
```

Then open **<http://localhost:8501>** in a browser (Streamlit usually opens it for you).

**Next time**, you only need the last line, from inside the folder with the environment active:

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m streamlit run app/streamlit_app.py
```

### If something goes wrong

| Problem | Fix |
|---|---|
| `python3: command not found` or a version below 3.12 | Install Python 3.12+ from <https://www.python.org/downloads/>, then use `python3.12 -m venv .venv` |
| PowerShell says running scripts is disabled | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again |
| Port 8501 is already in use | `python -m streamlit run app/streamlit_app.py --server.port 8502` |
| Streamlit asks for an email on first run | Press Enter to skip |

## Try a scenario

A two-minute walkthrough of the main idea:

1. In the sidebar, set **Dataset** to `real`. The map now shows Suffolk County's census tracts and nine hospitals, and the banner reads `MIXED ASSUMPTIONS` (real geography and beds, simulated epidemic). The default `synthetic` dataset is a small invented city.
2. Move the **Week** slider to the middle of the run.
3. Under **Scenario events**, choose `close_hospital`, pick a hospital, and click **Add event**. You can also choose `set_capacity` to cut a hospital to, for example, 60% of its beds.
4. Read the four headline numbers: overloaded hospitals, unmet need, people rerouted, and tracts below an access score of 70. Each shows its change against the run with no events.
5. Switch **Phase** between `before` and `after` to see the week before and after overflow is rerouted.
6. Open the **Reroute ledger** tab to see whose patients went from which hospital to which.
7. Open **Map**, **Hospitals**, and **Districts** to see which neighborhoods lost access.
8. Click **Reset to baseline** to clear all events.

The sidebar also has sliders for R0 (how contagious the disease is), the hospitalization share, starting infections, distance decay, dependency strengths, and the number of weeks. Results can be downloaded as CSV and JSON.

## The problem

Hospitals do not fail alone. Imagine a hospital with 100 beds when an outbreak sends it 140 patients. The extra 40 land on nearby hospitals, which may already be strained, and the neighborhoods that relied on the first hospital lose easy access to care.

Capacity is usually looked at one building at a time, so it is hard to answer questions like: *if this hospital closes or loses beds in the middle of a surge, which neighborhoods lose care, and where does the overflow go?*

## What it does

- **Simulates an outbreak week by week** across every census tract, and turns it into new hospital admissions.
- **Places patients** at nearby hospitals, weighted by distance, and **reroutes overflow** to hospitals that still have free beds. Anyone who cannot be placed is counted as unmet need.
- **Models hospitals as an interconnected network.** Each hospital gets a 0–100 operability score, strain passes between nearby hospitals, and each neighborhood's access score blends the hospitals it depends on.
- **Runs what-if scenarios**: close a hospital or cut its capacity over a chosen range of weeks, then compare against the same run with no events.
- **Shows before and after** for every week (before and after rerouting), with a ledger of every rerouted group of patients.
- **Labels everything.** A banner always says whether you are looking at synthetic or real data, and every setting in `config.yaml` is tagged as assumed, fitted, or taken from the plan.
- **Accepts any starting snapshot.** The demo starts from 2020–21 Suffolk County data, but the pipeline takes any set of districts, hospitals, and starting state, including this week's numbers, and simulates forward from there.
- **Validates honestly** against real hospital reporting data, and reports the result even though the simple baseline wins (see [Validation](#validation)).

## How it works

ResiliNet runs one simulated **week** at a time. A week is the unit because the hospital data we validate against (HHS) is reported weekly. The result of each week is the starting point for the next.

```text
Districts + hospitals (data)
        |
        v
SEIR epidemic, per census tract  ->  new hospital admissions needed
        |
        v
Patient placement at nearby hospitals (distance-weighted)
        |
        v
Network scores, pass 1 (FDNA-based)       <- scenario events applied here
        |
        v
Overflow rerouting to hospitals with free beds
        |
        v
Network scores, pass 2 (FDNA-based)
        |
        v
Before/after comparison  ->  next week
```

### 1. SEIR: how an outbreak spreads

Every person in a tract is in one of four groups: **S**usceptible (could catch it), **E**xposed (caught it, not contagious yet), **I**nfectious, or **R**ecovered. People move S → E → I → R, and the four groups always add up to the tract's population; the model checks this every week. A share of the people leaving the infectious group need a hospital bed (default 3%). That gives the number of **new people per week who need a bed**.

### 2. Patient placement: where patients go

Each tract can use up to its five nearest hospitals within 10 km. Closer hospitals get a larger share, falling off as `exp(-distance / 3 km)`. This straight-line distance rule is a deliberate simplification given the time we had; a closer-to-reality mapping would use travel time, insurance networks, and hospital systems.

If a hospital is full, its extra **new** patients are offered to other eligible hospitals with room. Patients already in a bed stay where they are, even if their hospital closes. Anything that still cannot be placed is **unmet need**: a gap in the model, not a count of deaths.

### 3. FDNA-based network scores: how strain spreads

FDNA (Functional Dependency Network Analysis) describes systems that depend on each other, so that trouble in one spreads to the ones that rely on it. In ResiliNet:

- Each hospital's own score (0–100) comes from how loaded it is.
- Hospitals within 5 km are linked both ways, so a struggling hospital pulls its neighbors' scores down a little. Because the links form loops, the scores are solved together until they settle.
- Each neighborhood's access score blends the scores of the hospitals it depends on, weighted by its distance shares.

We call this **FDNA-based**, not classical FDNA: the two-way hospital links, the loop solver, and the share-weighted neighborhood scores are our adaptations. The scores are computed twice a week, before and after rerouting, and never change the number of beds. Full equations: [docs/mathematical-model.md](docs/mathematical-model.md).

### 4. Scenario events

Events are applied from a chosen start week to an optional end week. The app offers **close a hospital** (capacity drops to zero; patients already inside are kept and reported as an inherited deficit) and **set capacity** (a fraction of normal beds). The engine in `pipeline/injections.py` also supports changing scores, hospital links, and neighborhood shares.

## Data

| Dataset | What is real | What is invented or assumed |
|---|---|---|
| `real` | Census tract outlines and populations (2020 Census, via MassGIS): 230 populated Suffolk County tracts. Hospital locations and licensed beds (MassGIS): 9 general adult acute-care hospitals. | The epidemic is simulated. Licensed beds stand in for staffed beds. Labeled `MIXED ASSUMPTIONS` in the app. |
| HHS hospital capacity, 2020–21 | Weekly COVID-occupied beds per Suffolk hospital, from federal reporting. | Used only for validation. |
| `synthetic` | Nothing. | An invented 24-tract, 6-hospital city for demonstrating the mechanism. Labeled `SYNTHETIC / ILLUSTRATIVE`. |
| `golden` | Nothing. | A 3-tract, 3-hospital case used by the tests. |

Only public, aggregate data is used, with no patient-level records. Sources, licenses, and checksums are in [data/raw/MANIFEST.json](data/raw/MANIFEST.json). The app runs from these committed snapshots and never calls a live API.

## Validation

We backtested the model against real HHS reporting: COVID inpatient beds in use at each of 8 Suffolk County hospitals, weekly from 2020-10-04 to 2021-05-30. R0 is fitted on the first 23 weeks only, and both the model and a simple baseline ("next week equals this week") are scored on the last 12 weeks.

| Strategy | Model error (beds) | Baseline error (beds) | Forecast pairs |
|---|---|---|---|
| Fixed-origin rollout | 11.47 | 2.49 | 88 |
| Rolling one-week-ahead | 18.76 | 2.49 | 88 |

Error is the mean absolute error in beds per hospital-week. Lower is better.

**The model does not beat the simple baseline, and we report that as measured.** ResiliNet is an approximation: we had to define the hospital-to-hospital dependencies and a custom cost function for how districts depend on hospitals ourselves. All of these are adjustable parameters, so the error mostly shows how far our default values are from reality, not a limit of the method. The tool is built to show the mechanism of a cascade, not to forecast hospital counts.

Reproduce with `PYTHONPATH=. python scripts/run_backtest.py`.

Automated checks (run 2026-10-24): `pytest` 73 passed; `ruff check` and `ruff format --check` clean; `scripts/smoke_demo.py` and `scripts/verify_demo.py` pass. The tests cover population conservation, patient conservation (`accepted + unmet = need`), capacity bounds, network score checks, closures, invalid inputs, identical results across repeated runs, and no use of future data in the rolling forecast.

## Assumptions and limitations

We mapped much more of the real-world system than we could build in a weekend, then chose what belongs in the MVP. Several later layers already have placeholder functions or hooks in the code. Every value below is set in [config.yaml](config.yaml) and can be changed.

**How the system is simplified**

- **One node per hospital, one layer.** Each hospital stands in for everything that gets a patient into a bed: ambulance and transport, emergency triage, referrals, specialty units, staffing, and the outpatient care around it. In reality these are separate systems, each with its own capacity and its own links to other hospitals, so failures can spread through several layers at once. We collapsed them into one hospital node and one layer of hospital-to-hospital links because of the time we had. Splitting a hospital into service nodes (EMS, ED, ward, ICU) and adding layers is the natural next step.
- **Straight-line distance.** It ignores travel time, traffic, transit, insurance, language access, hospital systems, and transport barriers.
- **Beds only.** No staff, separate ICU, or equipment in the weekly model.
- **Licensed beds, not staffed beds.**
- **Proximity is not a referral rule.** Two nearby hospitals are linked even if they do not actually transfer patients.
- **One county, nine hospitals.** Suffolk County is treated as closed, with no cross-county transfers. Children's, specialty, cancer, rehabilitation, and psychiatric hospitals are left out, with reasons in `pipeline/data_real.py`.

**Epidemic**

- One shared epidemic curve for every tract; tracts differ by population and risk weight, with no spread between neighborhoods and no behavior change.
- Risk weight changes the hospitalization rate, not transmission.
- R0 starts at 2.5 and is fitted to data in the backtest. Latent period 5 days, infectious period 7 days, length of stay 7 days (rounded up to whole weeks), 0.1% infectious at the start, 3% of people leaving the infectious group need a bed.
- Rerouting and closures never feed back into the epidemic.

**Network**

- A tract depends on up to 5 hospitals within 10 km, with shares `exp(-d / 3 km)`. One tract has no hospital within 10 km and is assigned to its nearest (11.4 km); this is disclosed in the data manifest.
- Hospitals within 5 km are linked both ways with strength 0.1. Tracts depend on hospitals with strength 0.9. These weights are assumptions, not measurements.
- Only new admissions are rerouted, only into free beds, and closed hospitals never receive patients.

**What would make it better**

Much of the missing detail (staffed beds, transfer agreements, EMS routing, real travel times) is best obtained in collaboration with public-health agencies and hospital systems. With it, the next steps are multi-layer service nodes, spread between neighborhoods, and replacing assumed weights with measured ones. The repository's separate daily model (below) already adds some of this.

## Ethics and responsibility

- **Data sourcing.** Public, aggregate sources only (2020 Census via MassGIS, MassGIS hospitals, HHS hospital capacity), each recorded with its source, license, and checksum.
- **Privacy.** No patient-level or personal data is collected or used.
- **Bias and fairness.** Straight-line distance can overstate access for neighborhoods that depend on transit or face language or insurance barriers, so access scores may look better than residents experience. We state this rather than hide it.
- **Harm and mitigation.** Misread as a forecast, the tool could mislead planning. The app labels every dataset as synthetic or mixed, calls unmet need a modeling gap rather than deaths, and the README reports that the model loses to a simple baseline.
- **Transparency.** Every assumption is a labeled, adjustable setting, and the equations are documented in [docs/mathematical-model.md](docs/mathematical-model.md).

## Architecture

The code has one module per pipeline stage. The Streamlit app reaches the model only through `pipeline/api.py` and contains no model math of its own.

```text
app/streamlit_app.py     Streamlit interface (the main demo)
pipeline/                the weekly model, one module per stage
validation/              backtests against real HHS data
data/raw/                committed public-data snapshots + MANIFEST.json
config.yaml              every adjustable setting, with its provenance
scripts/                 smoke test, verification, backtest, benchmark
tests/                   automated tests
contracts/               definitions of every object passed between stages
docs/                    equations, weekly state machine, decisions, walkthrough
frontend/                optional SvelteKit website + FastAPI wrapper
seir/                    a second, more detailed daily model
.kiro/                   Kiro steering files and spec
```

| Module | What it does |
|---|---|
| `pipeline/data.py`, `pipeline/data_real.py` | Load and check the synthetic and real Suffolk data |
| `pipeline/seir.py` | One week of the epidemic, producing new bed demand |
| `pipeline/accessibility.py` | Distances and each tract's share toward each hospital |
| `pipeline/il2.py`, `pipeline/hospital_state.py` | Admission requests and patients already in beds |
| `pipeline/fdna.py` | Hospital and neighborhood network scores |
| `pipeline/analysis.py` | Placement and overflow rerouting |
| `pipeline/injections.py` | Scenario events |
| `pipeline/il3.py`, `pipeline/runner.py` | Weekly results and the week loop |
| `validation/` | Fitting and backtests |

**Tech stack:** Python 3.12, NumPy and SciPy (`solve_ivp` for the epidemic, parameter fitting), pandas, PyYAML, Streamlit, pydeck (map), pytest and Ruff, GitHub Actions CI. All versions are pinned in [requirements.txt](requirements.txt).

### The daily model (`seir/`)

A second, more detailed model built earlier in the weekend: a daily metapopulation SEIR with age groups, ward, ICU and deaths, coupling between neighborhoods, ensembles and sensitivity runs, mobility-driven transmission, and an equity module that weights access by social vulnerability. It is calibrated to Massachusetts COVID-19 data. See [seir/README.md](seir/README.md).

### The website (optional)

A SvelteKit site over both models, served by a small FastAPI app. It needs Node 20+ as well as Python:

```bash
pip install -r requirements.txt -r seir/requirements.txt -r frontend/api/requirements.txt
npm --prefix frontend/web install
uvicorn main:app --app-dir frontend/api --port 8000      # terminal 1
npm --prefix frontend/web run dev                        # terminal 2, then open http://localhost:5173
```

Details in [frontend/README.md](frontend/README.md).

<details>
<summary>Developer commands</summary>

```bash
python -m pytest                              # automated tests
ruff check . && ruff format --check .         # lint and format
PYTHONPATH=. python scripts/smoke_demo.py     # offline smoke run
PYTHONPATH=. python scripts/verify_demo.py    # checks the worked example in docs
PYTHONPATH=. python scripts/run_backtest.py   # historical backtest
PYTHONPATH=. python scripts/benchmark.py      # timing and memory
```

On Windows PowerShell, set the variable first: `$env:PYTHONPATH="."`.

</details>

## Built with Kiro

ResiliNet was built in the Kiro IDE, with five to six agents working in parallel on separate parts of the pipeline, and the Fetch, GitHub, Context7, and Exa MCP servers for pulling sources, repository work, library documentation, and research.

| Path | What it is |
|---|---|
| [.kiro/steering/](.kiro/steering/) | Steering files: product goal, folder layout, technology choices, modeling guardrails |
| [.kiro/specs/epidemic-hospital-mvp/](.kiro/specs/epidemic-hospital-mvp/) | The first spec: requirements, design, tasks (later superseded by the reconciled documents below) |
| [AGENTS.md](AGENTS.md) | Rules for every agent and the split into workstreams with file ownership |
| [docs/agent-prompts/](docs/agent-prompts/README.md) | One implementation prompt per workstream |
| [architecture.md](architecture.md), [docs/architecture-decisions.md](docs/architecture-decisions.md) | The reconciled specification and the decision log |

## Team

- Valery (Vlarkus) Rabchanka
- Ansar Samatov
- David Safro
- Benjamin Gershenovich
- Andy

Thanks to BU Spark!, the Mass AI Coalition, Sundai, and Kiro, and to MassGIS and the U.S. Department of Health and Human Services for the public data.
