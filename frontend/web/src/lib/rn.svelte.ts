// Shared state for the ResiliNet weekly pages: settings, events, the latest run and what is selected.
import { heatColor } from './colors';
import {
	rnApi,
	type Dataset,
	type Evaluation,
	type MitigateResult,
	type ParamKey,
	type Phase,
	type RnDistrict,
	type RnEvent,
	type RnGeo,
	type RnMeta,
	type RnRequest,
	type RnRun,
	type Suggestion,
	type WeekView
} from './rn-api';

// The Streamlit app's defaults, used until /api/rn/meta answers.
const DEFAULTS: Record<ParamKey, number> = {
	r0: 2.6,
	p_h: 0.03,
	seed: 0.003,
	d0: 3,
	alpha_d: 0.9,
	alpha_h: 0.1,
	weeks: 8
};

class RnState {
	meta = $state<RnMeta | null>(null);
	dataset = $state<Dataset>('real');
	params = $state<Record<ParamKey, number>>({ ...DEFAULTS });
	fallback = $state(true);
	events = $state<RnEvent[]>([]);
	notice = $state<string | null>(null);

	result = $state<RnRun | null>(null);
	geo = $state<Partial<Record<Dataset, RnGeo>>>({});
	loading = $state(false);
	error = $state<string | null>(null);

	week = $state(0);
	phase = $state<Phase>('after');
	selectedHospital = $state<string | null>(null);
	selectedDistrict = $state<string | null>(null);
	ejOverlay = $state(false);
	controlsOpen = $state(false);

	evaluation = $state<Evaluation | null>(null);
	evalError = $state<string | null>(null);

	/** "What would help": fixes tried on the current scenario, or null until asked for. */
	suggestions = $state<MitigateResult | null>(null);
	suggesting = $state(false);
	suggestError = $state<string | null>(null);

	#abort: AbortController | null = null;
	#timer: ReturnType<typeof setTimeout> | null = null;
	#nextId = 1;
	#evalStarted = false;
	#suggestAbort: AbortController | null = null;
	#suggestKey = '';

	get nWeeks() {
		return this.result?.weeks ?? 0;
	}
	get view(): WeekView | null {
		return this.result?.scenario[this.week]?.[this.phase] ?? null;
	}
	/** The same week and phase with no events: the scenario itself when there are none. */
	get baseView(): WeekView | null {
		const b = this.result?.baseline;
		return b ? (b[this.week]?.[this.phase] ?? null) : this.view;
	}
	get hasBaseline() {
		return !!this.result?.baseline;
	}
	get datasetInfo() {
		return this.meta?.datasets.find((d) => d.id === this.dataset) ?? null;
	}
	get defaults(): Record<ParamKey, number> {
		const p = this.meta?.params;
		return p ? (Object.fromEntries(Object.entries(p).map(([k, v]) => [k, v.default])) as Record<ParamKey, number>) : DEFAULTS;
	}
	get changeCount() {
		const d = this.defaults;
		return (
			(Object.keys(d) as ParamKey[]).filter((k) => Math.abs(this.params[k] - d[k]) > 1e-9).length +
			this.events.length +
			(this.fallback !== (this.dataset === 'real') ? 1 : 0)
		);
	}

	request(): RnRequest {
		return { dataset: this.dataset, fallback: this.fallback, ...this.params, events: $state.snapshot(this.events) };
	}

	async init() {
		this.meta = await rnApi.meta();
		if (!this.meta.datasets.some((d) => d.id === this.dataset)) this.dataset = this.meta.datasets[0].id;
		this.params = { ...this.defaults };
		this.fallback = this.dataset === 'real';
		await Promise.all([this.run(), this.loadGeo(this.dataset)]);
		if (this.result) this.week = Math.min(this.result.weeks - 1, Math.floor(this.result.weeks / 2));
		// Warm the backtest so the "Tested on real data" page is ready when opened.
		this.loadEvaluation();
	}

	async loadGeo(d: Dataset) {
		if (this.geo[d]) return;
		const g = await rnApi.geo(d);
		this.geo = { ...this.geo, [d]: g };
	}

