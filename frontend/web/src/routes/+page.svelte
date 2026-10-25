<script lang="ts">
	import { rn, describeSuggestion, scoreColor, tractLabel, weekLabel } from '#lib/rn.svelte.ts';
	import { num, fixed, pct } from '#lib/format.ts';
	import RnMap from '#lib/components/RnMap.svelte';
	import Icon from '#lib/components/Icon.svelte';

	const r = $derived(rn.result!);
	const v = $derived(rn.view!);
	const b = $derived(rn.baseView!);
	const m = $derived(v.metrics);
	const after = $derived(rn.phase === 'after');
	const nTracts = $derived(r.districts.length);
	const need = $derived(v.need.reduce((a, x) => a + (x ?? 0), 0));

	// any week, after rerouting, where someone goes without a bed or a tract has poor access
	const troubled = $derived(
		r.scenario.some((w) => w.after.metrics.unmet_need_people >= 0.5 || w.after.metrics.districts_below_threshold > 0)
	);
	const topFix = $derived(rn.suggestions?.suggestions[0] ?? null);

	const hospitals = $derived(
		v.hospitals
			.map((h) => ({ ...h, full: h.capacity > 0 ? h.load / h.capacity : Infinity }))
			.sort((a, c) => c.full - a.full)
	);

	function delta(now: number, base: number, digits = 0) {
		if (!rn.hasBaseline) return '';
		const d = now - base;
		if (Math.abs(d) < 0.5 * 10 ** -digits) return 'unchanged by events';
		return `${d > 0 ? '+' : '−'}${fixed(Math.abs(d), digits)} vs no events`;
	}

	const tract = $derived.by(() => {
		const i = rn.districtIndex(rn.selectedDistrict);
		if (i < 0) return null;
		return { d: r.districts[i], score: v.access[i], need: v.need[i], unmet: v.unmet[i], base: b.access[i] };
	});
	const hosp = $derived.by(() => {
		if (!rn.selectedHospital) return null;
		const w = v.hospitals.find((h) => h.id === rn.selectedHospital);
		const h = r.hospitals.find((x) => x.id === rn.selectedHospital);
		return w && h ? { h, w } : null;
	});
</script>

