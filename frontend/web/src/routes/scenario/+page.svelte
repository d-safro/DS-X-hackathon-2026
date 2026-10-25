<script lang="ts">
	import { rn, tractLabel, weekLabel } from '#lib/rn.svelte.ts';
	import { num, fixed } from '#lib/format.ts';
	import type { Metrics } from '#lib/rn-api.ts';
	import Card from '#lib/components/Card.svelte';
	import LineChart from '#lib/components/LineChart.svelte';
	import More from '#lib/components/More.svelte';
	import RnEvents from '#lib/components/RnEvents.svelte';
	import RnSuggestions from '#lib/components/RnSuggestions.svelte';

	const r = $derived(rn.result!);
	const v = $derived(rn.view!);
	const b = $derived(rn.baseView!);
	const wk = $derived(r.scenario[rn.week]);
	const labels = $derived(r.scenario.map((_, i) => `W${i + 1}`));
	const has = $derived(rn.hasBaseline);
	const phaseWord = $derived(rn.phase === 'after' ? 'after rerouting' : 'before rerouting');

	const ROWS: { key: keyof Metrics; label: string; unit: string; digits: number }[] = [
		{ key: 'overloaded_hospitals', label: 'Hospitals over capacity', unit: 'hospitals', digits: 0 },
		{ key: 'unmet_need_people', label: "Can't get a bed", unit: 'people/week', digits: 0 },
		{ key: 'rerouted_people', label: 'Sent to another hospital', unit: 'people/week', digits: 0 },
		{ key: 'inherited_deficit_beds', label: 'Stranded by a closure', unit: 'patients', digits: 0 },
		{ key: 'districts_below_threshold', label: 'Tracts with poor access', unit: 'tracts', digits: 0 }
	];
	const change = (a: number, c: number) => {
		const d = c - a;
		return Math.abs(d) < 0.5 ? '–' : `${d > 0 ? '+' : '−'}${num(Math.abs(d))}`;
	};

	// Tracts whose access fell most against the no-events run, same week and phase.
	const hardest = $derived(
		r.districts
			.map((d, i) => ({ d, now: v.access[i], base: b.access[i], drop: b.access[i] - v.access[i] }))
			.filter((x) => (has ? x.drop > 0.05 : true))
			.sort((a, c) => (has ? c.drop - a.drop : a.now - c.now))
			.slice(0, 6)
	);
	const hospitalChanges = $derived(
		v.hospitals
			.map((h) => {
				const base = b.hospitals.find((x) => x.id === h.id)!;
				return { id: h.id, closed: h.closed, load: h.load, baseLoad: base.load, score: h.score, baseScore: base.score };
			})
			.sort((a, c) => Math.abs(c.load - c.baseLoad) - Math.abs(a.load - a.baseLoad))
	);

	// Reroute ledger: totals by sending and receiving hospital, then every tract-level move.
	const moves = $derived(rn.phase === 'after' ? v.reroutes : []);
	const flows = $derived.by(() => {
		const acc = new Map<string, { from: string; to: string; amount: number; tracts: number }>();
		for (const m of moves) {
			const k = `${m.from}>${m.to}`;
			const f = acc.get(k) ?? { from: m.from, to: m.to, amount: 0, tracts: 0 };
			f.amount += m.amount;
			f.tracts += 1;
			acc.set(k, f);
		}
		return [...acc.values()].sort((a, c) => c.amount - a.amount);
	});
	const maxFlow = $derived(Math.max(1e-9, ...flows.map((f) => f.amount)));
	const districtById = $derived(new Map(r.districts.map((d) => [d.id, d])));
</script>