	loadEvaluation() {
		if (this.#evalStarted) return;
		this.#evalStarted = true;
		rnApi
			.evaluation()
			.then((e) => (this.evaluation = e))
			.catch((e) => {
				this.evalError = (e as Error).message;
				this.#evalStarted = false;
			});
	}

	setParam(k: ParamKey, v: number) {
		this.params = { ...this.params, [k]: v };
		if (k === 'weeks') this.#fitEvents(Math.round(v));
		this.schedule();
	}

	setFallback(v: boolean) {
		this.fallback = v;
		this.schedule(0);
	}

	setDataset(d: Dataset) {
		if (d === this.dataset) return;
		this.dataset = d;
		this.fallback = d === 'real';
		if (this.events.length) this.notice = 'Your events were removed: the hospitals differ in this dataset.';
		this.events = [];
		this.selectedDistrict = null;
		this.selectedHospital = null;
		this.loadGeo(d).catch((e) => (this.error = (e as Error).message));
		this.schedule(0);
	}

	/** Drop events that start after the horizon and trim the rest to it. */
	#fitEvents(weeks: number) {
		const kept = this.events
			.filter((e) => e.start_week < weeks)
			.map((e) => (e.end_week !== null && e.end_week > weeks ? { ...e, end_week: weeks } : e));
		if (kept.length !== this.events.length) this.notice = 'Events that start after the last week were removed.';
		this.events = kept;
	}

	/** Add an event and rerun; if the engine rejects it, take it back and say why. */
	async addEvent(e: Omit<RnEvent, 'id'>) {
		const before = this.events;
		this.events = [...before, { ...e, id: `e${this.#nextId++}` }];
		this.notice = null;
		await this.run();
		if (this.error) {
			this.notice = `That event can't be added: ${this.error}`;
			this.events = before;
			this.error = null;
			await this.run();
		}
	}

	removeEvent(id: string) {
		this.events = this.events.filter((e) => e.id !== id);
		this.schedule(0);
	}

	reset() {
		this.params = { ...this.defaults };
		this.fallback = this.dataset === 'real';
		this.events = [];
		this.notice = null;
		this.schedule(0);
	}

