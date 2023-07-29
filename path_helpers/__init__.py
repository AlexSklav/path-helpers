#
# Copyright (c) 2011 Christian Fobel
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

""" path.py - An object representing a path to a file or directory.

Original author:
 Jason Orendorff <jason.orendorff\x40gmail\x2ecom>

Contributors:
 Mikhail Gusarov <dottedmag@dottedmag.net>
 Christian Fobel <christian@fobel.net>

Example:

from path_helpers import path
d = path('/home/guido/bin')
for f in d.files('*.py'):
    f.chmod(0o755)

This module is an implementation of the former path module by Christian Fobel for Python 3.6 or later.
"""

import errno
import fnmatch
import hashlib
import os
import pickle
import platform
import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Iterable, Union, List, Optional, Any, Hashable, Tuple, Set

from ._version import get_versions

__version__ = get_versions()['version']
del get_versions

__all__ = ['path']

# Platform-specific support for path.owner
if os.name == 'nt':
    try:
        import win32security
    except ImportError:
        win32security = None
    import ntfsutils
    import ntfsutils.junction
    import ntfsutils.hardlink
else:
    try:
        import pwd
    except ImportError:
        pwd = None


def open_path(path_):
    """
    Open file/directory using default application.

    Adapted from [here][1].

    [1]: http://stackoverflow.com/questions/6631299/python-opening-a-folder-in-explorer-nautilus-mac-thingie#16204023
    """
    if platform.system() == "Windows":
        subprocess.run(['start', path_], shell=True)
    elif platform.system() == "Darwin":
        subprocess.run(['open', path_])
    else:
        subprocess.run(['xdg-open', path_])


class TreeWalkWarning(Warning):
    pass


