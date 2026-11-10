"""Offline-capable pipeline entrypoint. Full logic lands in later commits."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Home battery payback pipeline")
    parser.add_argument("--from-snapshot", action="store_true")
    parser.parse_args()
    print("pipeline skeleton ok")


if __name__ == "__main__":
    main()