	schedule(delay = 250) {
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.run(), delay);
	}

	async run() {
		this.#abort?.abort();
		const ctrl = new AbortController();
		this.#abort = ctrl;
		this.loading = true;
		try {
			const res = await rnApi.run(this.request(), ctrl.signal);
			this.result = res;
			this.error = null;
			this.week = Math.min(this.week, res.weeks - 1);
			if (this.selectedHospital && !res.hospitals.some((h) => h.id === this.selectedHospital)) this.selectedHospital = null;
			if (this.selectedDistrict && !res.districts.some((d) => d.id === this.selectedDistrict)) this.selectedDistrict = null;
			// suggestions belong to the scenario they were worked out for
			if (this.suggestions && JSON.stringify(this.request()) !== this.#suggestKey) this.suggestions = null;
		} catch (e) {
			if ((e as Error).name !== 'AbortError') this.error = (e as Error).message;
		} finally {
			if (this.#abort === ctrl) this.loading = false;
		}
	}

	/** Try a few fixes on the current scenario (a few seconds: each one is a full rerun). */
	async suggest() {
		this.#suggestAbort?.abort();
		const ctrl = new AbortController();
		this.#suggestAbort = ctrl;
		const req = this.request();
		const key = JSON.stringify(req);
		this.suggesting = true;
		this.suggestError = null;
		try {
			const res = await rnApi.mitigate(req, ctrl.signal);
			if (JSON.stringify(this.request()) !== key) return; // the scenario changed meanwhile
			this.#suggestKey = key;
			this.suggestions = res;
		} catch (e) {
			if ((e as Error).name !== 'AbortError') this.suggestError = (e as Error).message;
		} finally {
			if (this.#suggestAbort === ctrl) this.suggesting = false;
		}
	}

	/** Make a suggestion part of the scenario, then rerun. */
	async applySuggestion(s: Suggestion) {
		const a = s.apply;
		this.suggestions = null;
		if (a.type === 'add_event') {
			const { id: _id, ...e } = a.event;
			await this.addEvent(e);
		} else if (a.type === 'param') {
			this.setParam(a.key, a.value);
		} else if (a.type === 'edit_event') {
			this.events = this.events.map((e) => (e.id === a.id ? { ...e, end_week: a.end_week } : e));
			this.schedule(0);
		} else {
			this.removeEvent(a.id);
		}
	}

	download(name: string) {
		return rnApi.download(name, this.request());
	}

	hospitalName(id: string, short = true) {
		const h = this.result?.hospitals.find((x) => x.id === id);
		if (!short) return h?.name ?? id;
		return SHORT[id] ?? id;
	}
	districtIndex(id: string | null) {
		return id ? (this.result?.districts.findIndex((d) => d.id === id) ?? -1) : -1;
	}
}

// Short names for the real hospitals, where the full MassGIS name won't fit a label.
const SHORT: Record<string, string> = {
	BIDMC_E: 'BIDMC East',
	BIDMC_W: 'BIDMC West',
	BMC_BRIGHTON: 'BMC Brighton',
	BMC_MENINO: 'BMC Menino',
	BWH: 'Brigham',
	FAULKNER: 'Faulkner',
	MGH: 'Mass General',
	NEBAPTIST: 'NE Baptist',
	TUFTS: 'Tufts'
};

export function tractLabel(d: RnDistrict | undefined | null): string {
	if (!d) return '–';
	return d.area ? `${d.area} · ${d.name.replace('Tract ', 'tract ')}` : d.name;
}

/** "Close" / "Cut to 60% of beds:" / "Add 25% beds:" and "weeks 3–8" for an event (weeks shown 1-based). */
export function describeEvent(e: RnEvent, nWeeks: number) {
	const f = e.factor ?? 0.6;
	const what =
		e.kind === 'close_hospital' ? 'Close' : f > 1 ? `Add ${Math.round((f - 1) * 100)}% beds:` : `Cut to ${Math.round(f * 100)}% of beds:`;
	const end = e.end_week ?? nWeeks;
	const when = e.start_week + 1 === end ? `week ${end}` : `weeks ${e.start_week + 1}–${end}`;
	return { what, when };
}

/** A suggestion in words: what to change, and the detail behind it. */
export function describeSuggestion(s: Suggestion, nWeeks: number): { title: string; detail: string } {
	const name = s.hospital_id ? rn.hospitalName(s.hospital_id) : '';
	switch (s.kind) {
		case 'surge_beds':
			return {
				title: `Add ${Math.round(((s.factor ?? 1) - 1) * 100)}% beds at ${name} from week ${(s.start_week ?? 0) + 1}`,
				detail: `${s.beds_added} extra beds. Each 100 of them get ${Math.round(s.per_100_beds ?? 0)} more people a bed over the run.`
			};
		case 'slow_spread':
			return {
				title: `Slow the spread by ${Math.round((s.cut ?? 0) * 100)}%`,
				detail: `R0 from ${s.r0_from} to ${s.r0_to}, as distancing, masks or vaccination might.`
			};
		case 'shorten_closure': {
			const ev = rn.events.find((e) => e.id === s.event_id);
			const was = (ev?.end_week ?? nWeeks) - (s.start_week ?? 0);
			const now = (s.end_week ?? 0) - (s.start_week ?? 0);
			return {
				title: `Reopen ${name} from week ${(s.end_week ?? 0) + 1}`,
				detail: `Closed for ${now} weeks instead of ${was}.`
			};
		}
		case 'cancel_closure':
			return { title: `Keep ${name} open`, detail: 'Drop your closure of this hospital.' };
		case 'restore_beds':
			return {
				title: `Give ${name} its beds back`,
				detail: `Undo your cut to ${Math.round((s.factor ?? 0) * 100)}% of its beds.`
			};
	}
}

export function weekLabel(i: number) {
	return `Week ${i + 1}`;
}

/** Access and network scores, 0-100, on one fixed scale: 100 recedes, low scores glow. */
export function scoreColor(score: number | null | undefined): string {
	if (score === null || score === undefined || !Number.isFinite(score)) return '#3a3a40';
	return heatColor(0.06 + 0.9 * (1 - Math.max(0, Math.min(100, score)) / 100));
}

export const rn = new RnState();
