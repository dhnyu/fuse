"""Run one isolated, pilot-gated supplementary retrieval target stage."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import retrieval_gallery_pipeline as pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("authority", "spatial", "cache", "prepared", "geometry", "inference",
                                          "union", "rankings", "inspector", "validate", "accept"))
    parser.add_argument("--parent")
    parser.add_argument("--evidence")
    parser.add_argument("--config", default="config/retrieval_gallery.yml")
    args = parser.parse_args()
    if args.stage == "authority":
        if not args.evidence:
            parser.error("authority requires reviewed pilot evidence")
        result = pipeline.authority(args.config, args.evidence)
    else:
        if not args.parent:
            parser.error("stage requires its verified parent manifest")
        result = getattr(pipeline, args.stage + "_production")(args.parent)
    print(result, flush=True)


if __name__ == "__main__":
    main()