<div class="mappage">
	<div class="mapcol">
		{#if rn.geo[r.dataset]}
			<RnMap />
		{:else}
			<div class="nomap"><span class="spin"></span> Loading tract outlines…</div>
		{/if}
	</div>

	<aside class="side">
		<div class="when">
			<div class="d">{weekLabel(rn.week)}</div>
			<div class="muted">of {r.weeks} · {after ? 'after sending patients elsewhere' : 'before any rerouting'}</div>
		</div>

		<p class="story">
			This week <b>{num(need)}</b> people need a hospital bed.
			{#if m.overloaded_hospitals}
				<b class="bad">{m.overloaded_hospitals} of {r.hospitals.length} hospitals</b> have more patients than beds{#if after && m.rerouted_people > 0.5}, so <b>{num(m.rerouted_people)}</b> are sent to a hospital with room{/if}.
			{:else}
				Every hospital has room.
			{/if}
			{#if m.unmet_need_people >= 0.5}<b class="bad">{num(m.unmet_need_people)}</b> can't get a bed nearby.{/if}
			{#if m.districts_below_threshold}
				{m.districts_below_threshold} of {nTracts} tracts have poor access (a score under {r.threshold}).
			{/if}
		</p>

		<div class="big">
			<div class="b" title="Hospitals asked for more beds than they have this week">
				<span>Hospitals over capacity</span>
				<b class:bad={m.overloaded_hospitals > 0}>{m.overloaded_hospitals} of {r.hospitals.length}</b>
				<small>{delta(m.overloaded_hospitals, b.metrics.overloaded_hospitals)}</small>
			</div>
			<div class="b" title="New patients this week with no bed at any hospital they could reach. People per week, not beds.">
				<span>Can't get a bed</span>
				<b class:bad={m.unmet_need_people >= 0.5}>{num(m.unmet_need_people)}</b>
				<small>{delta(m.unmet_need_people, b.metrics.unmet_need_people) || 'people this week'}</small>
			</div>
			<div class="b" title="New patients moved to a hospital with spare beds. Only happens after rerouting.">
				<span>Sent elsewhere</span>
				<b>{after ? num(m.rerouted_people) : '0'}</b>
				<small>{after ? 'people this week' : 'none before rerouting'}</small>
			</div>
			<div class="b" title="Tracts whose access score is under {r.threshold}. A display threshold, not a clinical standard.">
				<span>Tracts with poor access</span>
				<b class:bad={m.districts_below_threshold > 0}>{m.districts_below_threshold} of {nTracts}</b>
				<small>{delta(m.districts_below_threshold, b.metrics.districts_below_threshold) || `score under ${r.threshold}`}</small>
			</div>
		</div>

		{#if topFix}
			<a class="fix" href="/scenario#help">
				<Icon name="bulb" size={14} />
				<span
					>Biggest fix the model found: <b>{describeSuggestion(topFix, r.weeks).title}</b>, {num(topFix.people_helped)} more people
					get a bed over the run. See all →</span
				>
			</a>
		{:else if troubled}
			<a class="fix" href="/scenario#help" onclick={() => rn.suggest()}>
				<Icon name="bulb" size={14} />
				<span>What would help? Try a few fixes →</span>
			</a>
		{/if}

		{#if r.fallback_districts.length}
			<p class="note">
				{r.fallback_districts.length === 1 ? 'One tract has' : `${r.fallback_districts.length} tracts have`} no hospital within {rn.meta?.radius_km ?? 10} km, so it uses its nearest one:
				{r.fallback_districts.map((id) => tractLabel(r.districts.find((d) => d.id === id))).join(', ')}.
			</p>
		{/if}

		{#if tract}
			<div class="card">
				<div class="hh">
					<b>{tractLabel(tract.d)}</b>
					<button class="x" onclick={() => (rn.selectedDistrict = null)} aria-label="Close">×</button>
				</div>
				<div class="kv"><span>Access score</span><b><i class="sw" style:background={scoreColor(tract.score)}></i>{fixed(tract.score, 1)}</b></div>
				{#if rn.hasBaseline}<div class="kv"><span>With no events</span><b>{fixed(tract.base, 1)}</b></div>{/if}
				<div class="kv"><span>Need a bed</span><b>{fixed(tract.need, 1)} people/week</b></div>
				<div class="kv"><span>Can't get one</span><b>{fixed(tract.unmet, 1)} people/week</b></div>
				<div class="kv"><span>Residents</span><b>{num(tract.d.population)}</b></div>
				<div class="muted small go">Where its patients go (lines on the map)</div>
				{#each tract.d.catchment as c (c.id)}
					<div class="kv"><span>{rn.hospitalName(c.id)} · {fixed(c.km, 1)} km</span><b>{pct(c.share)}</b></div>
				{/each}
				<a class="link" href="/tracts">Everything about this tract →</a>
			</div>
		{:else if hosp}
			<div class="card">
				<div class="hh">
					<b>{hosp.h.name}</b>
					<button class="x" onclick={() => (rn.selectedHospital = null)} aria-label="Close">×</button>
				</div>
				{#if hosp.w.closed}<div class="kv"><span class="bad">Closed this week</span></div>{/if}
				<div class="kv"><span>Patients wanting a bed</span><b>{num(hosp.w.load)}</b></div>
				<div class="kv"><span>Beds available</span><b>{num(hosp.w.capacity)} of {num(hosp.h.beds)}</b></div>
				{#if hosp.w.excess > 0}<div class="kv"><span>Over capacity by</span><b class="bad">{num(hosp.w.excess)}</b></div>{/if}
				<div class="kv"><span>Score (own / with neighbours)</span><b>{fixed(hosp.w.own, 0)} / {fixed(hosp.w.score, 0)}</b></div>
				<a class="link" href="/hospitals">Week by week →</a>
			</div>
		{/if}

		<div class="block">
			<div class="bh">How full each hospital is</div>
			{#each hospitals as h (h.id)}
				<button class="hrow" class:sel={rn.selectedHospital === h.id} title={r.hospitals.find((x) => x.id === h.id)?.name} onclick={() => (rn.selectedHospital = rn.selectedHospital === h.id ? null : h.id)}>
					<span class="hid">{rn.hospitalName(h.id)}</span>
					<span class="hbar"><span class:over={h.full > 1} style:width="{Math.min(100, (h.closed ? 1 : h.full) * 100)}%"></span></span>
					<span class="hv" class:bad={h.closed || h.full > 1}>{h.closed ? 'closed' : pct(h.full)}</span>
				</button>
			{/each}
			<p class="muted small">Patients wanting a bed as a share of beds. Capacity is licensed beds{r.synthetic ? '' : ', a stand-in for staffed beds'}.</p>
		</div>

		<p class="foot muted">
			{r.synthetic ? 'Synthetic data, for illustration only.' : 'Real Suffolk County tracts and hospitals with a simulated epidemic.'}
			Change the assumptions or close a hospital with <b>What if…?</b> above.
		</p>
	</aside>
</div>

<style>
	.mappage {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 340px;
		height: 100%;
		min-height: 560px;
	}
	.mapcol {
		position: relative;
		min-height: 0;
	}
	.nomap {
		height: 100%;
		display: grid;
		place-items: center;
		color: var(--text-3);
		background: #0e0e10;
	}
	.side {
		border-left: 1px solid var(--line);
		overflow-y: auto;
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.when .d {
		font-size: 19px;
		font-weight: 600;
		letter-spacing: -0.01em;
	}
	.when .muted {
		font-size: 12px;
		margin-top: 2px;
	}
	.fix {
		display: flex;
		gap: 8px;
		align-items: flex-start;
		font-size: 12.5px;
		line-height: 1.5;
		color: var(--text-2);
		text-decoration: none;
		border: 1px solid var(--line-2);
		border-radius: 10px;
		padding: 9px 12px;
		background: rgb(12 163 12 / 0.06);
	}
	.fix:hover {
		background: var(--hover);
		color: var(--text-1);
	}
	.fix :global(svg) {
		flex-shrink: 0;
		margin-top: 2px;
		color: var(--good);
	}
	.fix b {
		color: var(--text-1);
		font-weight: 500;
	}
	.story {
		margin: 0;
		font-size: 13.5px;
		line-height: 1.6;
		color: var(--text-2);
	}
	.story b {
		color: var(--text-1);
		font-weight: 600;
	}
	.bad {
		color: #ff8a8a !important;
	}
	.big {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 10px;
	}
	.b {
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
	}
	.b span {
		font-size: 11.5px;
		color: var(--text-3);
	}
	.b b {
		font-size: 19px;
		font-weight: 600;
		letter-spacing: -0.01em;
	}
	.b small {
		font-size: 11px;
		color: var(--text-3);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.note {
		margin: 0;
		font-size: 12px;
		line-height: 1.5;
		color: var(--text-3);
		border-left: 2px solid var(--warning);
		padding-left: 10px;
	}
	.card {
		background: var(--panel);
		border: 1px solid var(--line-2);
		border-radius: 12px;
		padding: 12px 14px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.hh {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 8px;
		font-size: 14px;
	}
	.x {
		all: unset;
		cursor: pointer;
		color: var(--text-3);
		font-size: 18px;
		line-height: 1;
		padding: 0 4px;
	}
	.x:hover {
		color: var(--text-1);
	}
	.small {
		font-size: 11.5px;
		margin: 0;
	}
	.go {
		margin-top: 6px;
	}
	.sw {
		display: inline-block;
		width: 9px;
		height: 9px;
		border-radius: 2px;
		margin-right: 6px;
		box-shadow: 0 0 0 1px var(--line-2);
	}
	.link {
		font-size: 12px;
		color: var(--text-2);
		margin-top: 4px;
		text-decoration: none;
	}
	.link:hover {
		color: var(--text-1);
	}
	.bh {
		font-size: 12px;
		color: var(--text-2);
		font-weight: 500;
		margin-bottom: 6px;
	}
	.block {
		border-top: 1px solid var(--line);
		padding-top: 16px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.kv {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		font-size: 12.5px;
		color: var(--text-3);
	}
	.kv b {
		color: var(--text-1);
		font-weight: 500;
		text-align: right;
		white-space: nowrap;
	}
	.hrow {
		all: unset;
		display: grid;
		grid-template-columns: 92px 1fr 46px;
		gap: 10px;
		align-items: center;
		padding: 3px 6px;
		margin: 0 -6px;
		border-radius: 6px;
		cursor: pointer;
		font-size: 12px;
	}
	.hrow:hover,
	.hrow.sel {
		background: var(--hover);
	}
	.hid {
		color: var(--text-2);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.hbar {
		height: 6px;
		background: var(--line);
		border-radius: 3px;
		overflow: hidden;
	}
	.hbar span {
		display: block;
		height: 100%;
		border-radius: 3px;
		background: #6d6d78;
	}
	.hbar span.over {
		background: var(--critical);
	}
	.hv {
		text-align: right;
		font-family: var(--mono);
		color: var(--text-1);
	}
	.foot {
		font-size: 11.5px;
		line-height: 1.5;
		margin: auto 0 0;
	}
	.spin {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		border: 2px solid var(--line-2);
		border-top-color: var(--text-1);
		animation: spin 0.7s linear infinite;
		display: inline-block;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (max-width: 900px) {
		.mappage {
			grid-template-columns: 1fr;
			grid-template-rows: 62vh auto;
		}
		.side {
			border-left: 0;
			border-top: 1px solid var(--line);
		}
	}
</style>
