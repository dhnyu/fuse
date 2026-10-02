#!/usr/bin/env python
"""Render a descriptive audit report from existing audit tables only (no ranking)."""
from pathlib import Path
import argparse,json,hashlib,subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

def table(df):
    # No optional tabulate dependency; full precision remains in machine tables.
    def f(x):
        if pd.isna(x):return '—'
        if isinstance(x,(float,np.floating)):return f'{x:.6g}'
        return str(x).replace('|','\\|')
    return '| '+' | '.join(map(str,df.columns))+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(f(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();o=a.output;assert not a.report.exists()
    m=json.loads((o/'audit_manifest.json').read_text());read=lambda n:pd.read_csv(o/(n+'.csv'))
    s=read('summary_statistics');q=pd.read_parquet(o/'master_query_table.parquet');tr=read('rank1_transition_standard_to_nonlocal');h=read('hubness_summary');near=read('near_duplicate_summary');inv=read('invariant_checks');val=read('independent_acceptance_checks');th=read('threshold_proportions');region=read('rank_region_summary');num=read('numerical_precision_probe');dups=read('duplicate_representation_groups');pairs=read('exact_duplicate_pairs');cor=read('correlations')
    assert (inv.status=='PASS').all() and (val.status=='PASS').all()
    def summary(metrics):return table(s[s.metric.isin(metrics)][['metric','mode','n','mean','sd','min','p01','p05','p25','median','p75','p95','p99','max']])
    def value(metric,mode,stat='mean'):return float(s[(s.metric==metric)&(s['mode']==mode)].iloc[0][stat])
    def pct(x):return f'{100*x:.3f}%'
    st=q[q['mode']=='standard'];nl=q[q['mode']=='nonlocal'];findings=[
        f'All 9,000 originals were queries in both modes: 18,000 master rows; Standard has 80,991,000 directed eligible pairs and Non-local has {int(nl.eligible_count.sum()):,}.',
        f'Non-local eligible count ranges from {int(nl.eligible_count.min()):,} to {int(nl.eligible_count.max()):,}, mean {nl.eligible_count.mean():.3f}; mean excluded fraction is {pct(nl.excluded_nonlocal_proportion.mean())}.',
        f'Standard Rank-1 similarity mean/median: {st.rank1_similarity.mean():.6f}/{st.rank1_similarity.median():.6f}; Non-local: {nl.rank1_similarity.mean():.6f}/{nl.rank1_similarity.median():.6f}.',
        f'Standard Rank-1 distance median is {st.rank1_distance_m.median():.3f} m, mean {st.rank1_distance_km.mean():.3f} km; {pct((st.rank1_distance_m<250).mean())} are below 250 m.',
        f'{pct((st.rank1_distance_m<2000).mean())} of Standard Rank-1 candidates are below 2 km; {pct(tr.retained.mean())} retain the identical candidate after exclusion.',
        f'Delta = Non-local − Standard similarity has mean {tr.delta_sim.mean():.6f}, median {tr.delta_sim.median():.6f}; the largest drop is {tr.similarity_drop.max():.6f}.',
        f'{pct((tr.delta_sim<=-.05).mean())} lose at least 0.05 similarity and {pct((tr.delta_sim<=-.10).mean())} lose at least 0.10.',
        f'{int((tr.delta_sim==0).sum()):,} queries have zero score change, versus {int(tr.retained.sum()):,} retained IDs: {int(((tr.delta_sim==0)&(~tr.retained)).sum())} change ID at an identical score.',
        f'Non-local Rank-1 distance median is {nl.rank1_distance_km.median():.3f} km; minimum {nl.rank1_distance_m.min():.6f} m; {pct((nl.rank1_distance_m>=10000).mean())} are at least 10 km away.',
        f'Rank-1 similarity ≥0.90 occurs in {pct((st.rank1_similarity>=.90).mean())} Standard and {pct((nl.rank1_similarity>=.90).mean())} Non-local queries.',
        f'Median top1–top2 margin is {st.gap_rank1_rank2.median():.6f} Standard and {nl.gap_rank1_rank2.median():.6f} Non-local.',
        f'Mean cosine over all eligible directed pairs is {value("all_eligible_pair_similarity","standard"):.6f} Standard and {value("all_eligible_pair_similarity","nonlocal"):.6f} Non-local.',
        f'Median query Spearman(rank, distance) is {st.rho_rank_distance.median():.6f} Standard and {nl.rho_rank_distance.median():.6f} Non-local; geography is a descriptive association, not an explanation of causality.',
        'Mutual Rank-1 unordered pairs: '+', '.join(f'{r["mode"]} {int(r.mutual_top1_unordered_pairs):,} ({pct(r.mutual_top1_directed_edge_fraction)} of query selections)' for _,r in h.iterrows())+'.',
        'Rank-1 never-selected fractions: '+', '.join(f'{r["mode"]} {pct(r.never_selected_proportion)}; Gini {r.gini:.6f}' for _,r in h.iterrows())+'.',
        f'Exact embedding duplicates comprise {len(dups)} scenes in {dups.group.nunique()} groups ({m["duplicate_embedding_extra_rows"]} extra rows, {len(pairs)} unordered pairs); all have zero recorded objects. Distinct scene IDs and distinct centers remain intact.',
        f'There are {int(near.iloc[0].unordered_pairs):,} unordered pairs with cosine >0.99, including {int(near.iloc[0].distant_pairs):,} at ≥2 km. These are diagnostics, not confirmed preprocessing duplication.',
        f'All {len(inv)} producer invariants and {len(val)} independent checks pass; all 558,000 existing region rows and 3,000 legacy top-50 rows match exactly.'
    ]
    sections=[]
    def add(title,body):sections.append('# '+title+'\n\n'+body.strip()+'\n')
    add('Executive Summary','**PASS WITH CONDITIONS.** The full population audit is usable for Section 5.3.2. Conditions concern interpretation of exact/near duplicate representations, projected-distance and numerical conventions, and exploratory figure status; no integrity invariant failed. No manuscript wording or final figure selection was made.\n\nSource: final FM `'+m['model']['checkpoint_id']+'`, epoch 60; gallery `'+m['gallery_manifest']+'`; embedding `'+m['embedding_manifest']+'`; existing all-query region generation `s10all_0d929355b8cad37b85860e2c`.\n\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(findings,1)))
    add('1. Scope and Scientific Contract',f'''Purpose: a broad descriptive inventory of final FM retrieval behavior for dissertation Chapter 5, Section 5.3, especially 5.3.2. Input prompt requested all 9,000 original scenes as queries in Standard and Non-local modes; complete lineage, statistics, diagnostics, plotting sources, candidate figures, invariants, and no scientific mutation/training/inference/selection/commit/push.

Execution began {m['started_at']}; report created {datetime.now(ZoneInfo('Asia/Seoul')).isoformat()}. Repository commit `{m['git_commit']}`, branch `{m['branch']}`; dissertation commit `{m['dissertation_commit']}`. Initially the workspace was on `s11/representation-contract-pilot-20260923`, at the same commit as reduced. Following the user's instruction, `git switch reduced` preserved every existing status entry and checked file bytes. No merge commit was required. Existing uncommitted work was preserved.

Read current dissertation inference/cosine equations, training-selection section, retrieval section, and current blueprint. The current 5.3.2 heading is **Retrieval Summary**, while the prompt calls it **Overall Retrieval Behavior**; this is an editorial naming difference, not a changed calculation. Historical S10 30-query and 100-query viewer scope is not treated as the population scope. No blueprint or scientific contract was edited for this audit.

This is an isolated report/audit script, not a new research or maintenance target. No target definition, command, dependency, store, training pipeline, or network changed. Thus tar_manifest/tar_network/tar_validate/tar_make and network HTML regeneration are not applicable and were not run. CPU deterministic post-processing only; no GPU acquisition, model loading, checkpoint selection, augmentation, or raw/canonical rebuilding.''')
    paths=pd.DataFrame([dict(role=k,path=v) for k,v in m['source_paths'].items() if k in ['checkpoint','checkpoint_manifest','campaign','gallery','models','fm_embedding_manifest','fm_vectors','bands','band_manifest','scene_index','finalization','legacy_ranking']])
    add('2. Source Artifact and Lineage Audit',table(paths)+f'''

All consumed source hashes are in `source_checksums_before.json` and `audit_manifest.json`; all matched after processing and independent validation. The finalization is existing authoritative evidence, not a new selection: validation loss **0.29247623682022095**, source-separation margin **0.34660565853118896**, epoch **60**, update **4560**. Existing selector replay contains 16 candidates, four final non-improving validation events at epochs 65/70/75/80, and stopping at epoch 80. Evaluation-consumption count during selection is zero.

Checkpoint SHA256: `{m['model']['payload_sha256']}`. Vector SHA256: `{m['embedding_sha256']}`. Inference source uses `model.load_state_dict(payload["online_model"])`, then `model(...)["scene_embedding"]`, then L2 normalization. `model_families.py` returns the scene fusion output separately from the contrastive projection. Historical runtime source hashes for inference, encoder, originals reader, pipeline, and ranking all match current source. No checkpoint was deserialized for this audit.

Embedding shape **(9000, 256)**, dtype **float32**; observed float32 row norms **{m['normalization_min']:.10f}–{m['normalization_max']:.10f}**. Stored values were not renormalized. IDs are unique and lexically ordered, exactly match the embedding manifest, prepared-original manifest and accepted evaluation scene index. Coordinates match that index bit-for-bit in **EPSG:5186** (meters). Evaluation coordinates are not assumed to lie on the training lattice.

The original S10 ranking has only 30 queries/mode ×50 ranks (3,000 FM rows). The all-query artifact has 9,000 queries/mode ×31 region candidates (558,000 rows), but not complete rankings. Existing regions are reused and fully checked; missing ranks and distribution statistics come from deterministic in-memory ordering of existing vectors. No new scientific ranking artifact replaces an old artifact.

The gallery `source_payload_sha256` identifies source shard payloads, not individual scene-content fingerprints: {m['repeated_source_shard_hash_extra_rows']:,} repeated rows in that field reflect shared shards. They do **not** establish repeated scenes. `duplicate_representation_groups.csv` preserves that field for provenance only.''')
    add('3. Retrieval Definitions','''For query i, s(i,j) = X[j] dot X[i], computed by float32 NumPy GEMV on the accepted L2-normalized encoder representation. This implements the dissertation cosine equation within floating-point error. No temperature, projected embedding, or new normalization is used. Stable descending score order over ascending scene IDs implements exact-score ties by ascending scene ID.

Standard eligibility: j ≠ i. Non-local eligibility: j ≠ i and sqrt((xj−xi)²+(yj−yi)²) ≥ 2000 m. The comparison has no geographic epsilon: **exactly 2000 m is allowed**. Distances are planar projected center distances, not ellipsoidal geodesics.

For n eligible candidates, one-based regions are Rank1={1}, Upper={2,…,11}, Middle={floor((n−10)/2)+1,…,floor((n−10)/2)+10}, Lower={n−9,…,n}. Standard n=8999 gives Middle **4495–4504**. This is the historical deterministic lower-side centering convention for an even-sized window; it is reproduced without modification. Selected scalar midpoint is rank floor((n−1)/2)+1 (4500 for Standard), distinct from the ten-member Middle region.

Common descriptive conventions: population SD (ddof=0); linear empirical quantiles, h=(n−1)p and interpolation between adjacent order statistics; IQR=Q75−Q25; MAD=median(|x−median(x)|), **unscaled**; moment skewness and excess kurtosis (bias=True); CV=SD/mean only for nonnegative values with positive mean. Constant-distribution skewness/kurtosis and inapplicable CV are blank. No sample-inference interpretation or p-values.

Spearman uses average ranks for tied values. Rank-versus-distance uses actual deterministic ordinal retrieval ranks; similarity-versus-distance uses average score ranks. They can differ slightly at ties. Near-zero correlation is |rho|≤0.05, an explicit descriptive threshold; positive/negative categories overlap that near-zero set. Region paired standardized difference is mean(delta)/population-SD(delta), not a significance test.

All-pair summaries are **directed** eligible query-candidate pairs, weighted equally per pair. Non-local query means are separately equally weighted per query. Pair quantiles are exact quantiles of stored float32 scores using disk-backed arrays, not histogram approximations. No arbitrary relevance labels, HIT@K, MRR, accuracy, or pseudo-ground truth are created.''')
    add('4. Integrity and Invariant Checks',table(inv)+ '\n\nIndependent checks:\n\n'+table(val)+f'''

Every full-ranking row was checked for self exclusion, score ordering, exact lexical tie order, finite values, candidate counts and distance eligibility. Every query resolves uniquely. Standard→Non-local score increases: **{m['raw_positive_delta_count']} even at zero tolerance**; the declared audit tolerance is 1e−6. Norm tolerance is 2e−6. Already-eligible Standard winners retain ID and score exactly. No data pair lies exactly at 2000 m ({m['exact_boundary_directed_pairs']} directed pairs), so the equality boundary is verified with explicit 1999.999/2000/2000.001 m fixtures.

A deterministic 33-query float64 cosine probe has maximum absolute score discrepancy **{num.max_abs_float32_vs_float64_cosine.max():.9g}**, and **{int(num.rank1_changed.sum())}** Rank-1 ID changes. This probe is a numerical diagnostic, not replacement ranking. Distinct-scene scores >1: {m['distinct_directed_scores_gt_one']}. Maximum observed pair distance: {m['max_distance_m']:.3f} m. Distances are nonnegative, finite and within the scene support; the minimum Rank-1 distance is plausible for independently sampled evaluation centers.

Syntax and deterministic fixtures passed. Independent validation reconstructs 41 evenly spaced queries with lexsort and scipy Spearman, verifies mass/count consistency, checks source preservation and historical code lineage. Full production elapsed about one minute with CPU 1 worker ×1 thread, maximum RSS about 1.7 GB (see log). No active process was stopped.''')
    add('5. Eligible Candidate Statistics',summary(['eligible_count','excluded_nonlocal_count','excluded_nonlocal_proportion'])+'\n\nStandard is exactly 8,999 for every query. Non-local removed count uses 8,999−n, excluding self from the denominator. `candidate_count_distribution.csv` gives exact count frequencies. `boundary_proxy_summary.csv` groups candidate counts by quintiles of center-coordinate, distance to evaluation-center centroid, and distance to evaluation-center convex-hull boundary. These are support-edge proxies, not administrative-boundary analysis.\n\n'+table(cor[cor.metric.str.contains('count')])+'\n\nThe association supports systematic candidate-count variation across the spatial support. It cannot separate study-boundary effects from the sampled center distribution, and it does not identify a geographic cause.')
    add('6. Rank-1 Similarity',summary(['rank1_similarity','delta_sim','similarity_drop'])+'\n\nThreshold proportions:\n\n'+table(th[th.metric.isin(['rank1_similarity','delta_sim'])])+'\n\nDelta correlations:\n\n'+table(cor[cor.metric.str.contains('delta')])+'\n\nFull quantiles, MAD, CV where applicable, skewness and excess kurtosis are in `summary_statistics.csv`. `histogram_counts.csv`, `ecdf_points.csv`, and the 18,000-row master table provide plotting and density-estimation source data. Empirical p01–p99 are additional data-driven thresholds; no kernel-density bandwidth is imposed.')
    add('7. Geographic Distance',summary(['rank1_distance_m','rank1_distance_km'])+'\n\nMutually exclusive bands (km):\n\n'+table(read('distance_bin_summary'))+'\n\nAll requested cumulative cutoffs, including 250/500/750/1000/1500/2000/3000/5000/10000 m and additional 15/20/30 km cutoffs, are in `threshold_proportions.csv`. Every Non-local Rank-1 distance is ≥2 km. Distance ECDF, logarithmic-bin histogram and linear distance hexbin sources are retained.')
    add('8. Standard vs Non-local Transition',f'''`rank1_transition_standard_to_nonlocal.csv` has exactly 9,000 ID-paired rows with both candidate IDs, scores, distances, counts, retained indicator, delta and positive drop. Retained: **{tr.retained.sum():,} ({pct(tr.retained.mean())})**; changed: **{(~tr.retained).sum():,} ({pct((~tr.retained).mean())})**. Already ≥2 km but changed: **0**. Every changed query originally had a local winner.

Zero-score-change and retained-ID rates must not be conflated: **{((tr.delta_sim==0)&(~tr.retained)).sum()}** changed queries keep the identical float32 score. They are legitimate tied substitutions. Local-only replacement distributions and gap statistics are in `summary_statistics.csv` (`local_substitution_*`) and `locality_diagnostics.csv` (`local_lt_2km`). Distance-band retention rates, mean/median drops and replacement similarity are included for all bands; empty bands are explicitly n=0.'''+ '\n\n'+table(read('locality_diagnostics').query("group=='local_lt_2km'") [['metric','n','mean','sd','median','p25','p75']]))
    add('9. Rank Profiles',summary(['gap_rank1_rank2','gap_rank1_rank5','gap_rank1_rank10','gap_rank1_rank100','gap_rank1_median','gap_rank1_bottom'])+'\n\n`rank_profile.csv` contains ranks 1–100 densely, then 60 log-spaced positions through rank 8000, separately by mode. Each point has all common distribution statistics. `selected_rank_summary.csv` also covers 1,2,5,10,11,25,50,100, the query-dependent midpoint, bottom-10 start and last rank, for both cosine and distance. The underlying selected rows are in `selected_rank_source.parquet`. Absolute-rank curve stops at 8000 to avoid unequal query support; tail and midpoint summaries remain query-relative. No ranking-accuracy meaning is attached.')
    add('10. Rank-region Analysis',table(region[(region.metric=='cosine')&(region.aggregation=='query_mean')][['mode','region','n','mean','sd','p25','median','p75']])+'\n\n`rank_region_summary.csv` includes pooled and query-mean distributions of cosine and geographic distance for all four regions. Each mode has 9,000 Rank1 and 90,000 Upper/Middle/Lower values; no region is sampled. `rank_region_source.parquet` is the verified copy of existing bands.\n\n'+table(read('paired_region_differences')[['mode','contrast','mean','median','sd','standardized_paired_difference']])+'\n\nStandard and Non-local query-level region distributions should be compared with equal query weighting. Pooled region SD measures within- and between-query variation together. Differences and paired standardized effects are descriptive only.')
    add('11. Locality Diagnostics',table(read('locality_diagnostics').query("group in ['local_lt_2km','nonlocal_ge_2km'] and metric in ['standard_rank1_similarity','top1_top2_margin','similarity_drop','nonlocal_similarity','nonlocal_eligible_count']")[['group','metric','n','mean','median','retention_rate']])+'\n\nAll distance-band comparisons, including top10 SD, count within 0.01 of maximum, replacement distance and candidate counts, are in `locality_diagnostics.csv`. These groups condition on the learned Standard nearest neighbor. They are not randomized interventions; lower Non-local similarity follows from candidate-set restriction and must not be described as a causal decomposition of geographic influence.\n\n'+summary(['rho_rank_distance','rho_similarity_distance'])+'\n\nSelected-rank and region geographic-distance distributions are provided. Positive rho(rank,distance) means more distant candidates tend to occur farther down the ranking. The summary has mixed signs and modest medians; do not infer a universal monotonic relationship. Sign and near-zero proportions are in `threshold_proportions.csv`.')
    add('12. Neighborhood Sharpness / Ambiguity',summary(['gap_rank1_top5_mean','gap_rank1_top10_mean','top10_sd','top10_range','within_0p005_count','within_0p01_count','within_0p025_count','within_0p05_count','rank1_exact_tie_count'])+'\n\nThe top5/top10 mean margins include Rank1: s1−mean(s1…sk). For epsilon∈{0.005,0.01,0.025,0.05}, count = sum over eligible j of I[sj≥s1−epsilon], and proportion=count/n. Thus these counts include the winning candidate and all exact ties. Top10 SD uses population SD. No temperature-dependent “effective neighbor” metric is introduced.\n\nAll-pair distribution:\n\n'+table(read('all_pair_similarity_summary'))+'\n\nPer-query all_mean/all_sd/all_min/all_max/all_median/all_p95/all_p99, max_minus_p99, max_minus_mean, and max_zscore=(max−mean)/SD are in the master and summary tables. The trivial percentile rank of a maximum is omitted. These quantify concentration, not the correctness of a nearest neighbor.')
    add('13. Reciprocity and Hubness',table(h[['mode','max','never_selected_proportion','gini','top_0.01_selection_share','top_0.05_selection_share','top_0.1_selection_share','mutual_top1_unordered_pairs','mutual_top1_directed_edge_fraction','mutual_top5_unordered_pairs','mutual_top5_directed_edge_fraction','mutual_top10_unordered_pairs','mutual_top10_directed_edge_fraction']])+'''\n\nIndegree includes all 9,000 scenes, including zeros, and sums to 9,000 per mode. `scene_indegree.csv` is the complete distribution and `hub_top20.csv` the most selected scenes, with scene-ID tie breaking. Top p% concentration uses the largest ceil(p×9000) indegrees. Gini = 2 sum(i*x_sorted_i)/(N sum x) − (N+1)/N.

Mutual top-k pair means i selects j in its first k and j selects i in its first k. Unordered pairs are counted once; directed-edge fraction = 2×mutual_pairs/(9000k). At k=1 it also equals the fraction of queries participating in a reciprocal pair. `mutual_rank1_pairs.csv` lists all unordered pairs. These diagnostics do not establish model quality.''')
    add('14. Duplicate / Near-duplicate Diagnostics',table(near)+f'''

Threshold comparisons are strict `>`. Unordered pair counts use the lower lexical scene ID as query, once per pair; the main all-pair distributions retain both query directions. Distinct-scene support counts are also reported separately for each mode. Representative examples are bounded to the first 20 lexical pairs per threshold; they are not a random sample.

Exact float32 duplicate groups: {dups.group.nunique()} groups of sizes {sorted(dups.groupby('group').size().tolist())}, totaling {len(dups)} scenes and {len(pairs)} pairs. Their distance range is **{pairs.distance_m.min():.3f}–{pairs.distance_m.max():.3f} m**; **{(pairs.distance_m>=2000).sum()}** are ≥2 km. All have object count zero. Empty-object scenes may share outputs despite differing scene identity/location; the audit establishes equality of representations, not the cause. Near duplicates require later inspection of accepted inputs before any preprocessing-duplication claim. No scene, vector, candidate or outlier was removed.

`duplicate_representation_groups.csv`, `exact_duplicate_pairs.csv`, `near_duplicate_summary.csv`, `near_duplicate_examples.csv` and query-level threshold counts preserve evidence. Repeated source shard hashes are normal provenance and are explicitly not used as duplicate-scene tests.''')
    add('15. Spatial Export Diagnostics','''`master_query_table.parquet` and its CSV have EPSG:5186 center_x/center_y, two rows per query distinguished by mode, Rank1 score/distance/ID, transition delta/drop/retention, margins, concentration counts, own indegree and retrieved-candidate indegree. This is an explicitly documented coordinate table, **not a GeoParquet geometry encoding**. `spatial_metadata.json` specifies CRS and field meanings; `evaluation_scene_identity.csv` preserves accepted existing metadata, excluding geometry blobs.

No new labels, administrative zones, land-use classes or geographic supervised evaluation were introduced. The optional point-map figure uses existing projected centers directly, with no basemap, polygon join or reprojection. Convex-hull support proxies are analytic diagnostics only.''')
    add('16. Extreme-query Inventory',f'''`extreme_query_inventory.csv` has {len(read('extreme_query_inventory')):,} category-membership rows (a query may appear more than once). It includes highest/lowest score in both modes, largest/smallest drops, shortest/longest distances, largest/smallest margins, hub-associated queries, mutual examples, and geographically distant (≥10 km) high-similarity candidates. Every category uses deterministic metric order then ascending query ID, retaining at most 20 members.

This is an inventory for later qualitative inspection, **not cherry-picked evidence of performance**. Inspect successes, ambiguous ties, empty-object scenes, weak scores and outliers together. No figure examples were selected for the dissertation.''')
    figure_rows=[]
    names=['Rank-1 cosine distributions','Distance ECDF','Standard distance logarithmic histogram','Signed similarity-change histogram','Similarity/drop by distance band','Mean similarity by rank','Rank-region median/IQR','Top1–top2 margin distributions','Rank-1 indegree distribution','Distance–similarity hexbin','Spatial query statistics']
    sources=['master_query_table.csv; histogram_counts.csv','ecdf_points.csv','master_query_table.csv','rank1_transition_standard_to_nonlocal.csv; histogram_counts.csv','rank1_transition_standard_to_nonlocal.csv; locality_diagnostics.csv','rank_profile.csv','rank_region_summary.csv','master_query_table.csv; histogram_counts.csv','scene_indegree.csv','master_query_table.csv','master_query_table.csv; spatial_metadata.json']
    for path,title,src in zip(sorted((o/'figures').glob('*.png')),names,sources):figure_rows.append(dict(figure=path.name,description=title,source=src))
    add('17. Candidate Figures',table(pd.DataFrame(figure_rows))+f'\n\nDirectory: `{o}/figures`. All 11 figures are supplied as PNG and vector PDF and labeled **Exploratory candidate — not final dissertation figure**. Figure 1 bins cover the full observed range in both modes. Histogram density heights are not query proportions; use bin counts/ECDF for exact proportions. Spatial point maps have no causal interpretation. Full source data are retained; no raster-only statistic is authoritative.')
    add('18. Statistics Recommended for Dissertation Section 5.3.2','''Recommendations only: **even CORE is not a final manuscript choice**. A person must inspect these outputs and decide what to report.

| Grade | Candidate statistic | Reason |
| --- | --- | --- |
| CORE | 9,000 queries per mode; 8,999 Standard candidates; Non-local count range | Establishes population and differing candidate pools |
| CORE | Rank1 cosine median/IQR (optionally mean/SD), both modes | Describes nearest learned neighbors |
| CORE | Standard distance ECDF, median/IQR, fractions <250m/<500m/<2km and ≥2km | Makes locality explicit |
| CORE | Paired score-drop median/IQR and same-ID retention | Quantifies the immediate consequence of exclusion |
| CORE | Tied-score caveat: unchanged score ≠ retained ID | Prevents misreporting the 16 tied substitutions |
| SUPPORTING | Rank-region similarity or compact rank profile | Describes representation-space ordering beyond Rank1 |
| SUPPORTING | Non-local Rank1 distance distribution and ≥10km fraction | Documents actual geographic separation |
| SUPPORTING | Top1–top2 margin distribution | Documents neighbor ambiguity |
| SUPPORTING | Distance-band similarity/drop comparison | Supports descriptive locality discussion |
| DIAGNOSTIC | Duplicate representations, precision probe, invariant tests | Qualifies reliability and interpretation |
| DIAGNOSTIC | Hubness/reciprocity, all-pair moments, count-edge proxies | Broadens neighborhood diagnostics |

Avoid reporting many redundant thresholds in the main text. Exact manuscript phrasing, figure count and preferred summaries remain undecided.''')
    add('19. Statistics Better Kept for Appendix / Diagnostics','''Full p01/p05/p10/p25/p50/p75/p90/p95/p99 tables, skewness/kurtosis/CV/MAD, pooled all-pair distribution, every selected rank, all margins and threshold counts, hub top20, mutual top5/top10, per-query Spearman sign distributions, numeric probes, all source hashes and extreme inventories are suitable for appendix/internal review. Candidate-count boundary proxies require care because they summarize evaluation-center support, not a true Seoul administrative boundary. Multiple diagnostics are exploratory; no multiple-testing or significance claims are made.''')
    add('20. Limitations and Interpretation Boundaries','''1. No externally validated relevance exists. These measurements cannot establish retrieval accuracy or semantic correctness.
2. The existing accepted FM and evaluation embeddings are the source of truth; the audit does not assess new model training, alternative checkpoints, augmentation robustness, or generalization beyond this evaluation set.
3. Distance is EPSG:5186 planar center distance, matching accepted implementation. Do not describe it as great-circle/geodesic distance. The exact 2km edge has synthetic rather than observed-data coverage.
4. Float32 score ties and near ties can depend on the pinned numerical implementation. Exact accepted-GEMV parity takes priority; the float64 probe is limited to 33 predetermined queries.
5. Exact and near duplicate representations, especially empty-object cases, merit inspection. No raw P3 scene payload was re-extracted or new inference run to attribute the cause. Individual prepared-original payload files were not all rehashed; their accepted manifests, IDs, source bindings and key inference/code/checkpoint hashes were verified.
6. All-pair rows and nearby overlapping scenes are statistically dependent. Population summaries are not confidence estimates. Paired effects are descriptive and no p-values were calculated.
7. Fixed top5/top10 reciprocity uses deterministic tie-breaking; alternative tied-neighbor set definitions could differ and were not substituted.
8. Candidate-count edge proxies use the evaluation-center convex hull, not a polygon boundary. Spatial artifacts support future visualization without spatial-cause claims.
9. Old S10 subset viewers remain subset viewers. They were only used as lineage/parity references; all reported population statistics use all 9,000 queries.
10. Pilot and the earlier full audit outputs remain isolated. An earlier candidate histogram did not cover the lowest Non-local scores; the current run fixes the plotting range. Its scientific statistics were unchanged. Use only the current directory below.
11. No research targets changed; target-specific checks and network HTML regeneration were not run. No supervised external labels, nonlinear density bandwidth selection, effective-neighbor temperature metric or inferential tests were introduced.
12. Current source artifacts were not overwritten. New audit outputs are separate, and temporary disk-backed pair arrays were removed by the owning script after summarization. No data/checkpoints/store files were added to Git, and no commit/push occurred.''')
    artifact_rows=[]
    for p in sorted(o.iterdir()):
        if p.is_file():artifact_rows.append(dict(file=p.name,bytes=p.stat().st_size))
    add('21. Exact Artifact Paths and Reproduction Command',f'''Machine-readable output: `{o}`.

Figures: `{o}/figures`.

Log: `/members/dhnyu/fuse/logs/20260924_0352_fm_9000_retrieval_behavior_audit.log`.

Report: `{a.report.resolve()}`.

Code: `/members/dhnyu/fuse/scripts/audit_fm_9000_retrieval.py`, `/members/dhnyu/fuse/scripts/validate_fm_9000_retrieval_audit.py`, `/members/dhnyu/fuse/scripts/report_fm_9000_retrieval_audit.py`. The producer imports only read-only lineage helpers from `python/s10_extreme_rank1.py`; copies of producer/helper/config are in `reproduction/`. Source hashes and package versions are pinned in the audit manifest. No random sampling occurs in the population computation; the float64 probe and independent checks use deterministic index sequences, so no random seed is required.

Run from `/members/dhnyu/fuse`, selecting a **new** output directory (existing output paths are rejected):

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python scripts/audit_fm_9000_retrieval.py --fixture-only
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python scripts/audit_fm_9000_retrieval.py --output /mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/fm_retrieval_behavior/NEW_RUN
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/validate_fm_9000_retrieval_audit.py /mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/fm_retrieval_behavior/NEW_RUN
python scripts/report_fm_9000_retrieval_audit.py /mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/fm_retrieval_behavior/NEW_RUN --report reports/NEW_KST_TIMESTAMP_fm_9000_scene_retrieval_behavior_audit.md
```

All CSV/Parquet statistics are full precision; report tables are rounded for reading. Main outputs and checksums:

'''+table(pd.DataFrame(artifact_rows))+ '\n\nFinal judgement: **YES**, sufficient descriptive material to write Section 5.3.2 after human review. **PASS WITH CONDITIONS** is not a model-quality verdict. Final manuscript statistics and figures remain the author’s choice.')
    a.report.parent.mkdir(parents=True,exist_ok=True)
    with a.report.open('x') as f:f.write('\n'.join(sections))
    print(a.report.resolve())

if __name__=='__main__':main()
