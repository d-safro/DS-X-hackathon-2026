// Typed client for the ResiliNet weekly pipeline (frontend/api/resilinet.py, /api/rn/*).
import type * as GeoJSON from 'geojson';

export type Dataset = 'real' | 'synthetic' | 'golden';
export type Phase = 'after' | 'before';

export interface ParamRange {
	min: number;
	max: number;
	step: number;
	default: number;
}
export type ParamKey = 'r0' | 'p_h' | 'seed' | 'd0' | 'alpha_d' | 'alpha_h' | 'weeks';

export interface RnMeta {
	datasets: { id: Dataset; title: string; mode: string; label: string; synthetic: boolean }[];
	params: Record<ParamKey, ParamRange>;
	threshold: number;
	radius_km: number;
	events: { kind: EventKind; label: string; factor?: number }[];
}

export type EventKind = 'close_hospital' | 'set_capacity';
export interface RnEvent {
	id: string;
	kind: EventKind;
	hospital_id: string;
	start_week: number;
	/** exclusive, like the engine; null runs to the end */
	end_week: number | null;
	factor?: number | null;
}

export interface RnRequest extends Record<ParamKey, number> {
	dataset: Dataset;
	fallback: boolean;
	events: RnEvent[];
}

export interface RnHospital {
	id: string;
	name: string;
	lat: number;
	lon: number;
	beds: number;
	icu: number;
}

export interface RnDistrict {
	id: string;
	name: string;
	area: string;
	population: number;
	risk: number;
	ej: boolean | null;
	lat: number;
	lon: number;
	access_index: number;
	catchment: { id: string; km: number; share: number }[];
}

export interface HospitalWeek {
	id: string;
	baseline: number;
	retained: number;
	request: number;
	load: number;
	capacity: number;
	committed: number;
	accepted: number;
	deficit: number;
	own: number;
	score: number;
	excess: number;
	closed: boolean;
}

export interface Metrics {
	overloaded_hospitals: number;
	unmet_need_people: number;
	rerouted_people: number;
	inherited_deficit_beds: number;
	districts_below_threshold: number;
}

export interface Reroute {
	district: string;
	from: string;
	to: string;
	amount: number;
}

export interface WeekView {
	metrics: Metrics;
	hospitals: HospitalWeek[];
	/** per district, in the order of RnRun.districts */
	access: number[];
	need: number[];
	unmet: number[];
	reroutes: Reroute[];
	events: string[];
	checks: Record<string, boolean>;
}

export type Weeks = { before: WeekView; after: WeekView }[];

export interface RnRun {
	run_id: string;
	base_run_id: string;
	dataset: Dataset;
	data_mode: string;
	mode: string;
	mode_label: string;
	synthetic: boolean;
	threshold: number;
	weeks: number;
	warnings: string[];
	fallback_districts: string[];
	manifest: Record<string, unknown>;
	hospitals: RnHospital[];
	districts: RnDistrict[];
	epi: { new_infections: number[]; need: number[]; infectious: number[]; susceptible: number[] };
	scenario: Weeks;
	baseline: Weeks | null;
}

export type RnGeo = GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, { district_id: string }>;

export interface ForecastRow {
	ccn: string;
	origin: string;
	target: string;
	model: number;
	observed: number;
	persistence: number;
	fitted_r0?: number;
}

export interface Strategy {
	strategy: string;
	status?: string;
	forecast_pairs: number;
	model_mae_beds: number;
	persistence_mae_beds: number;
	rows: ForecastRow[];
	leakage_free?: boolean;
	observation_operator?: string;
	regional_model_mae_beds?: number;
	regional_persistence_mae_beds?: number;
	per_facility?: Record<string, { n: number; model_mae: number; persistence_mae: number }>;
	fit?: { fitted_r0: number; train_mae_beds: number; seed_frac: number; p_h_fixed: number };
}

export interface Evaluation {
	status: 'verified' | 'unavailable' | string;
	reason?: string;
	source_url?: string;
	period?: [string, string];
	calendar_weeks?: number;
	train_weeks?: number;
	holdout_weeks?: number;
	matched_facilities?: number;
	min_coverage_days?: number;
	excluded_records?: number;
	honest_note?: string;
	fixed_origin?: Strategy;
	rolling_origin?: Strategy;
	facilities?: Record<string, { hospitals: string[]; names: string[]; name: string }>;
}

export type SuggestionKind = 'surge_beds' | 'slow_spread' | 'shorten_closure' | 'cancel_closure' | 'restore_beds';
export type SuggestionApply =
	| { type: 'add_event'; event: RnEvent }
	| { type: 'param'; key: ParamKey; value: number }
	| { type: 'edit_event'; id: string; end_week: number }
	| { type: 'remove_event'; id: string };

/** One fix, already run through the model: the user's scenario plus this one change. */
export interface Suggestion {
	id: string;
	kind: SuggestionKind;
	hospital_id?: string;
	event_id?: string;
	factor?: number | null;
	start_week?: number;
	end_week?: number;
	beds_added?: number;
	r0_from?: number;
	r0_to?: number;
	cut?: number;
	/** totals over every simulated week, after rerouting */
	people_helped: number;
	tract_weeks_fixed: number;
	unmet_after: number;
	poor_after: number;
	per_100_beds: number | null;
	apply: SuggestionApply;
}

export interface MitigateResult {
	current: { unmet: number; poor_tract_weeks: number; peak_week: number; start_week: number | null };
	suggestions: Suggestion[];
	tried: number;
	seconds: number;
	status: 'ok' | 'nothing_to_fix' | 'none_helped';
}

async function call<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
	const res = await fetch(`/api/rn/${path}`, {
		method: body === undefined ? 'GET' : 'POST',
		headers: body === undefined ? undefined : { 'content-type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body),
		signal
	});
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const j = await res.json();
			detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
		} catch {
			/* keep statusText */
		}
		throw new Error(detail);
	}
	return res.json() as Promise<T>;
}

export const rnApi = {
	meta: () => call<RnMeta>('meta'),
	geo: (d: Dataset) => call<RnGeo>(`geo/${d}`),
	run: (r: RnRequest, signal?: AbortSignal) => call<RnRun>('run', r, signal),
	mitigate: (r: RnRequest, signal?: AbortSignal) => call<MitigateResult>('mitigate', r, signal),
	evaluation: () => call<Evaluation>('evaluation'),
	async download(name: string, r: RnRequest) {
		const res = await fetch(`/api/rn/export/${name}`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(r)
		});
		if (!res.ok) throw new Error(res.statusText);
		const url = URL.createObjectURL(await res.blob());
		const a = document.createElement('a');
		a.href = url;
		a.download = name;
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
};
