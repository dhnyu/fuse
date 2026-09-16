"""Model-independent original-scene SVG cache; never reads embeddings or scores.

Reuses current model_data original extraction and the augmentation inspector's
observed_geometry convention. North-up EPSG:5186, fixed 500 m scene frame.
"""
from pathlib import Path
import html
import shapely
from shapely.affinity import translate
from retrieval_artifacts import digest, file_hash, publish_bytes

PARAMETERS = {"width_m": 500, "north_up": True, "B": "#667085", "R": "#e4a11b",
              "P": "#c83e63", "background": "#f4f6f3", "renderer": "observed-vector-v1"}


def render_scene(scene, source_identity, root):
    identity = {"scene_id": scene["scene_id"], "source_scene_data_identity": source_identity,
                "rendering_code_hash": file_hash(__file__), "rendering_parameter_hash": digest(PARAMETERS)}
    key = digest(identity)
    x, y = scene["center"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" role="img"><title>{html.escape(scene["scene_id"])}</title>',
             '<rect width="500" height="500" fill="#f4f6f3"/><g transform="translate(0 500) scale(1 -1)">']
    for row in scene["entities"]:
        shape = translate(shapely.from_wkb(bytes(row["observed_geometry"])), 250 - x, 250 - y)
        color = PARAMETERS[row["entity_type"]]
        # Geometry serializes numerical coordinates only; labels are escaped above.
        parts.append(shape.svg(scale_factor=0.4, fill_color=color) if shape.geom_type in ("Polygon", "MultiPolygon", "Point", "MultiPoint")
                     else shape.svg(scale_factor=0.4, stroke_color=color))
    parts.append('</g><text x="480" y="20" font-size="13">N</text></svg>')
    path = Path(root) / (key + ".svg")
    publish_bytes(path, "".join(parts).encode())
    return {**identity, "cache_id": key, "path": str(path)}
