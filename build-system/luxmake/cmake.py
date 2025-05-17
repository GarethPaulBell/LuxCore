# SPDX-FileCopyrightText: 2025 Authors (see AUTHORS.txt)
#
# SPDX-License-Identifier: Apache-2.0

"""This script wraps cmake calls for LuxCore build.

It is intended to get the same behaviour between Windows and *nix os
"""

import os
import subprocess
import sys
import logging
import shutil
import argparse
import tempfile
import platform
from pathlib import (
    Path,
)
from functools import (
    cache,
)
import re
from enum import (
    Enum,
)
import json

import make_deps

# External variables
BINARY_DIR = Path(
    os.getenv(
        "LUX_BINARY_DIR",
        "out",
    )
)
SOURCE_DIR = Path(
    os.getenv(
        "LUX_SOURCE_DIR",
        os.getcwd(),
    )
)
BUILD_TYPE = os.getenv(
    "LUX_BUILD_TYPE",
    "Release",
)

# Computed variables
BUILD_DIR = BINARY_DIR / "build"
INSTALL_DIR = BINARY_DIR / "install" / BUILD_TYPE
WHEEL_BUILD_DIR = BUILD_DIR / "wheel"
WHEEL_LIB_DIR = INSTALL_DIR / "lib"  # TODO Windows, MacOS etc.
WHEEL_DIR = BINARY_DIR / "wheel"

# Logger
logger = logging.getLogger("LuxCore Build")


# Preset stuff
class PresetType(Enum):
    """CMake preset types."""

    CONFIG = "configure"
    BUILD = "build"
    TEST = "test"
    PACKAGE = "package"


PRESET_PATTERN = re.compile(r"\s*\"([a-zA-Z\-]+)\".*")


@cache
def ensure_cmake_app():
    """Ensure cmake is installed."""
    logger.debug("Looking for cmake")
    if not (res := shutil.which("cmake")):
        logger.error("CMake not found!")
        sys.exit(1)
    logger.debug(
        "CMake found: '%s'",
        res,
    )
    return res


def run_cmake(
    args,
    **kwargs,
):
    """Run cmake statement."""
    cmake_app = ensure_cmake_app()
    args = [cmake_app] + args
    logger.debug(args)
    res = subprocess.run(
        args,
        shell=False,
        check=False,
        **kwargs,
    )
    if res.returncode:
        logger.error("Error while executing cmake")
        print(res.stdout)
        print(res.stderr)
        sys.exit(1)
    return res


def config(
    _,
):
    """CMake config."""
    cmd = [
        "--preset conan-default",
        f"-DCMAKE_INSTALL_PREFIX={str(INSTALL_DIR)}",
        f"-S {str(SOURCE_DIR)}",
    ]
    run_cmake(cmd)


PRESETS = {
    "Release": "conan-release",
    "Debug": "conan-debug",
    "RelWithDebInfo": "conan-relwithdebinfo",
    "MinSizeRel": "conan-minsizerel",
}


def get_preset_from_build_type(
    build_type,
):
    """Get conan preset from build type."""
    try:
        preset = PRESETS[build_type]
    except KeyError:
        logger.error(
            "Unknown build type '%s'",
            build_type,
        )
        logger.error(
            "Valid values (case sensitive) are: %s",
            PRESETS.keys(),
        )
        sys.exit(1)
    if preset not in (presets := get_presets(PresetType.BUILD)):
        logger.error(
            "Preset '%s' missing",
            preset,
        )
        logger.error(
            "Available presets: %s",
            presets,
        )
    return preset


def build(
    args,
):
    """CMake build."""
    preset = get_preset_from_build_type(BUILD_TYPE)
    cmd = [
        "--build",
        f"--preset {preset}",
        f"--target {args.target}",
    ]
    run_cmake(cmd)


def install(
    args,
):
    """CMake install."""
    cmd = [
        "--install",
        str(BUILD_DIR),
        f"--prefix {INSTALL_DIR}",
        f"--config {BUILD_TYPE}",
        f"--component {args.target}",
    ]
    run_cmake(cmd)


def build_and_install(
    args,
):
    """CMake build and install."""
    build(args)
    install(args)


def get_presets(
    preset_type: PresetType,
):
    """CMake get presets for a given type."""
    preset_type = str(preset_type.value)
    cmd = [f"--list-presets={preset_type}"]
    res = run_cmake(
        cmd,
        capture_output=True,
        text=True,
    )
    presets = [
        preset[1]
        for line in res.stdout.splitlines()
        if (preset := PRESET_PATTERN.fullmatch(line)) is not None
    ]
    return presets


def get_all_presets():
    """CMake get all presets."""
    presets = {
        preset_type.value: get_presets(preset_type)
        for preset_type in PresetType.__members__.values()
    }
    return presets


def list_presets(
    _,
):
    """List all presets."""
    print(get_all_presets())


def clean(
    _,
):
    """CMake clean."""
    for preset in get_presets(PresetType.BUILD):
        logger.info(
            "Cleaning preset '%s'",
            preset,
        )
        cmd = [
            "--build",
            f"--preset {preset}",
            "--target clean",
        ]
        run_cmake(cmd)


