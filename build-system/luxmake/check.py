# SPDX-FileCopyrightText: 2025 Authors (see AUTHORS.txt)
#
# SPDX-License-Identifier: Apache-2.0

"""Check whether requirements are installed."""

import shutil
import subprocess
import re
from dataclasses import dataclass

from .utils import logger, fail

@dataclass
class Require:
    name: str
    min_version: tuple
    mandatory: bool


REQUIREMENTS = (
    Require("conan", None, True),
    Require("wheel", None, True),
    Require("cmake", (3, 29), True),
    Require("git", None, True),
    Require("act", None, False),
    Require("gh", None, False),
)



def check(name, min_version=None, mandatory=True):
    """Check whether an app exists and whether its version is correct."""

    def error(*args):
        log = logger.error if mandatory else logger.warning
        log(*args)
        return not mandatory

    # Existence
    if not (app := shutil.which(name)):
        return error("'%s' is missing!", name)

    # Get version
    result = subprocess.run(
        [app, "--version"],
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip() or result.stderr.strip()
    # Match version patterns like 1.2.3, 4.5, 2.0.1-alpha, etc.
    match = re.search(r'\d+\.\d+(?:\.\d+)?(?:[-.\w]*)?', output)
    if match:
        version = match.group(0)
        if '-' in version:
            version, *_ = version.rpartition("-")
        version = tuple(int(i) for i in version.split("."))
        version_str = ".".join(str(i) for i in version)
    else:
        version = None
        version_str = None

    # Check Version, if necessary
    if min_version:
        min_version_str = ".".join(str(i) for i in min_version)
        if not version:
            return error("Cannot read '%s' version", name)
        if version < min_version:
            return error(
                "'%s': installed version ('%s') is lower than required ('%s')",
                app,
                version_str,
                min_version_str,
            )
    if version_str:
        logger.info("'%s' - Found '%s', version '%s'", name, app, version_str)
    else:
        logger.info("'%s' - Found '%s'", name, app)

    return True


def check_requirements():
    """Check all requirements."""
    logger.info("Checking requirements")
    checks = (
        check(req.name, req.min_version, req.mandatory) for req in REQUIREMENTS
    )
    if not all(checks):
        fail("Some mandatory requirements are missing. Please check...")
    logger.info("Requirements - pass")
