"""FM-only S11 production stages; none run merely by importing this module."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from representation_analysis import file_sha256, cosine_block, eligibility, band_indices
from s11_artifacts import (assert_population, configuration, load_bundle, payload,
    publish, read_json, require, write_json)
from s11_inputs import verify_inputs
from s11_descriptors import p3_index

def accepted_parents(ctx):
    contract,lock,execution=configuration()
    x,centers,ids=verify_inputs(contract,lock)
    p3_index()
    def build(stage):
        write_json(stage/"parents.json",{"s10":lock["parents"],"p3":execution["p3_pins"],
            "embedding_stage":"pre-contrastive-head scene_embedding; accepted S10 source verified",
            "checkpoint_id":lock["checkpoint_id"],"selected_epoch":60})
        pq.write_table(pa.table({"scene_id":ids,"center_x":centers[:,0],"center_y":centers[:,1]}),stage/"population.parquet")
        assert_population(pq.read_table(stage/"population.parquet")["scene_id"].to_pylist(),ids)
        return {"scene_count":9000,"dimension":256,"original":True,"configuration_id":"cmp_FM"}
    paths=[p["path"] for p in lock["parents"].values()]+[p["path"] for p in execution["p3_pins"].values()]
    return publish(ctx,"accepted_parents","parents",build,paths)

def read_population(parent_manifest):
    load_bundle(parent_manifest,"accepted_parents")
    contract,lock,_=configuration()
    # Exact original accepted bytes; no normalization/re-embedding.
    require(file_sha256(lock["parents"]["fm_vectors"]["path"])==lock["parents"]["fm_vectors"]["sha256"],"EMBEDDING_HASH")
    x=np.load(lock["parents"]["fm_vectors"]["path"],mmap_mode="r",allow_pickle=False)
    table=pq.read_table(payload(parent_manifest,"population.parquet"))
    ids=table["scene_id"].to_pylist()
    centers=np.column_stack([table["center_x"].to_numpy(),table["center_y"].to_numpy()])
    require(x.shape==(9000,256) and ids==sorted(set(ids)) and len(ids)==9000,"ACCEPTED_POPULATION")
    return x,centers,ids

def illustrations_figure(selected, stage):
    """Original geometry sketches; hash-verified P3 bytes, no scene replacement."""
    import tarfile
    import pyarrow.compute as pc
    import shapely
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath
    index=p3_index(); root=Path(configuration()[2]["p3_root"])
    figure,axes=plt.subplots(3,3,figsize=(10,10),squeeze=False)
    for ax in axes.flat:
        ax.set_visible(False)
    grouped={}
    for selected_row in selected:
        scene=selected_row["scene_id"]; r=index[scene]
        grouped.setdefault(r["branch_id"],[]).append(selected_row)
    for branch, selection in grouped.items():
        spec=index[selection[0]["scene_id"]]; source=root/"shards"/branch/spec["payload_filename"]
        require(file_sha256(source)==spec["payload_sha256"],"ILLUSTRATION_P3_HASH")
        with tarfile.open(source,"r:") as tar:
            tables={name:pq.read_table(pa.BufferReader(tar.extractfile("vector/"+name+"_observed.parquet").read())) for name in ("building","road","poi")}
            raster=pq.read_table(pa.BufferReader(tar.extractfile("raster/scene_raster_index.parquet").read()))
        for selected_row in selection:
            scene=selected_row["scene_id"]; ax=axes[2-selected_row["cell_y"],selected_row["cell_x"]];ax.set_visible(True)
            extent=raster.filter(pc.equal(raster["scene_id"],scene)).to_pylist()[0]
            for name,table in tables.items():
                geometries=shapely.from_wkb(table.filter(pc.equal(table["scene_id"],scene))["observed_geometry"].to_pylist())
                for geometry in geometries:
                    pieces=list(geometry.geoms) if hasattr(geometry,"geoms") else [geometry]
                    for g in pieces:
                        if name=="building":
                            paths=[]
                            for ring in [g.exterior,*g.interiors]:
                                xy=np.asarray(ring.coords); codes=np.full(len(xy),MplPath.LINETO);codes[0]=MplPath.MOVETO;codes[-1]=MplPath.CLOSEPOLY
                                paths.append(MplPath(xy,codes))
                            ax.add_patch(PathPatch(MplPath.make_compound_path(*paths),facecolor="#777777",edgecolor="none"))
                        elif name=="road":
                            xy=np.asarray(g.coords);ax.plot(xy[:,0],xy[:,1],color="#2166ac",linewidth=.5)
                        else:
                            ax.plot(g.x,g.y,".",color="#b2182b",markersize=1)
            ax.set(xlim=(extent["xmin"],extent["xmax"]),ylim=(extent["ymin"],extent["ymax"]),aspect="equal")
            ax.set_title(scene,fontsize=6);ax.set_xticks([]);ax.set_yticks([])
    figure.suptitle("Original scene illustrations (buildings / roads / POIs); no cluster or prototype interpretation",fontsize=9)
    figure.tight_layout();figure.savefig(stage/"illustrations.pdf",metadata={"CreationDate":None,"ModDate":None});plt.close(figure)

def figures_tables(ctx, descriptor_manifest, umap_manifest, summary_manifest):
    contract,_,_=configuration()
    require(ctx["scope"]=="full","PUBLICATION_REQUIRES_FULL_POPULATION")
    def build(stage):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        coordinates=pq.read_table(payload(umap_manifest,"coordinates.parquet")).to_pydict()
        descriptors=pq.read_table(payload(descriptor_manifest,"descriptors.parquet")).to_pydict()
        assert_population(coordinates["scene_id"],descriptors["scene_id"])
        require(len(coordinates["scene_id"])==9000,"FIGURE_POPULATION")
        x,y=coordinates["x"],coordinates["y"]
        panels=contract["umap"]["panels"]
        require(read_json(payload(umap_manifest,"panels.json"))==panels,"SIX_FROZEN_PANELS")
        fig,axes=plt.subplots(2,3,figsize=(15,9))
        registry={d["id"]:d for d in read_json(payload(descriptor_manifest,"dictionary.json"))}
        for ax,panel in zip(axes.flat,panels,strict=True):
            key={"dominant_poi_l2":"poi_l2_composition","dominant_landcover":"landcover_composition"}.get(panel,panel)
            raw=descriptors[key];valid=np.array([v is not None for v in raw])
            categorical=panel.startswith("dominant_")
            colors=np.array([int(np.argmax(v)) if categorical else v for v in raw if v is not None])
            ax.scatter(np.asarray(x)[~valid],np.asarray(y)[~valid],s=2,c="#cccccc",label="undefined")
            kwargs={"cmap":"tab20" if len(registry[key].get("category_keys",[]))<=20 else "gist_ncar"} if categorical else {"cmap":"viridis"}
            if categorical:
                kwargs.update(vmin=-.5,vmax=len(registry[key]["category_keys"])-.5)
            marks=ax.scatter(np.asarray(x)[valid],np.asarray(y)[valid],s=2,c=colors,**kwargs)
            cb=fig.colorbar(marks,ax=ax)
            if categorical:
                keys=registry[key]["category_keys"];cb.set_ticks(range(len(keys)),labels=keys);cb.ax.tick_params(labelsize=5)
            ax.set_title(panel.replace("_"," "));ax.set_xlabel("UMAP 1");ax.set_ylabel("UMAP 2")
        fig.tight_layout();fig.savefig(stage/"umap_six_panels.pdf",metadata={"CreationDate":None,"ModDate":None});plt.close(fig)
        import csv
        rows=read_json(payload(summary_manifest,"summary.json"))
        with (stage/"alignment_summary.csv").open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        illustrations=read_json(payload(umap_manifest,"illustrations.json"))
        illustrations_figure(illustrations["scenes"],stage)
        write_json(stage/"figure_metadata.json",{"panels":panels,"illustrations":illustrations,
            "undefined_color":"#cccccc","categorical_ties":"first frozen category key","clustering":False})
        require(all(p.stat().st_size>0 for p in stage.iterdir()),"PUBLICATION_EMPTY")
        return {"panels":panels,"illustration_count":len(illustrations["scenes"]),"summary_rows":len(rows)}
    return publish(ctx,"publication","figures_tables",build,[descriptor_manifest,umap_manifest,summary_manifest])

def scientific_acceptance(ctx, parent, descriptors, umap, plan, blocks, summaries, publication):
    """Independent read-back gate. Not called in the implementation phase."""
    require(ctx["scope"]=="full","NO_PILOT_SCIENTIFIC_ACCEPTANCE")
    inputs=[parent,descriptors,umap,plan,*blocks,summaries,publication]
    for m in inputs:
        require(load_bundle(m)["context"]==ctx,"ACCEPTANCE_CONTEXT")
    x,centers,ids=read_population(parent)
    require(load_bundle(descriptors)["metadata"]["scene_count"]==9000 and
            load_bundle(umap)["metadata"]["scene_count"]==9000 and
            load_bundle(summaries)["metadata"]["query_count"]==9000,"SCIENTIFIC_POPULATION")
    assert_population(pq.read_table(payload(descriptors,"descriptors.parquet"))["scene_id"].to_pylist(),ids)
    assert_population(pq.read_table(payload(umap,"coordinates.parquet"))["scene_id"].to_pylist(),ids)
    from s11_alignment import descriptor_arrays,validate_metrics
    from s11_descriptors import extract_records
    import tempfile
    from scipy.stats import spearmanr
    from threadpoolctl import threadpool_limits
    arrays=descriptor_arrays(descriptors,ids,"full")
    positions=[0,4499,8999]
    checks=0; band_checks=0; null_checks=0
    for q in positions:
        block=next(m for m in blocks if q in load_bundle(m)["metadata"]["positions"])
        metrics=pq.read_table(payload(block,"metrics.parquet"),filters=[("query_index","=",q)]).to_pylist()
        validate_metrics(metrics,ids,[q],list(arrays))
        with threadpool_limits(limits=1):
            reference=x @ x[q]
        require(np.array_equal(reference,cosine_block(x,[q])[0]),"ACCEPTANCE_GEMV_PARITY")
        _,modes=eligibility(centers,[q])
        saved_bands=pq.read_table(payload(block,"bands.parquet"),filters=[("query_index","=",q)]).to_pylist()
        lookup={}
        from representation_analysis import band_positions
        for mode,mask in modes.items():
            eligible=np.flatnonzero(mask[0]);order=eligible[np.lexsort((np.array(ids)[eligible],-reference[eligible]))]
            ranks=band_positions(np.array([len(order)]))
            for name,rank in ranks.items():
                lookup[(mode,name)]=order[rank[0]-1]
            for row in (r for r in saved_bands if r["mode"]==mode):
                candidate=order[row["rank"]-1]
                require(row["candidate_scene_id"]==ids[candidate] and row["cosine"]==float(reference[candidate]),"INDEPENDENT_BAND_RANKING")
                band_checks+=1
        for r in metrics:
            v,valid=arrays[r["descriptor"]]; mask=modes[r["mode"]][0]&valid&valid[q]
            diff=np.abs(v-v[q]) if v.ndim==1 else np.linalg.norm(v-v[q],axis=1)
            if r["region"]=="rho":
                s=reference[mask];d=diff[mask]
                reason="fewer_than_two_valid_pairs" if len(d)<2 else "constant_similarity" if np.ptp(s)==0 else "constant_difference" if np.ptp(d)==0 else None
                require(r["null_reason"]==reason and r["valid_count"]==int(mask.sum()),"INDEPENDENT_RHO_SUPPORT")
                if reason:
                    require(r["value"] is None,"INDEPENDENT_NULL_RHO");null_checks+=1
                else:
                    independent=float(spearmanr(s,d).statistic)
                    require(np.isclose(independent,r["value"],rtol=0,atol=2e-12),"INDEPENDENT_RHO")
                    checks+=1
            else:
                candidates=lookup[(r["mode"],r["region"])];ok=valid[candidates]&valid[q]
                require(r["valid_count"]==int(ok.sum()),"INDEPENDENT_BAND_SUPPORT")
                if np.any(ok):
                    require(np.isclose(np.mean(diff[candidates[ok]]),r["value"],rtol=1e-12,atol=2e-10),"INDEPENDENT_BAND_MEAN")
                else:
                    require(r["value"] is None,"INDEPENDENT_BAND_NULL")
    # Original observations are re-read in fresh R processes for three fixed
    # scenes, independently of descriptor shard/merge outputs and target cache.
    index=p3_index();execution=configuration()[2]
    for q in positions:
        scene=ids[q];item=index[scene]
        spec={"scene_ids":[scene],"path":str(Path(execution["p3_root"])/"shards"/item["branch_id"]/item["payload_filename"]),"sha256":item["payload_sha256"]}
        with tempfile.TemporaryDirectory(prefix=".acceptance-readback-",dir=ctx["root"]) as temporary:
            original=extract_records(spec,temporary)[0]["descriptors"]
        for name,(v,valid) in arrays.items():
            value=original[name]["value"]
            require(bool(valid[q])==(value is not None),"ACCEPTANCE_DESCRIPTOR_VALIDITY")
            if value is not None:
                require(np.array_equal(v[q],value),"ACCEPTANCE_DESCRIPTOR_RECOMPUTATION")
    contract,lock,_=configuration();verify_inputs(contract,lock)
    def build(stage):
        write_json(stage/"acceptance.json",{"status":"PASS","scene_count":9000,"query_count":9000,
            "descriptors":22,"configuration":"cmp_FM","independent_rho_checks":checks,
            "independent_query_positions":positions,"no_clustering":True,"composite_score":False,
            "independent_band_checks":band_checks,"independent_null_rho_checks":null_checks,
            "descriptor_recomputed_scenes":3,
            "monotonicity_is_acceptance_criterion":False,"parents_reverified":True})
        return {"scientific_acceptance":True,"viewer_required":False}
    return publish(ctx,"scientific_acceptance","accepted",build,inputs)
