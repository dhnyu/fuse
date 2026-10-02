"""B6 artifact audit is observational and catches ambiguous component lineage."""
import importlib.util
from pathlib import Path
import pandas as pd
from shapely.geometry import MultiLineString

spec = importlib.util.spec_from_file_location('b6_artifact_audit', Path(__file__).resolve().parents[2] / 'python/b6_artifact_audit.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_component_ownership_complete_and_missing():
    geometry = pd.DataFrame([{'candidate_id': 'v', 'local_entity_id': 1,
        'geometry_wkb': MultiLineString([[(0, 0), (1, 0)], [(1, 0), (2, 0)]]).wkb}])
    rows = pd.DataFrame([{'candidate_id':'v', 'receiver_local_entity_id':1,
        'component_index':i, 'component_source_road_id':str(i)} for i in range(2)])
    assert m.component_ownership(rows, geometry)['component_ownership_pass']
    assert not m.component_ownership(rows.iloc[:1], geometry)['component_ownership_pass']

def test_component_ownership_ambiguous_and_query_identity():
    geometry = pd.DataFrame([{'query_id': 'v', 'local_entity_id': 1,
        'geometry_wkb': MultiLineString([[(0, 0), (1, 0)]]).wkb}])
    rows = pd.DataFrame([{'query_id':'v', 'receiver_local_entity_id':1,
        'component_index':0, 'component_source_road_id':str(i)} for i in range(2)])
    assert not m.component_ownership(rows, geometry)['component_ownership_pass']

def test_no_model_or_mutation_imports():
    import ast
    tree = ast.parse(Path(m.__file__).read_text())
    imported = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(x.startswith(('torch', 'training_', 'model_')) for x in imported)
