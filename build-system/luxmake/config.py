# SPDX-FileCopyrightText: 2025 Authors (see AUTHORS.txt)
#
# SPDX-License-Identifier: Apache-2.0

"""Config command."""

from .constants import INSTALL_DIR, SOURCE_DIR, BINARY_DIR
from .utils import run_cmake, fail


def config(
    _,
):
    """CMake config."""
    # Check whether presets exist
    presets = BINARY_DIR / "build" / "generators" / "CMakePresets.json"
    if not presets.exists():
        fail(
            "Cannot find presets file ('%s'). "
            "Have you run 'make deps' beforehand?",
            str(presets.absolute()),
        )

    # Run command
    cmd = [
        "--preset conan-default",
        f"-DCMAKE_INSTALL_PREFIX={str(INSTALL_DIR)}",
        f"-S {str(SOURCE_DIR)}",
    ]
    run_cmake(cmd)
