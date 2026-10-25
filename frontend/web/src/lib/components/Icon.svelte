<script lang="ts">
	// A few 16px line icons, drawn inline so the site works offline.
	const PATHS: Record<string, string> = {
		map: 'M2 4l4-2 4 2 4-2v10l-4 2-4-2-4 2zM6 2v10M10 4v10',
		pulse: 'M1 8h3l2-5 4 10 2-5h3',
		hospital: 'M3 14V3h10v11M6 14v-3h4v3M8 5v4M6 7h4',
		spread: 'M1 12c3 0 4-8 7-8s4 8 7 8M1 12h14',
		check: 'M2 8.5l3.5 3.5L14 4',
		book: 'M3 2h8a2 2 0 012 2v10H5a2 2 0 01-2-2zM3 12a2 2 0 012-2h8',
		sliders: 'M3 2v12M8 2v12M13 2v12M1 10h4M6 5h4M11 11h4',
		play: 'M4 2.5v11l9-5.5z',
		pause: 'M4 2.5h3v11H4zM9 2.5h3v11H9z',
		reset: 'M2.5 8a5.5 5.5 0 109.4-3.9M12 1.5V4.5H9',
		x: 'M3.5 3.5l9 9M12.5 3.5l-9 9',
		plus: 'M8 3v10M3 8h10',
		bulb: 'M6 13h4M6.5 15h3M8 1.5a4.5 4.5 0 00-2.5 8.2V11h5V9.7A4.5 4.5 0 008 1.5z',
		bolt: 'M9 1L3 9h4l-1 6 6-8H8z',
		layers: 'M8 1.5l6.5 3.5L8 8.5 1.5 5zM1.5 8L8 11.5 14.5 8M1.5 11L8 14.5 14.5 11',
		chevron: 'M6 3l5 5-5 5',
		tracts: 'M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z',
		lab: 'M6 1.5h4M6.5 1.5v4L2.6 12.9a1 1 0 00.9 1.6h9a1 1 0 00.9-1.6L9.5 5.5v-4M4.6 10h6.8',
		download: 'M8 2v8M4.5 6.5L8 10l3.5-3.5M2.5 13.5h11',
		data: 'M2.5 4c0-1.1 2.5-2 5.5-2s5.5.9 5.5 2-2.5 2-5.5 2-5.5-.9-5.5-2zM2.5 4v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V4M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2'
	};
	interface Props {
		name: keyof typeof PATHS | string;
		size?: number;
	}
	let { name, size = 16 }: Props = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 16 16"
	fill={name === 'play' || name === 'pause' ? 'currentColor' : 'none'}
	stroke="currentColor"
	stroke-width="1.4"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"><path d={PATHS[name]} /></svg
>
