#!/usr/bin/env python
"""Six presentation-only palette finalists; accepted scientific positions are read-only."""
from pathlib import Path
import argparse, csv, hashlib, json, shutil, sys
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from highdiversity_s11_colors import colors, key, mapping_table
from refine_s11_geographic_colors import gu, draw
from visualize_s11_geographic_colors import inputs, ROOT, RECEIPT, VIZ, COMMIT
from revisualize_s11_publication import sha, snapshot, unchanged, write_json, run

OLD = VIZ / '20260924_0156_umap_geographic_color_transfer_highdiversity'
PALETTES = ['OpponentHueDisk', 'Ziegler', 'CubeDiagonal', 'Bremm', 'HueChromaSweep', 'Teuling2']
VIEW = {'main': [-3.5, 4., 8.1, 18.], 'sw': [-3.5, -2.3, -.75, .75], 'east': [15.5, 16.22, 3.98, 4.62]}
INSETS = {'sw': [.015, .025, .18, .18], 'east': [.77, .025, .20, .20]}

def masks(xy):
    result = {k: (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)
              for k, (x0, x1, y0, y1) in VIEW.items()}
    assert np.all(np.sum(list(result.values()), axis=0) == 1)
    return result

def panel(fig, cm, xy, geo, rgba, boundary, palette, version):
    left = fig.add_axes([.075, .235, .38, .70])
    right = fig.add_axes([.505, .22, .46, .715])
    legend = fig.add_axes([.220, .075, .087, .125])
    subsets = masks(xy)
    main = draw(left, xy[subsets['main']], rgba[subsets['main']], size=4)
    left.set(xlim=VIEW['main'][:2], ylim=VIEW['main'][2:])
    left.set_title('(a) FM representation space', loc='left')
    for name, rect in INSETS.items():
        ax = left.inset_axes(rect)
        sc = ax.scatter(*xy[subsets[name]].T, c=rgba[subsets[name]], s=2, linewidths=0)
        ax.set(xlim=VIEW[name][:2], ylim=VIEW[name][2:], aspect='equal', xticks=[], yticks=[])
        for spine in ax.spines.values(): spine.set(linewidth=.5, color='#777777')
        assert np.array_equal(sc.get_facecolors(), rgba[subsets[name]])
        assert np.array_equal(np.asarray(sc.get_offsets()), xy[subsets[name]])
        # Insets sit in empty space; do not cover any displayed main-manifold point.
        x0, x1, y0, y1 = VIEW['main']
        u = (xy[subsets['main'], 0]-x0)/(x1-x0)
        v = (xy[subsets['main'], 1]-y0)/(y1-y0)
        assert not np.any((u >= rect[0]) & (u <= rect[0]+rect[2]) & (v >= rect[1]) & (v <= rect[1]+rect[3]))
    geographic = draw(right, geo, rgba, True, boundary, size=5.6)
    assert np.array_equal(main.get_facecolors(), geographic.get_facecolors()[subsets['main']])
    right.set_title('(b) Geographic distribution in Seoul', loc='left')
    key(legend, cm, palette, 'marginal_cdf')
    fig.text(.5, .985, f'v{version} · {palette}', ha='center', va='top', fontsize=10)
    fig.text(.5, .015, 'Insets use original coordinates; spacing to the main view is not preserved.', ha='center', fontsize=7)
    fig.canvas.draw()
    return {k: int(v.sum()) for k, v in subsets.items()}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['render', 'verify'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); out = args.output
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.labelsize': 9, 'axes.titlesize': 10, 'pdf.fonttype': 42})
    if args.phase == 'render':
        assert not out.exists()
        baseline = json.loads((OLD/'preservation_snapshot.json').read_text())
        unchanged(baseline)
        manifest = json.loads((OLD/'visualization_manifest.json').read_text())
        for p, h in manifest['payload_sha256'].items(): assert sha(p) == h
        assert sha(manifest['source_script']) == manifest['source_script_sha256']
        receipt = json.loads(RECEIPT.read_text()); assert receipt['status'] == 'PASS'
        for p, h in receipt['verified_payload_hashes'].items(): assert sha(p) == h
        baseline.update(snapshot(p for p in VIZ.rglob('*') if p.is_file()))
        out.mkdir()
        write_json(out/'preservation_snapshot.json', baseline)
        shutil.copytree(OLD/'reference_source', out/'reference_source', ignore=shutil.ignore_patterns('__pycache__'))
        print('INPUT/PRESERVATION PREFLIGHT PASS', flush=True)
    cm, ids, xy, geo, ranges = inputs(out)
    previous = pq.read_table(OLD/'scene_color_mapping_highdiversity.parquet')
    uv = np.column_stack([previous['color_u'].to_numpy(), previous['color_v'].to_numpy()])
    # Independent average-rank construction verifies all reused color coordinates.
    for j in range(2):
        sorted_axis = np.sort(xy[:, j])
        ranks = (np.searchsorted(sorted_axis, xy[:, j], side='left') + np.searchsorted(sorted_axis, xy[:, j], side='right') - 1)/2/8999
        assert np.array_equal(ranks, uv[:, j])
    cache = np.load(OLD/'candidate_RGB.npz')
    if args.phase == 'verify':
        for i, palette in enumerate(PALETTES, 1):
            rgb = colors(cm, palette, uv)
            expected = mapping_table(ids, xy, geo, uv, rgb, 'marginal_cdf', palette)
            path = out/f'scene_color_mapping_v{i}.parquet'
            assert expected.equals(pq.read_table(path))
            sink = pa.BufferOutputStream(); pq.write_table(expected, sink, compression='zstd')
            assert hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest() == sha(path)
        print('ALL SIX FRESH-PROCESS MAPPINGS/BYTES PASS'); return
    metrics = json.loads((OLD/'color_quality_metrics.json').read_text())
    boundary = gu(); rows = []; counts = None
    with PdfPages(out/'palette_finalists_all.pdf', metadata={'CreationDate': None, 'ModDate': None}) as pages:
        for i, palette in enumerate(PALETTES, 1):
            rgb = cache['marginal_cdf__'+palette]
            assert np.array_equal(rgb, colors(cm, palette, uv))
            rgba = np.column_stack([rgb/255, np.ones(9000)])
            table = mapping_table(ids, xy, geo, uv, rgb, 'marginal_cdf', palette)
            for col in ['scene_id', 'accepted_scene_index', 'UMAP1', 'UMAP2', 'center_x', 'center_y']:
                assert table[col].equals(previous[col])
            pq.write_table(table, out/f'scene_color_mapping_v{i}.parquet', compression='zstd')
            with (out/f'scene_color_mapping_v{i}.csv').open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=table.column_names); writer.writeheader(); writer.writerows(table.to_pylist())
            assert pq.read_table(out/f'scene_color_mapping_v{i}.parquet').equals(table)
            with (out/f'scene_color_mapping_v{i}.csv').open() as f:
                for a, b in zip(csv.DictReader(f), table.to_pylist(), strict=True):
                    for k, v in b.items(): assert (float(a[k]) == v if isinstance(v, float) else int(a[k]) == v if isinstance(v, int) else a[k] == v)
            fig = plt.figure(figsize=(11.6, 7.2))
            counts = panel(fig, cm, xy, geo, rgba, boundary, palette, i)
            fig.savefig(out/f'fm_seoul_palette_v{i}.pdf', metadata={'CreationDate': None, 'ModDate': None})
            fig.savefig(out/f'fm_seoul_palette_v{i}.png', dpi=300)
            pages.savefig(fig); plt.close(fig)
            rows.append({'version': i, 'palette': palette, 'normalization': 'marginal_cdf', **metrics['marginal_cdf__'+palette]})
            print(f'RENDERED v{i} {palette}', flush=True)
    # Overview uses exact final PNGs, so data, marker sizes and layout remain matched.
    fig, axes = plt.subplots(3, 2, figsize=(16, 15))
    for i, ax in enumerate(axes.flat, 1):
        ax.imshow(plt.imread(out/f'fm_seoul_palette_v{i}.png')); ax.axis('off')
    fig.subplots_adjust(left=.005, right=.995, bottom=.005, top=.995, hspace=.025, wspace=.015)
    fig.savefig(out/'palette_comparison_overview.png', dpi=210)
    fig.savefig(out/'palette_comparison_overview.pdf', metadata={'CreationDate': None, 'ModDate': None}); plt.close(fig)
    write_json(out/'palette_quality.json', rows)
    print(run(sys.executable, Path(__file__), 'verify', '--output', out), flush=True)
    oldmeta = json.loads((OLD/'figure_metadata.json').read_text())
    write_json(out/'figure_metadata.json', {
        'scope': 'Visualization-only palette finalists; no scientific calculation',
        'version_palette_order': PALETTES, 'normalization': '(average marginal rank - 1)/8999, reused global 9000-scene color coordinates',
        'same_transform_for_all_palettes': True, 'coordinate_extent': ranges, 'viewports': VIEW, 'inset_rectangles': INSETS,
        'display_population_counts': counts, 'point_sizes_pt2': {'main': 4, 'insets': 2, 'Seoul': 5.6}, 'alpha': 1,
        'figure_size_inches': [11.6, 7.2], 'PNG_dpi': 300, 'map_axes': 'off', 'map_boundary': oldmeta['boundary'],
        'source_inputs': oldmeta['input_hashes'], 'accepted_receipt': str(RECEIPT),
        'previous_visualization': str(OLD), 'previous_manifest_sha256': sha(OLD/'visualization_manifest.json'),
        'reference_package': 'pycolormap-2d 1.1.7 Apache-2.0; commit '+COMMIT,
        'custom_palette_definitions': {k: v for k, v in oldmeta.items() if k.startswith('custom_')},
        'quality_metrics': 'Reused earlier display-only diagnostics, unchanged; not scientific metrics or perceptual thresholds',
        'quality_definitions': oldmeta['quality_definitions'],
        'runtime': oldmeta['runtime'],
        'caveats': ['Original positions unchanged; global marginal CDF only changes color assignment.', 'Two distant portions shown with original coordinates; spacing to main view not preserved.', 'Central-lower portion remains inside the enlarged main viewport.', 'No local/inset color normalization.', 'RGB uniqueness does not imply perceptual uniqueness.', 'Colors are not semantic classes, 256D distances, model validity evidence or removal of spatial dependence.']})
    unchanged(json.loads((out/'preservation_snapshot.json').read_text()))
    write_json(out/'validation.json', {'status': 'PASS', 'scenes_per_version': 9000, 'versions': 6, 'exact_scene_order_coordinates': True, 'all_RGB_left_right_exact': True, 'all_CSV_Parquet_cells_exact': True, 'fresh_process_mapping_Parquet_bytes_identical': True, 'prior_candidate_RGB_exact': True, 'viewports_exhaustive_disjoint': counts, 'insets_occlude_zero_main_points': True, 'S11_receipt_listed_files_unchanged': 1352, 'S12_files_unchanged': 27427, 'previous_visualizations_and_dissertation_unchanged': True})
    write_json(out/'visualization_manifest.json', {'status': 'PASS', 'source_script': str(Path(__file__).resolve()), 'source_script_sha256': sha(__file__), 'payload_sha256': snapshot(p for p in out.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name != 'visualization_manifest.json')})
    print('READY '+str(out), flush=True)

if __name__ == '__main__': main()