class path(Path):
    """ Represents a filesystem path.

    For documentation on individual methods, consult their
    counterparts in os.path.
    """
    _flavour = type(Path())._flavour

    # --- Special Python methods.
    # def __repr__(self) -> str:
    #     return f'path({super().__repr__()})'

    # Adding a path and a string yields a path.
    def __add__(self, more: str) -> 'Path':
        return self / more

    def __radd__(self, other: str) -> 'Path':
        if isinstance(other, str):
            return self.__add__(other)
        else:
            return NotImplemented

    @classmethod
    def getcwd(cls) -> Path:
        """ Return the current working directory as a path object. """
        return cls.cwd()

    # --- Operations on path strings.

    def abspath(self) -> Path:
        return self.absolute()

    def normcase(self) -> Path:
        return self.resolve()

    def normpath(self) -> Path:
        return self.resolve()

    def realpath(self, strict: bool = False) -> Path:
        return self.resolve(strict=strict)

    def expandvars(self) -> Path:
        return self.__class__(os.path.expandvars(self))

    def dirname(self) -> Path:
        return self.parent

    def basename(self) -> str:
        return self.name

    def expand(self) -> Path:
        """ Clean up a filename by calling expandvars(),
        expanduser(), and normpath() on it.

        This is commonly everything needed to clean up a filename
        read from a configuration file, for example.
        """
        return self.expandvars().expanduser().normpath()

    def _get_namebase(self) -> str:
        return self.stem

    @property
    def namebase(self) -> str:
        """ The same as path.name, but with one file extension stripped off.

        For example, path('/home/guido/python.tar.gz').name     == 'python.tar.gz',
        but          path('/home/guido/python.tar.gz').namebase == 'python.tar'
        """
        return self._get_namebase()

    def _get_ext(self) -> str:
        return self.suffix

    @property
    def ext(self) -> str:
        """ The file extension, for example '.py'. """
        return self._get_ext()

    def _get_drive(self) -> Path:
        return Path(self.drive)

    def splitpath(self) -> Tuple[Path, str]:
        """ p.splitpath() -> Return (p.parent, p.name). """
        return self.parent, self.name

    def splitdrive(self) -> Tuple[Path, Path]:
        """ p.splitdrive() -> Return (p.drive, <the rest of p>).

        Split the drive specifier from this path.  If there is
        no drive specifier, p.drive is empty, so the return value
        is simply (path(''), p).  This is always the case on Unix.
        """
        return Path(self.drive), Path(os.sep.join(self.parts[1:]))

    def splitext(self) -> Tuple[Path, str]:
        """ p.splitext() -> Return (p.stripext(), p.ext).

        Split the filename extension from this path and return
        the two parts.  Either part may be empty.

        The extension is everything from '.' to the end of the
        last path segment.  This has the property that if
        (a, b) == p.splitext(), then a + b == p.
        """
        return Path(self.stem), self.suffix

    def stripext(self) -> Path:
        """ p.stripext() -> Remove one file extension from the path.

        For example, path('/home/guido/python.tar.gz').stripext()
        returns path('/home/guido/python.tar').
        """
        return Path(self.stem)

    if hasattr(os.path, 'splitunc'):
        def splitunc(self) -> Tuple[Path, str]:
            unc, rest = os.path.splitunc(self)
            return Path(unc), rest

        def _get_uncshare(self) -> Path:
            unc, _ = os.path.splitunc(self)
            return Path(unc)

        @property
        def uncshare(self) -> Path:
            """ The UNC mount point for this path.
            This is empty for paths on local drives. """
            return self._get_uncshare()

    def splitall(self) -> List[str]:
        r""" Return a list of the path components in this path.

        The first item in the list will be a path.  Its value will be
        either os.curdir, os.pardir, empty, or the root directory of
        this path (for example, '/' or 'C:\\').  The other items in
        the list will be strings.

        path.path.joinpath(*result) will yield the original path.
        """
        return list(self.parts)

    def relpathto(self, dest: Union[str, Path]) -> Path:
        return self.relative_to(dest)

    def relpath(self) -> Path:
        """ Return this path as a relative path,
        based from the current working directory.
        """
        return self.relpathto(self.cwd())

    # --- Listing, searching, walking, and matching

    def listdir(self, pattern: Optional[str] = None) -> List[Path]:
        """Return a list of items in this directory.

        Use D.files() or D.dirs() instead if you want a listing
        of just files or just subdirectories.

        The elements of the list are path objects.

        With the optional 'pattern' argument, this only lists
        items whose names match the given pattern.
        """
        if self.is_dir():
            pt = self
        else:
            pt = self.parent

        if pattern is None:
            return list(pt.iterdir())
        else:
            return list(pt.glob(pattern))

    def dirs(self, pattern: Optional[str] = None) -> List[Path]:
        """Return a list of this directory's subdirectories.

        The elements of the list are path objects.
        This does not walk recursively into subdirectories
        (but see path.walkdirs).

        With the optional 'pattern' argument, this only lists
        directories whose names match the given pattern.  For
        example, d.dirs('build-*').
        """
        return [p for p in self.listdir(pattern) if p.is_dir()]

    def files(self, pattern: Optional[str] = None) -> List[Path]:
        """Return a list of the files in this directory.

        The elements of the list are path objects.
        This does not walk into subdirectories (see path.walkfiles).

        With the optional 'pattern' argument, this only lists files
        whose names match the given pattern.  For example,
        d.files('*.pyc').
        """

        return [p for p in self.listdir(pattern) if p.is_file()]

    def fnmatch(self, pattern: str) -> bool:
        """ Return True if self.name matches the given pattern.

        pattern - A filename pattern with wildcards,
            for example '*.py'.
        """
        return fnmatch.fnmatch(self.name, pattern)

    def walk(self, pattern: Optional[str] = None, errors: str = 'strict') -> Iterable[Path]:
        """Iterate over files and subdirs, recursively.

        The iterator yields path objects naming each child item of
        this directory and its descendants.  This requires that
        D.isdir().

        This performs a depth-first traversal of the directory tree.
        Each directory is returned just before all its children.

        The errors= keyword argument controls behavior when an
        error occurs.  The default is 'strict', which causes an
        exception.  The other allowed values are 'warn', which
        reports the error via warnings.warn(), and 'ignore'.
        """
        if errors not in ('strict', 'warn', 'ignore'):
            raise ValueError("invalid errors parameter")

        try:
            child_list = self.listdir()
        except Exception as e:
            if errors == 'ignore':
                return
            elif errors == 'warn':
                warnings.warn(f"Unable to list directory '{self}': {e}", TreeWalkWarning)
                return
            else:
                raise e

        for child in child_list:
            if pattern is None or child.fnmatch(pattern):
                yield child
            try:
                isdir = child.is_dir()
            except Exception as e:
                if errors == 'ignore':
                    isdir = False
                elif errors == 'warn':
                    warnings.warn(f"Unable to access '{child}': {e}", TreeWalkWarning)
                    isdir = False
                else:
                    raise e

            if isdir:
                for item in child.walk(pattern, errors):
                    yield item

    def walkdirs(self, pattern: Optional[str] = None, errors: str = 'strict',
                 ignore: Union[str, Iterable[str]] = None) -> Iterable[Path]:
        """Iterate over subdirs, recursively.

        With the optional 'pattern' argument, this yields only
        directories whose names match the given pattern.  For
        example, mydir.walkdirs('*test') yields only directories
        with names ending in 'test'.

        The errors= keyword argument controls behavior when an
        error occurs.  The default is 'strict', which causes an
        exception.  The other allowed values are 'warn', which
        reports the error via warnings.warn(), and 'ignore'.

        The optional argument 'ignore' ignores any directory or file that
        is specified using one or more regular expression patterns.  If ignore
        is iterable, each pattern will be iterated through.  Otherwise, ignore
        is assumed to be a single string regular expression pattern.
        """
        if errors not in ('strict', 'warn', 'ignore'):
            raise ValueError("invalid errors parameter")

        def ignore_match(x: Path) -> bool:
            if ignore is not None:
                ignore_list = ignore if isinstance(ignore, Iterable) else [ignore]
                for ip in ignore_list:
                    if re.search(ip, str(x)):
                        return True
            return False

        if ignore_match(self):
            return

        try:
            dirs = self.dirs()
        except Exception as e:
            if errors == 'ignore':
                return
            elif errors == 'warn':
                warnings.warn(f"Unable to list directory '{self}': {e}", TreeWalkWarning)
                return
            else:
                raise e

        for child in dirs:
            if pattern is None or child.fnmatch(pattern):
                if not ignore_match(child):
                    yield child
            for subsubdir in child.walkdirs(pattern, errors, ignore):
                yield subsubdir

    def walkfiles(self, pattern: Optional[str] = None, errors: str = 'strict',
                  ignore: Union[str, Iterable[str]] = None):
        """Iterate over files in the path, recursively.

        The optional argument 'pattern' limits the results to files
        with names that match the pattern. For example,
        mydir.walkfiles('*.tmp') yields only files with the .tmp
        extension.

        The optional argument 'ignore' ignores any directory or file that
        is specified using one or more regular expression patterns. If ignore
        is iterable, each pattern will be iterated through. Otherwise, ignore
        is assumed to be a single string regular expression pattern.
        """
        if errors not in ('strict', 'warn', 'ignore'):
            raise ValueError("Invalid errors parameter")

        def ignore_match(x: Path) -> bool:
            if ignore is not None:
                ignore_list = ignore if isinstance(ignore, Iterable) else [ignore]
                for ip in ignore_list:
                    if re.search(ip, str(x)):
                        return True
            return False

        if ignore_match(self):
            return

        try:
            child_list = self.listdir()
        except Exception as e:
            if errors == 'ignore':
                return
            elif errors == 'warn':
                warnings.warn(f"Unable to list directory '{self}': {e}", TreeWalkWarning)
                return
            else:
                raise e

        for child in child_list:
            try:
                isfile = child.is_file()
                isdir = child.is_dir()
            except Exception as e:
                if errors == 'ignore':
                    continue
                elif errors == 'warn':
                    warnings.warn(f"Unable to access '{child}': {e}", TreeWalkWarning)
                    continue
                else:
                    raise e

            if isfile:
                if pattern is None or child.fnmatch(pattern):
                    if not ignore_match(child):
                        yield child
            elif isdir:
                for f in child.walkfiles(pattern, errors, ignore):
                    yield f

    # --- Reading or writing an entire file at once.

    def bytes(self) -> bytes:
        """ Open this file, read all bytes, return them as a string. """
        with self.open('rb') as f:
            return f.read()

    def write_bytes(self, bytes_to_write: bytes, append: bool = False) -> None:
        """ Open this file and write the given bytes to it.

        Default behavior is to overwrite any existing file.
        Call p.write_bytes(bytes, append=True) to append instead.
        """
        mode = 'ab' if append else 'wb'
        with self.open(mode=mode) as f:
            f.write(bytes_to_write)

    def text(self, encoding: Optional[str] = None, errors: str = 'strict') -> str:
        r""" Open this file, read it in, return the content as a string.

        This uses 'r' mode which automatically handles newline characters.

        Optional arguments:

        encoding - The Unicode encoding (or character set) of
            the file.  If present, the content of the file is
            decoded and returned as a Unicode object; otherwise
            it is returned as an 8-bit str.
        errors - How to handle Unicode errors; see help(str.decode)
            for the options.  Default is 'strict'.
        """
        with self.open('r', encoding=encoding, errors=errors) as f:
            return f.read()

    def write_text(self, text: Union[str, bytes], encoding: Optional[str] = None, errors: str = 'strict',
                   linesep: Optional[str] = os.linesep, append: bool = False) -> None:
        r""" Write the given text to this file.

        The default behavior is to overwrite any existing file;
        to append instead, use the 'append=True' keyword argument.

        Parameters:
          text:  - str - The text to be written.

          encoding: - str - The Unicode encoding that will be used.
            This is ignored if 'text' isn't a Unicode string.

          errors: - str - How to handle Unicode encoding errors.
            Default is 'strict'.  See help(str.encode) for the options.

          linesep: - keyword argument - str - The sequence of characters
            to be used to mark end-of-line. The default is os.linesep.
            You can also specify None; this means to leave all newlines
            as they are in 'text'.

          append: - keyword argument - bool - Specifies what to do if
            the file already exists (True: append to the end of it;
            False: overwrite it.)  The default is False.


        --- Newline handling.

        write_text() converts all standard end-of-line sequences
        ('\n', '\r', and '\r\n') to your platform's default end-of-line
        sequence (see os.linesep; on Windows, for example, the
        end-of-line marker is '\r\n').

        If you don't like your platform's default, you can override it
        using the 'linesep=' keyword argument.  If you specifically want
        write_text() to preserve the newlines as-is, use 'linesep=None'.

        This applies to Unicode text the same as to 8-bit text, except
        there are three additional standard Unicode end-of-line sequences:
        u'\x85', u'\r\x85', and u'\u2028'.

        (This is slightly different from when you open a file for
        writing with fopen(filename, "w") in C or file(filename, 'w')
        in Python.)


        --- Unicode

        If 'text' isn't Unicode, then apart from newline handling, the
        bytes are written verbatim to the file.  The 'encoding' and
        'errors' arguments are not used and must be omitted.

        If 'text' is Unicode, it is first converted to bytes using the
        specified 'encoding' (or the default encoding if 'encoding'
        isn't specified).  The 'errors' argument applies only to this
        conversion.
        """
        if isinstance(text, str):
            if linesep is not None:
                # Convert all standard end-of-line sequences to ordinary newline characters.
                text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x85', '\n').replace('\u2028', '\n')
                text = text.replace('\n', linesep)
            bytes_ = text.encode(encoding or 'utf-8', errors)
        else:
            # It is an error to specify an encoding if 'text' is an 8-bit string.
            assert encoding is None

            if linesep is not None:
                text = text.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                bytes_ = text.replace(b'\n', linesep.encode())

        mode = 'ab' if append else 'wb'
        with self.open(mode) as f:
            f.write(bytes_)

    def pickle_dump(self, obj: Any, *args, **kwargs) -> None:
        """ Serialize and write the given object to this file using pickle.

        Parameters:
            obj: Any - The object to be serialized and written to the file.
            *args: Any - Additional arguments to be passed to pickle.dump().
            **kwargs: Any - Additional keyword arguments to be passed to pickle.dump().
        """
        with self.open('wb') as file:
            pickle.dump(obj, file, *args, **kwargs)

    def pickle_load(self, *args, **kwargs) -> Any:
        """ Read and deserialize the object from this file using pickle.

        Parameters:
            *args: Any - Additional arguments to be passed to pickle.load().
            **kwargs: Any - Additional keyword arguments to be passed to pickle.load().

        Returns:
            Any - The deserialized object read from the file.
        """
        with self.open('rb') as file:
            return pickle.load(file, *args, **kwargs)

    def lines(self, encoding: Optional[str] = None, errors: str = 'strict', retain: bool = True) -> List[str]:
        r""" Open this file, read all lines, return them in a list.

        Optional arguments:
            encoding - The Unicode encoding (or character set) of
                the file.  The default is None, meaning the content
                of the file is read as 8-bit characters and returned
                as a list of (non-Unicode) str objects.
            errors - How to handle Unicode errors; see help(str.decode)
                for the options.  Default is 'strict'.
            retain - If true, retain newline characters; but all newline
                character combinations ('\r', '\n', '\r\n') are
                translated to '\n'.  If false, newline characters are
                stripped off.  Default is True.
        """
        if encoding is None and retain:
            with self.open('r') as f:
                return f.readlines()
        else:
            return self.text(encoding, errors).splitlines(retain)

    def write_lines(self, lines: List[str], encoding: Optional[str] = None, errors: str = 'strict',
                    linesep: Optional[str] = os.linesep, append: bool = False) -> None:
        r""" Write the given lines of text to this file.

        By default, this overwrites any existing file at this path.

        This puts a platform-specific newline sequence on every line.
        See 'linesep' below.

        lines - A list of strings.

        encoding - A Unicode encoding to use.  This applies only if
            'lines' contains any Unicode strings.

        errors - How to handle errors in Unicode encoding.  This
            also applies only to Unicode strings.

        linesep - The desired line-ending.  This line-ending is
            applied to every line.  If a line already has any
            standard line ending ('\r', '\n', '\r\n', u'\x85',
            u'\r\x85', u'\u2028'), that will be stripped off and
            this will be used instead.  The default is os.linesep,
            which is platform-dependent ('\r\n' on Windows, '\n' on
            Unix, etc.)  Specify None to write the lines as-is,
            like file.writelines().

        Use the keyword argument append=True to append lines to the
        file.  The default is to overwrite the file.  Warning:
        When you use this with Unicode data, if the encoding of the
        existing data in the file is different from the encoding
        you specify with the encoding= parameter, the result is
        mixed-encoding data, which can really confuse someone trying
        to read the file later.
        """
        mode = 'ab' if append else 'wb'
        with self.open(mode) as f:
            for line in lines:
                is_unicode = isinstance(line, str)
                if linesep is not None:
                    # Strip off any existing line-end and add the specified linesep string.
                    if is_unicode:
                        line = line.replace('\r\n', '\n').replace('\r', '\n').replace('\x85', '\n')
                    else:
                        line = line.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                    line += linesep
                if is_unicode:
                    if encoding is None:
                        encoding = sys.getdefaultencoding()
                    line = line.encode(encoding, errors)
                f.write(line)

    def read_md5(self) -> bytes:
        """ Calculate the md5 hash for this file.

        This reads through the entire file.
        """
        return self.read_hash('md5')

    def _hash(self, hash_name: str) -> Hashable:
        with self.open('rb') as f:
            m = hashlib.new(hash_name)
            while True:
                d = f.read(8192)
                if not d:
                    break
                m.update(d)
        return m

    def read_hash(self, hash_name: str) -> bytes:
        """ Calculate given hash for this file.

        List of supported hashes can be obtained from hashlib package. This
        reads the entire file.
        """
        return self._hash(hash_name).digest()

    def read_hexhash(self, hash_name: str) -> str:
        """ Calculate given hash for this file, returning hexdigest.

        List of supported hashes can be obtained from hashlib package. This
        reads the entire file.
        """
        return self._hash(hash_name).hexdigest()

    # --- Methods for querying the filesystem.
    # N.B. On some platforms, the os.path functions may be implemented in C
    # (e.g. isdir on Windows, Python 3.2.2), and compiled functions don't get
    # bound. Playing it safe and wrapping them all in method calls.

    def isabs(self) -> bool:
        return os.path.isabs(self)

    def isdir(self) -> bool:
        return os.path.isdir(self)

    def isfile(self) -> bool:
        return os.path.isfile(self)

    def islink(self) -> bool:
        return os.path.islink(self)

    def ismount(self) -> bool:
        return os.path.ismount(self)

    def getatime(self) -> float:
        return os.path.getatime(self)

    @property
    def atime(self) -> float:
        """ Last access time of the file. """
        return self.getatime()

    def getmtime(self) -> float:
        return os.path.getmtime(self)

    @property
    def mtime(self) -> float:
        """ Last-modified time of the file. """
        return self.getmtime()

    if hasattr(os.path, 'getctime'):
        def getctime(self) -> float:
            return os.path.getctime(self)

        @property
        def ctime(self) -> float:
            """ Creation time of the file. """
            return self.getctime()

    def getsize(self) -> int:
        return os.path.getsize(self)

    @property
    def size(self) -> int:
        """ Size of the file, in bytes. """
        return self.getsize()

    if hasattr(os, 'access'):
        def access(self, mode: int) -> bool:
            """ Return true if current user has access to this path.

            mode - One of the constants: os.F_OK, os.R_OK, os.W_OK, os.X_OK
            """
            return os.access(self, mode)

    def get_owner(self) -> str:
        r""" Return the name of the owner of this file or directory.

        This follows symbolic links.

        On Windows, this returns a name of the form ur'DOMAIN\User Name'.
        On Windows, a group can own a file or directory.
        """
        return super().owner()

    @property
    def owner(self) -> str:
        """ Name of the owner of this file or directory. """
        return self.get_owner()

    if hasattr(os, 'statvfs'):
        def statvfs(self) -> os.statvfs_result:
            """ Perform a statvfs() system call on this path. """
            return os.statvfs(self)

    if hasattr(os, 'pathconf'):
        def pathconf(self, name: int) -> int:
            return os.pathconf(self, name)

    # --- Modifying operations on files and directories

    def utime(self, times: Optional[Tuple[float, float]] = None) -> None:
        """ Set the access and modified times of this file. """
        os.utime(self, times)

    if hasattr(os, 'chown'):
        def chown(self, uid: int, gid: int) -> None:
            os.chown(self, uid, gid)

    def renames(self, new: str) -> None:
        os.renames(self, new)

    # --- Create/delete operations on directories

    def mkdir_p(self, mode: int = 0o777) -> None:
        try:
            self.mkdir(mode)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def makedirs(self, mode: int = 0o777, exist_ok: bool = False) -> None:
        os.makedirs(self, mode=mode, exist_ok=exist_ok)

    def makedirs_p(self, mode: int = 0o777) -> None:
        try:
            self.makedirs(mode=mode, exist_ok=True)
        except FileExistsError:
            raise

    def rmdir_p(self) -> None:
        try:
            self.rmdir()
        except OSError as e:
            if e.errno != errno.ENOTEMPTY and e.errno != errno.EEXIST:
                raise

    def removedirs(self) -> None:
        os.removedirs(self)

    def removedirs_p(self) -> None:
        try:
            self.removedirs()
        except OSError as e:
            if e.errno != errno.ENOTEMPTY and e.errno != errno.EEXIST:
                raise

    # --- Modifying operations on files

    def remove(self) -> None:
        os.remove(self)

    def remove_p(self) -> None:
        try:
            self.unlink()
        except FileNotFoundError:
            raise

    def unlink_p(self) -> None:
        self.remove_p()

    def launch(self) -> None:
        """
        Open file/directory using default application.
        """
        open_path(self)

    def noconflict(self) -> Path:
        """
        Returns a file system path based on the current path with an available unique name.

        If a file exists at the specified path, return the next available unique name
        with "(Copy <i>)" appended to the base of the name.

        Returns
        -------
        Path
            A new file system path with an available unique name.

        Examples
        --------
            path = path_helpers.Path('foo.txt')
            path.noconflict()
        Path('foo.txt')
            path.exists()
        False
            path.touch()
            path.noconflict()
        Path('foo (Copy).txt')
            path.touch()
            path.noconflict()
        Path('foo (Copy 1).txt')
        """
        cre_copy = re.compile(r'^(?P<name>.*?)'
                              r'(?P<copy> \(Copy(?P<copy_count> \d+)?\))?'
                              r'(?P<ext>\.[^.]*)?$')
        candidate_path = self

        while candidate_path.exists():
            groups_i = cre_copy.match(candidate_path.name).groupdict()
            if groups_i['copy']:
                groups_i['copy_count'] = (0 if groups_i['copy_count'] is None
                                          else int(groups_i['copy_count']))
                groups_i['copy_count'] += 1
            candidate_name_i = ('{name} (Copy{}){}'
                                .format(' {}'.format(groups_i['copy_count'])
                                        if groups_i['copy_count'] else '',
                                        groups_i['ext'] or '', **groups_i))
            candidate_path = candidate_path.parent.joinpath(candidate_name_i)
        return candidate_path

    # --- Links

    if hasattr(os, 'link'):
        def link(self, newpath) -> None:
            """ Create a hard link at 'newpath', pointing to this file. """
            os.link(self, newpath)

    if hasattr(os, 'symlink'):
        def symlink(self, newlink) -> None:
            """ Create a symbolic link at 'newlink', pointing here. """
            os.symlink(self, newlink)

    if hasattr(os, 'readlink'):

        def readlinkabs(self) -> Path:
            """ Return the path to which this symbolic link points.

            The result is always an absolute path.
            """
            p = self.readlink()
            if p.isabs():
                return p
            else:
                return (self.parent / p).abspath()

    # --- High-level functions from shutil

    # File copying functions
    copyfile = shutil.copyfile
    copymode = shutil.copymode
    copystat = shutil.copystat
    copy = shutil.copy
    copy2 = shutil.copy2
    copytree = shutil.copytree

    if hasattr(shutil, 'move'):
        move = shutil.move
    rmtree = shutil.rmtree

    # --- Special stuff from os

    if hasattr(os, 'chroot'):
        def chroot(self) -> None:
            os.chroot(self)

    if hasattr(os, 'startfile'):
        def startfile(self) -> None:
            os.startfile(self)

    # --- Special stuff for Windows

    if platform.system() == 'Windows':
        # Junction methods
        def isjunction(self) -> bool:
            return ntfsutils.junction.isjunction(self)

        def junction(self, target: Path) -> None:
            ntfsutils.junction.create(self, target)

        def __unlink(self) -> None:
            self.unlink()

        def unlink(self) -> None:
            if self.isjunction():
                ntfsutils.junction.unlink(self)
            else:
                self.__unlink()

        def readlink(self) -> Path:
            return self.__class__(ntfsutils.junction.readlink(self))

        # Hard link methods
        def link(self, target: Path) -> None:
            ntfsutils.hardlink.create(self, target)

        def samefile(self, other: Path) -> bool:
            return ntfsutils.hardlink.samefile(self, other)


def resource_copytree(src: str, dst: str, ignore: Optional[callable] = None) -> None:
    """
    Port of `shutil.copytree` to support copying from a Python module.

    This maintains compatibility, e.g., when copying from a module
    stored in a ``.zip`` archive or ``.egg`` file.
    """

    def _ignore(src: str, names_: List[str]) -> Set[str]:
        if ignore is not None:
            return set(ignore(src, names_))
        return set()

    names = os.listdir(src)
    ignored_names = _ignore(src, names)

    os.makedirs(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if os.path.isdir(srcname):
                resource_copytree(srcname, dstname, ignore)
            else:
                shutil.copy2(srcname, dstname)

        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except shutil.Error as err:
            errors.extend(err.args[0])
        except EnvironmentError as why:
            errors.append((srcname, dstname, str(why)))
    if errors:
        raise shutil.Error(errors)
