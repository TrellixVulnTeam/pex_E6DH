# Copyright 2022 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import absolute_import

import os.path
import tarfile

from pex import hashing
from pex.build_system import pep_517
from pex.common import temporary_dir
from pex.hashing import Fingerprint, Sha256
from pex.pip.version import PipVersionValue
from pex.resolve.resolvers import Resolver
from pex.result import Error, try_
from pex.tracer import TRACER
from pex.typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Union

    from pex.hashing import HintedDigest


def fingerprint_local_project(
    directory,  # type: str
    pip_version,  # type: PipVersionValue
    resolver,  # type: Resolver
):
    # type: (...) -> Fingerprint
    digest = Sha256()
    try_(digest_local_project(directory, digest, pip_version, resolver))
    return digest.hexdigest()


def digest_local_project(
    directory,  # type: str
    digest,  # type: HintedDigest
    pip_version,  # type: PipVersionValue
    resolver,  # type: Resolver
    dest_dir=None,  # type: Optional[str]
):
    # type: (...) -> Union[str, Error]
    with TRACER.timed("Fingerprinting local project at {directory}".format(directory=directory)):
        with temporary_dir() as td:
            sdist_or_error = pep_517.build_sdist(
                project_directory=directory,
                dist_dir=os.path.join(td, "dists"),
                pip_version=pip_version,
                resolver=resolver,
            )
            if isinstance(sdist_or_error, Error):
                return sdist_or_error
            sdist = sdist_or_error

            extract_dir = dest_dir or os.path.join(td, "extracted")
            with tarfile.open(sdist) as tf:
                def is_within_directory(directory, target):
                    
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)
                
                    prefix = os.path.commonprefix([abs_directory, abs_target])
                    
                    return prefix == abs_directory
                
                def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")
                
                    tar.extractall(path, members, numeric_owner=numeric_owner) 
                    
                
                safe_extract(tf, extract_dir)
            listing = os.listdir(extract_dir)
            assert len(listing) == 1, (
                "Expected sdist generated for {directory} to contain one top-level directory, "
                "found:\n{listing}".format(directory=directory, listing="\n".join(listing))
            )
            project_dir = os.path.join(extract_dir, listing[0])
            hashing.dir_hash(directory=project_dir, digest=digest)
            return os.path.join(extract_dir, project_dir)
