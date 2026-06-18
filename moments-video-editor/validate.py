#!/usr/bin/env python3
"""Validate the example edit documents against editing_model.proto.

Compiles editing_model.proto into temporary Python stubs (no generated files are
committed), then parses every examples/*.textproto into a Post message. Exits
non-zero if any sample fails to parse, listing the offending file and error.

Usage:
    python3 validate.py

Requires: grpcio-tools (pip install grpcio-tools)
"""

import glob
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(HERE, "editing_model.proto")
EXAMPLES_GLOB = os.path.join(HERE, "examples", "*.textproto")


def compile_proto(out_dir):
    from grpc_tools import protoc

    rc = protoc.main([
        "protoc",
        f"--proto_path={HERE}",
        f"--python_out={out_dir}",
        PROTO,
    ])
    if rc != 0:
        raise SystemExit(f"protoc failed to compile {PROTO} (exit {rc})")


def load_pb(out_dir):
    module_path = os.path.join(out_dir, "editing_model_pb2.py")
    spec = importlib.util.spec_from_file_location("editing_model_pb2", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["editing_model_pb2"] = module
    spec.loader.exec_module(module)
    return module


def main():
    from google.protobuf import text_format

    with tempfile.TemporaryDirectory() as out_dir:
        compile_proto(out_dir)
        pb = load_pb(out_dir)

        files = sorted(glob.glob(EXAMPLES_GLOB))
        if not files:
            raise SystemExit("no example .textproto files found")

        failures = []
        for path in files:
            name = os.path.basename(path)
            try:
                with open(path) as f:
                    post = text_format.Parse(f.read(), pb.Post())
                tracks = len(post.timeline.tracks)
                assets = len(post.assets)
                print(f"  OK   {name}  (profile={pb.DocumentProfile.Name(post.profile)}, "
                      f"tracks={tracks}, assets={assets})")
            except Exception as e:  # noqa: BLE001 - report any parse error
                failures.append((name, str(e)))
                print(f"  FAIL {name}\n       {e}")

        print()
        if failures:
            print(f"{len(failures)}/{len(files)} sample(s) failed to parse.")
            return 1
        print(f"All {len(files)} samples parsed successfully.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