<div class="page">
	<div class="page-head">
		<h1>Scenario lab</h1>
		<p>
			Close a hospital or cut its beds for some weeks, then compare with the same weeks when nothing goes wrong. Both runs
			share every other setting, and the compare uses the view you picked below ({phaseWord}). <b>What would help</b>
			tries a few fixes and ranks them.
		</p>
	</div>

	<div class="grid-2">
		<Card title="Your events" sub="Weeks are inclusive. Changes rerun the model.">
			<RnEvents compact />
		</Card>

		<Card title="{weekLabel(rn.week)}: with your events vs with none" sub={has ? `Same week, ${phaseWord}` : 'Add an event to see a comparison'}>
			<table class="cmp">
				<thead><tr><th></th><th>No events</th><th>With events</th><th>Change</th></tr></thead>
				<tbody>
					{#each ROWS as row (row.key)}
						<tr>
							<td>{row.label} <small>{row.unit}</small></td>
							<td>{num(b.metrics[row.key])}</td>
							<td>{has ? num(v.metrics[row.key]) : '–'}</td>
							<td class:bad={has && v.metrics[row.key] - b.metrics[row.key] >= 0.5 && row.key !== 'rerouted_people'}>
								{has ? change(b.metrics[row.key], v.metrics[row.key]) : '–'}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="muted small">"Sent to another hospital" counts patients moved, not patients helped. Poor access means a score under {r.threshold}.</p>
		</Card>
	</div>

	<div id="help">
		<Card title="What would help" sub="Each idea is run through the model on top of your scenario. Ranked by how many more people get a bed over the whole run.">
			<RnSuggestions />
		</Card>
	</div>

	<Card title="{weekLabel(rn.week)}: before and after rerouting" sub="Before: each hospital takes the new patients it has room for. After: patients who didn't fit are moved to hospitals with spare beds.">
		<table class="cmp">
			<thead><tr><th></th><th>Before rerouting</th><th>After rerouting</th><th>Change</th></tr></thead>
			<tbody>
				{#each ROWS as row (row.key)}
					<tr>
						<td>{row.label} <small>{row.unit}</small></td>
						<td>{num(wk.before.metrics[row.key])}</td>
						<td>{num(wk.after.metrics[row.key])}</td>
						<td>{change(wk.before.metrics[row.key], wk.after.metrics[row.key])}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#if wk.after.metrics.rerouted_people < 0.5}
			<p class="muted small">Nothing moved this week, so before and after are the same by construction.</p>
		{/if}
	</Card>

	<div class="grid-2">
		<Card title="Can't get a bed, week by week" sub="People per week, {phaseWord}">
			<LineChart
				{labels}
				height={210}
				marker={rn.week}
				onscrub={(i) => (rn.week = i)}
				series={[
					...(r.baseline ? [{ id: 'base', label: 'No events', values: r.baseline.map((w) => w[rn.phase].metrics.unmet_need_people), color: '#898781', dashed: true }] : []),
					{ id: 'scn', label: r.baseline ? 'With your events' : "Can't get a bed", values: r.scenario.map((w) => w[rn.phase].metrics.unmet_need_people), color: '#d03b3b' }
				]}
			/>
		</Card>
		<Card title="Tracts with poor access, week by week" sub="Access score under {r.threshold}, {phaseWord}">
			<LineChart
				{labels}
				height={210}
				marker={rn.week}
				onscrub={(i) => (rn.week = i)}
				yMin={0}
				series={[
					...(r.baseline ? [{ id: 'base', label: 'No events', values: r.baseline.map((w) => w[rn.phase].metrics.districts_below_threshold), color: '#898781', dashed: true }] : []),
					{ id: 'scn', label: r.baseline ? 'With your events' : 'Tracts', values: r.scenario.map((w) => w[rn.phase].metrics.districts_below_threshold), color: '#d95926' }
				]}
			/>
		</Card>
	</div>

	<div class="grid-2">
		<Card title={has ? 'Hardest-hit tracts' : 'Lowest access tracts'} sub={has ? 'Biggest drop in access score against no events, this week' : 'This week. Add an event to rank by how much each tract loses.'}>
			{#if hardest.length}
				<table class="cmp">
					<thead><tr><th>Tract</th>{#if has}<th>No events</th>{/if}<th>{has ? 'With events' : 'Access'}</th>{#if has}<th>Drop</th>{/if}</tr></thead>
					<tbody>
						{#each hardest as x (x.d.id)}
							<tr class="click" onclick={() => (rn.selectedDistrict = x.d.id)}>
								<td><a href="/tracts">{tractLabel(x.d)}</a></td>
								{#if has}<td>{fixed(x.base, 1)}</td>{/if}
								<td class:bad={x.now < r.threshold}>{fixed(x.now, 1)}</td>
								{#if has}<td class="bad">−{fixed(x.drop, 1)}</td>{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			{:else}
				<p class="empty">No tract loses access this week.</p>
			{/if}
		</Card>
		<Card title="Hospitals" sub={has ? 'Patients wanting a bed and score, against no events' : 'Patients wanting a bed and score this week'}>
			<table class="cmp">
				<thead><tr><th>Hospital</th>{#if has}<th>No events</th>{/if}<th>Wanting a bed</th>{#if has}<th>Change</th>{/if}<th>Score</th></tr></thead>
				<tbody>
					{#each hospitalChanges as h (h.id)}
						<tr>
							<td>{rn.hospitalName(h.id)}</td>
							{#if has}<td>{num(h.baseLoad)}</td>{/if}
							<td>{h.closed ? 'closed' : num(h.load)}</td>
							{#if has}<td>{change(h.baseLoad, h.load)}</td>{/if}
							<td class:bad={h.score < r.threshold}>{fixed(h.score, 0)}{#if has && Math.abs(h.score - h.baseScore) >= 0.5}<small>&nbsp;({change(h.baseScore, h.score)})</small>{/if}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="muted small">A closed hospital's existing patients don't vanish: they count as stranded until they leave.</p>
		</Card>
	</div>

	<Card title="Where rerouted patients went, {weekLabel(rn.week).toLowerCase()}" sub="New patients moved from a full hospital to one with spare beds. A ledger, not a road route.">
		{#if flows.length}
			<div class="flows">
				{#each flows as f (f.from + f.to)}
					<div class="flow">
						<span class="fn">{rn.hospitalName(f.from)}</span>
						<span class="arrow">→</span>
						<span class="fn">{rn.hospitalName(f.to)}</span>
						<span class="ftrack"><span style:width="{(f.amount / maxFlow) * 100}%"></span></span>
						<span class="fv">{fixed(f.amount, 1)} <small>from {f.tracts} tract{f.tracts > 1 ? 's' : ''}</small></span>
					</div>
				{/each}
			</div>
		{:else if rn.phase === 'before'}
			<p class="empty">Rerouting happens in the "after" view. Switch to After rerouting below.</p>
		{:else if v.metrics.unmet_need_people < 1e-6}
			<p class="empty">No rerouting needed: every new patient got a bed at a usual hospital this week.</p>
		{:else}
			<p class="empty">
				No rerouting happened: patients were left without a bed, but no reachable hospital had spare beds to take them. With
				nothing moved, before and after are the same.
			</p>
		{/if}
	</Card>

	{#if moves.length}
		<More title="Every move, tract by tract" sub="{moves.length} moves in {weekLabel(rn.week).toLowerCase()}">
			<div class="ledger">
				<table class="cmp">
					<thead><tr><th>Tract</th><th>From</th><th>To</th><th>People</th></tr></thead>
					<tbody>
						{#each [...moves].sort((a, c) => c.amount - a.amount) as m, i (i)}
							<tr>
								<td>{tractLabel(districtById.get(m.district))}</td>
								<td>{rn.hospitalName(m.from)}</td>
								<td>{rn.hospitalName(m.to)}</td>
								<td>{fixed(m.amount, 2)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</More>
	{/if}
</div>

<style>
	.cmp {
		width: 100%;
		border-collapse: collapse;
		font-size: 12.5px;
		font-variant-numeric: tabular-nums;
	}
	.cmp th,
	.cmp td {
		padding: 6px 8px;
		border-bottom: 1px solid var(--line);
		text-align: right;
		white-space: nowrap;
	}
	.cmp th:first-child,
	.cmp td:first-child {
		text-align: left;
		white-space: normal;
	}
	.cmp th {
		color: var(--text-3);
		font-weight: 500;
	}
	.cmp td {
		color: var(--text-2);
	}
	.cmp td:first-child {
		color: var(--text-1);
	}
	.cmp small {
		color: var(--text-3);
		font-size: 11px;
	}
	.cmp a {
		color: inherit;
		text-decoration: none;
	}
	.cmp tr.click {
		cursor: pointer;
	}
	.cmp tr.click:hover {
		background: var(--hover);
	}
	.bad {
		color: #ff8a8a !important;
	}
	.small {
		font-size: 11.5px;
		line-height: 1.5;
		margin: 10px 0 0;
	}
	.flows {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.flow {
		display: grid;
		grid-template-columns: 100px 16px 100px 1fr 150px;
		gap: 10px;
		align-items: center;
		font-size: 12.5px;
	}
	.fn {
		color: var(--text-2);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.arrow {
		color: var(--text-3);
	}
	.ftrack {
		height: 6px;
		background: var(--line);
		border-radius: 3px;
		overflow: hidden;
	}
	.ftrack span {
		display: block;
		height: 100%;
		background: #3987e5;
		border-radius: 3px;
	}
	.fv {
		text-align: right;
		font-family: var(--mono);
		font-size: 12px;
		color: var(--text-1);
	}
	.fv small {
		font-family: var(--sans);
		color: var(--text-3);
	}
	.ledger {
		max-height: 420px;
		overflow-y: auto;
	}
	.empty {
		padding: 16px 0;
		text-align: left;
		line-height: 1.5;
	}
	@media (max-width: 700px) {
		.cmp th,
		.cmp td {
			padding: 6px 4px;
			white-space: normal;
		}
		.cmp small {
			display: block;
		}
		.flow {
			grid-template-columns: 1fr 14px 1fr;
			row-gap: 2px;
		}
		.ftrack {
			grid-column: 1 / 3;
		}
	}
</style>