def clear(
    _,
):
    """Clear binary directory."""
    # We just remove the subdirectories, in order to avoid
    # unwanted removals if BINARY_DIR points to a wrong directory
    for subdir in (
        "build",
        "dependencies",
        "install",
    ):
        directory = BINARY_DIR / subdir
        logger.info(
            "Removing '%s'",
            directory,
        )
        try:
            shutil.rmtree(
                directory,
                ignore_errors=True,
            )
        except FileNotFoundError:
            logger.debug(
                "'%s' not found",
                directory,
            )


def deps(
    _,
):
    """Install dependencies."""
    make_deps.main([f"--output={BINARY_DIR}"])


def get_glibc_version():
    """
    Returns the version of glibc installed on the system, or None if it cannot be determined.
    """
    try:
        # Run ldd --version and capture the output
        result = subprocess.run(['ldd', '--version'], capture_output=True, text=True)
        output = result.stdout or result.stderr
        # Look for a version number in the output
        match = re.search(r'(\d+\.\d+(?:\.\d+)*)', output)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def make_wheel(args):
    """Build a wheel."""
    logger.warning(
        "This command builds a TEST wheel, "
        "not fully compliant to standard "
        "and only intended for test. "
        "DO NOT USE IN PRODUCTION."
    )
    # Build and install pyluxcore
    args.target = "pyluxcore"
    build_and_install(args)

    # Compute version
    build_settings_file = Path("build-system", "build-settings.json")
    with open(build_settings_file) as in_file:
        default_version = json.load(in_file)["DefaultVersion"]
    version = ".".join(default_version[i] for i in ("major", "minor", "patch"))

    # Compute tag
    vinfo = sys.version_info
    python_tag = f"cp{vinfo.major}{vinfo.minor}"
    abi_tag = python_tag
    glibc_version = get_glibc_version().replace(".", "_")
    platform_tag = f"manylinux_{glibc_version}_x86_64"
    platform_tag = f"linux_x86_64"  # TODO
    # TODO Only Linux at the moment
    tag = f"{python_tag}-{abi_tag}-{platform_tag}"

    # Destination folder
    logger.info(f"Making wheel for version '{version}' and tag '{tag}'")
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_out:
        tmp = Path(tmp)
        tmp_out = Path(tmp_out)

        # Create dist-info
        dist_info = tmp / f"pyluxcore-{version}.dist-info"
        dist_info.mkdir(exist_ok=True)

        # Compute tag
        # This tag is absolutely mendacious. Do not use in production.
        # https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/
        # Export WHEEL file
        wheel_content = f"""\
Wheel-Version: 1.0
Generator: fake 0.0.0
Root-Is-Purelib: false
Tag: {tag}
"""
        with open(dist_info / "WHEEL", 'w', encoding="utf-8") as f:
            f.write(wheel_content)

        # Copy subfolders
        shutil.copytree(
            SOURCE_DIR / "python" / "pyluxcore",
            tmp / "pyluxcore",
            dirs_exist_ok=True
        )
        shutil.copytree(
            INSTALL_DIR / "pyluxcore",
            tmp / "pyluxcore",
            dirs_exist_ok=True
        )
        shutil.copytree(
            INSTALL_DIR / "pyluxcore.libs",
            tmp / "pyluxcore.libs",
            dirs_exist_ok=True
        )


        # Pack wheel
        pack_cmd = ["wheel", "pack", tmp, "--dest-dir", str(tmp_out) ]
        proc = subprocess.run(pack_cmd, text=True)

        # Then repair
        # TODO
        logger.info("Repairing wheel")
        if platform.system() != "Linux":
            cmd = [
                "repairwheel",
                "-o",
                str(WHEEL_DIR),
                "-l",
                str(WHEEL_LIB_DIR),
                str(tmp_out / f"pyluxcore-{version}-{tag}.whl"),
            ]
        else:
            cmd = [
                "pipx",
                "run",
                "auditwheel",
                "repair",
                "--plat",
                platform_tag,
                "--wheel-dir",
                str(INSTALL_DIR / "wheel"),
                str(tmp_out / f"pyluxcore-{version}-{tag}.whl"),
            ]
        # TODO repairwheel to be installed (via pipx?) ? Or per-platform approach?
        try:
            result = subprocess.check_output(cmd, text=True)
        except subprocess.CalledProcessError as err:
            logger.error(err)
            sys.exit(1)
        logger.info(result)


def main():
    """Entry point."""
    # Set-up logger
    logger.setLevel(logging.INFO)
    logging.basicConfig(level=logging.INFO)

    # Get command-line parameters
    parser = argparse.ArgumentParser(
        prog="make",
        add_help=False,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers()

    # Dependencies
    parser_deps = subparsers.add_parser("deps")
    parser_deps.set_defaults(func=deps)

    # List Presets
    parser_presets = subparsers.add_parser("list-presets")
    parser_presets.set_defaults(func=list_presets)

    # Config
    parser_config = subparsers.add_parser("config")
    parser_config.set_defaults(func=config)

    # Build
    parser_build_and_install = subparsers.add_parser("build-and-install")
    parser_build_and_install.add_argument("target")
    parser_build_and_install.set_defaults(func=build_and_install)

    # Install
    parser_install = subparsers.add_parser("install")
    parser_install.add_argument("target")
    parser_install.set_defaults(func=install)

    # Wheel
    parser_wheel = subparsers.add_parser("wheel-test")
    parser_wheel.set_defaults(func=make_wheel)

    # Clear
    parser_clear = subparsers.add_parser("clear")
    parser_clear.set_defaults(func=clear)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose mode")
    args.func(args)


if __name__ == "__main__":
    main()
