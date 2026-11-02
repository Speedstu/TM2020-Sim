#!/usr/bin/env python3
"""Backward-compatible command for Trackmania pose manifest generation.

Earlier V1 assumptions incorrectly swapped X/Z and omitted process start time.
V1/V2 manifests are archived and must NEVER be fed to the C++ pose reader.
This entrypoint uses the corrected V3 manifest generator only.
"""
from generate_pose_manifest_v3 import main

if __name__ == "__main__":
    main()
