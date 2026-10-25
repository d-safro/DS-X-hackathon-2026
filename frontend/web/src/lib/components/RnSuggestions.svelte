<script lang="ts">
	import { rn, describeSuggestion } from '#lib/rn.svelte.ts';
	import { num, pct } from '#lib/format.ts';
	import type { Suggestion } from '#lib/rn-api.ts';
	import Icon from './Icon.svelte';

	const r = $derived(rn.result!);
	const res = $derived(rn.suggestions);
	const closures = $derived(rn.events.some((e) => e.kind === 'close_hospital'));
	const cuts = $derived(rn.events.some((e) => e.kind === 'set_capacity' && (e.factor ?? 1) < 1));

	// How much of today's shortfall a fix removes; for an access-only problem, count tract-weeks instead.
	function share(s: Suggestion) {
		const c = res!.current;
		return c.unmet >= 0.5 ? s.people_helped / c.unmet : s.tract_weeks_fixed / Math.max(1, c.poor_tract_weeks);
	}
	const TW = 'One tract for one week. 60 fewer could mean 20 tracts each spend 3 fewer weeks with an access score under the threshold.';
</script>

<div class="help">
	{#if !res}
		<p class="lead">
			Try a few fixes on this scenario: more beds where hospitals overflow, slower spread{closures ? ', reopening a hospital you closed' : ''}{cuts
				? ', giving back beds you cut'
				: ''}. Each fix is a full rerun of the model, so this takes a few seconds.
		</p>
		<button class="btn primary" onclick={() => rn.suggest()} disabled={rn.suggesting || rn.loading}>
			{#if rn.suggesting}<span class="spin"></span> Trying fixes…{:else}<Icon name="bulb" size={14} /> Find fixes{/if}
		</button>
		{#if rn.suggestError}<p class="err">{rn.suggestError}</p>{/if}
	{:else if res.status === 'nothing_to_fix'}
		<p class="lead">Nothing to fix: everyone who needs a bed gets one, and every tract keeps good access.</p>
	{:else}
		<p class="lead">
			As things stand, over {r.weeks} weeks <b>{num(res.current.unmet)}</b> people can't get a bed and tracts spend
			<b title={TW}>{num(res.current.poor_tract_weeks)}</b> <span class="tw" title={TW}>tract-weeks</span> with poor access. Each
			fix below was run on its own on top of your scenario.
		</p>
		{#if res.status === 'none_helped'}
			<p class="lead">None of the {res.tried} fixes tried helps in this scenario.</p>
		{/if}
		<ol class="list">
			{#each res.suggestions as s, i (s.id)}
				{@const d = describeSuggestion(s, r.weeks)}
				<li class="row">
					<div class="top">
						<span class="rank">{i + 1}</span>
						<b class="title">{d.title}</b>
						<button class="btn apply" onclick={() => rn.applySuggestion(s)} disabled={rn.loading}>Apply</button>
					</div>
					<div class="bar" title="{pct(share(s))} of the current shortfall"><i style:width="{Math.min(1, share(s)) * 100}%"></i></div>
					<div class="res">
						<b>{num(s.people_helped)}</b> more people get a bed{#if s.tract_weeks_fixed > 0}&nbsp;· <b>{num(s.tract_weeks_fixed)}</b>
							<span class="tw" title={TW}>fewer tract-weeks</span> of poor access{/if}
					</div>
					<div class="detail">{d.detail}</div>
				</li>
			{/each}
		</ol>
		<p class="meta">Tried {res.tried} fixes in {res.seconds} s. Apply one to add it to your scenario; the list clears when anything changes.</p>
	{/if}
	<p class="caveat">
		What-ifs in a simple model, not advice. Tested on real hospital data it forecasts worse than “next week looks like this
		week”, and it is not for hospital planning.
	</p>
</div>

<style>
	.help {
		display: flex;
		flex-direction: column;
		gap: 10px;
		align-items: flex-start;
	}
	.lead {
		margin: 0;
		font-size: 12.5px;
		line-height: 1.55;
		color: var(--text-2);
	}
	.lead b {
		color: var(--text-1);
		font-weight: 600;
	}
	.tw {
		text-decoration: underline dotted var(--text-3);
		text-underline-offset: 2px;
		cursor: help;
	}
	.err {
		margin: 0;
		font-size: 12px;
		color: #ff8a8a;
	}
	.list {
		list-style: none;
		margin: 0;
		padding: 0;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.row {
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		background: var(--bg);
	}
	.top {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.rank {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--text-3);
		width: 14px;
		flex-shrink: 0;
	}
	.title {
		flex: 1;
		font-size: 13px;
		font-weight: 500;
		color: var(--text-1);
	}
	.apply {
		padding: 4px 12px;
		flex-shrink: 0;
	}
	.bar {
		height: 6px;
		border-radius: 3px;
		background: var(--line);
		margin-left: 24px;
		overflow: hidden;
	}
	.bar i {
		display: block;
		height: 100%;
		background: var(--good);
		border-radius: 3px;
	}
	.res,
	.detail {
		margin-left: 24px;
		font-size: 12px;
		line-height: 1.5;
	}
	.res {
		color: var(--text-2);
	}
	.res b {
		color: var(--text-1);
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.detail {
		color: var(--text-3);
	}
	.meta,
	.caveat {
		margin: 0;
		font-size: 11.5px;
		line-height: 1.5;
		color: var(--text-3);
	}
	.spin {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		border: 2px solid rgb(0 0 0 / 0.2);
		border-top-color: var(--bg);
		animation: spin 0.7s linear infinite;
		display: inline-block;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (max-width: 700px) {
		.bar,
		.res,
		.detail {
			margin-left: 0;
		}
	}
</style>
