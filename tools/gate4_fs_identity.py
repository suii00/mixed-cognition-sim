"""Linux no-follow directory identity primitives for Gate 4 tooling.

This module contains no publisher or workload policy.  It only pins an
absolute lexical directory path component by component and exposes the
device/inode identity of the opened directory descriptor.
"""

from __future__ import annotations

import contextlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


class Gate4FilesystemIdentityError(RuntimeError):
    """A lexical directory path or expected identity is unsafe."""


@dataclass(frozen=True)
class DirectoryIdentity:
    device: int
    inode: int

    @classmethod
    def from_descriptor(cls, descriptor: int) -> "DirectoryIdentity":
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise Gate4FilesystemIdentityError("descriptor is not a directory")
        return cls(device=metadata.st_dev, inode=metadata.st_ino)

    @classmethod
    def from_value(
        cls,
        value: Mapping[str, Any],
        context: str,
    ) -> "DirectoryIdentity":
        if not isinstance(value, Mapping) or set(value) != {"device", "inode"}:
            raise Gate4FilesystemIdentityError(f"{context} fields differ")
        device = value["device"]
        inode = value["inode"]
        if type(device) is not int or device < 0:
            raise Gate4FilesystemIdentityError(f"{context}.device is invalid")
        if type(inode) is not int or inode <= 0:
            raise Gate4FilesystemIdentityError(f"{context}.inode is invalid")
        return cls(device=device, inode=inode)

    def as_dict(self) -> dict[str, int]:
        return {"device": self.device, "inode": self.inode}


def absolute_lexical_path(path: Path | str, context: str) -> Path:
    raw = os.fspath(path)
    if not raw or "\0" in raw:
        raise Gate4FilesystemIdentityError(f"{context} is not a valid path")
    absolute = os.path.abspath(raw)
    if absolute.startswith("//"):
        raise Gate4FilesystemIdentityError(f"{context} has an unsupported root")
    return Path(absolute)


def ensure_directory(path: Path | str, context: str, mode: int = 0o755) -> Path:
    """Create missing lexical components without following a symlink."""
    absolute = absolute_lexical_path(path, context)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise Gate4FilesystemIdentityError(
            "O_NOFOLLOW and O_DIRECTORY are required for Gate 4 directories"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open("/", flags)
    try:
        for component in (part for part in absolute.parts if part != "/"):
            try:
                named = os.stat(
                    component,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode, dir_fd=descriptor)
                except FileExistsError:
                    pass
                named = os.stat(
                    component,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
                raise Gate4FilesystemIdentityError(
                    f"{context} contains an unsafe path component"
                )
            child = os.open(component, flags, dir_fd=descriptor)
            opened = os.fstat(child)
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                os.close(child)
                raise Gate4FilesystemIdentityError(
                    f"{context} changed during component creation"
                )
            os.close(descriptor)
            descriptor = child
        return absolute
    except OSError as error:
        raise Gate4FilesystemIdentityError(
            f"{context} cannot be created safely"
        ) from error
    finally:
        os.close(descriptor)


@dataclass
class PinnedDirectory:
    path: Path
    descriptors: list[int]
    components: tuple[str, ...]

    @property
    def fd(self) -> int:
        return self.descriptors[-1]

    @property
    def identity(self) -> DirectoryIdentity:
        return DirectoryIdentity.from_descriptor(self.fd)

    def assert_path_identity(self) -> None:
        root_opened = os.fstat(self.descriptors[0])
        root_named = os.stat("/", follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or (root_opened.st_dev, root_opened.st_ino)
            != (root_named.st_dev, root_named.st_ino)
        ):
            raise Gate4FilesystemIdentityError("filesystem root identity changed")
        for index, component in enumerate(self.components, start=1):
            opened = os.fstat(self.descriptors[index])
            try:
                named = os.stat(
                    component,
                    dir_fd=self.descriptors[index - 1],
                    follow_symlinks=False,
                )
            except OSError as error:
                raise Gate4FilesystemIdentityError(
                    f"pinned directory path changed: {self.path}"
                ) from error
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (named.st_dev, named.st_ino)
            ):
                raise Gate4FilesystemIdentityError(
                    f"pinned directory path changed: {self.path}"
                )

    def close(self) -> None:
        while self.descriptors:
            os.close(self.descriptors.pop())


@contextlib.contextmanager
def pin_directory(path: Path | str, context: str) -> Iterator[PinnedDirectory]:
    absolute = absolute_lexical_path(path, context)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise Gate4FilesystemIdentityError(
            "O_NOFOLLOW and O_DIRECTORY are required for Gate 4 directories"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptors: list[int] = []
    components = tuple(part for part in absolute.parts if part != "/")
    try:
        descriptors.append(os.open("/", flags))
        for component in components:
            parent_fd = descriptors[-1]
            try:
                named = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as error:
                raise Gate4FilesystemIdentityError(
                    f"{context} cannot be inspected"
                ) from error
            if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
                raise Gate4FilesystemIdentityError(
                    f"{context} contains an unsafe path component"
                )
            descriptor = os.open(component, flags, dir_fd=parent_fd)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            ):
                os.close(descriptor)
                raise Gate4FilesystemIdentityError(
                    f"{context} changed during component open"
                )
            descriptors.append(descriptor)
        pinned = PinnedDirectory(absolute, descriptors, components)
        pinned.assert_path_identity()
        try:
            yield pinned
        finally:
            pinned.close()
    except Exception:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)
        raise
