import codecs
from dataclasses import dataclass
import errno
import io
import os
from pathlib import Path
import re
import select
import sys
from typing import Any, Callable, List, Optional, TextIO
from django.conf import settings
from django.core.management import BaseCommand, execute_from_command_line

ANSI_COLORS = [
    "\033[34m",  # Blue
    "\033[33m",  # Yellow
    "\033[35m",  # Magenta
    "\033[32m",  # Green
    "\033[36m",  # Cyan
    "\033[91m",  # Bright Red
    "\033[94m",  # Bright Blue
    "\033[93m",  # Bright Yellow
    "\033[95m",  # Bright Magenta
    "\033[92m",  # Bright Green
    "\033[96m",  # Bright Cyan
]
ANSI_RESET = "\x1b[0m"


class NonBlockingTextIO:
    _CHUNK_SIZE = 2048

    def __init__(self, buffer, newline=None):
        self._check_newline(newline)
        self._readuniversal = not newline
        self._readtranslate = newline is None
        self.buffer = buffer
        os.set_blocking(self.buffer.fileno(), False)
        self._decoder = None
        self._decoded_chars = ""  # buffer for text returned from decoder
        self._decoded_chars_used = 0  # offset into _decoded_chars for read()

    def _check_newline(self, newline):
        if newline is not None and not isinstance(newline, str):
            raise TypeError("illegal newline type: %r" % (type(newline),))
        if newline not in (None, "", "\n", "\r", "\r\n"):
            raise ValueError("illegal newline value: %r" % (newline,))

    def _read_chunk(self):
        """
        Read and decode the next chunk of data from the BufferedReader.
        """

        if self._decoder is None:
            raise ValueError("no decoder")

        # Read a chunk, decode it, and put the result in self._decoded_chars.
        try:
            input_chunk = self.buffer.read1(self._CHUNK_SIZE)
        except OSError as e:
            if e.errno == errno.EIO:
                return False
            raise e
        eof = not input_chunk
        decoded_chars = self._decoder.decode(input_chunk, eof)
        self._set_decoded_chars(decoded_chars)

        return not eof

    # The following three methods implement an ADT for _decoded_chars.
    # Text returned from the decoder is buffered here until the client
    # requests it by calling our read() or readline() method.
    def _set_decoded_chars(self, chars):
        """Set the _decoded_chars buffer."""
        self._decoded_chars = chars
        self._decoded_chars_used = 0

    def _get_decoded_chars(self, n=None):
        """Advance into the _decoded_chars buffer."""
        offset = self._decoded_chars_used
        if n is None:
            chars = self._decoded_chars[offset:]
        else:
            chars = self._decoded_chars[offset : offset + n]
        self._decoded_chars_used += len(chars)
        return chars

    def _rewind_decoded_chars(self, n):
        """Rewind the _decoded_chars buffer."""
        if self._decoded_chars_used < n:
            raise AssertionError("rewind decoded_chars out of bounds")
        self._decoded_chars_used -= n

    def _get_decoder(self):
        make_decoder = codecs.getincrementaldecoder("utf-8")
        decoder = make_decoder()
        if self._readuniversal:
            decoder = io.IncrementalNewlineDecoder(decoder, self._readtranslate)
        self._decoder = decoder
        return decoder

    def readline(self, size=None):
        if size is None:
            size = -1
        else:
            try:
                size_index = size.__index__
            except AttributeError:
                raise TypeError(f"{size!r} is not an integer")
            else:
                size = size_index()

        # Grab all the decoded text (we will rewind any extra bits later).
        line = self._get_decoded_chars()

        start = 0
        # Make the decoder if it doesn't already exist.
        if not self._decoder:
            self._get_decoder()

        pos = endpos = None
        while True:
            if self._readtranslate:
                # Newlines are already translated, only search for \n
                pos = line.find("\n", start)
                if pos >= 0:
                    endpos = pos + 1
                    break
                else:
                    start = len(line)

            elif self._readuniversal:
                # Universal newline search. Find any of \r, \r\n, \n
                # The decoder ensures that \r\n are not split in two pieces

                # In C we'd look for these in parallel of course.
                nlpos = line.find("\n", start)
                crpos = line.find("\r", start)
                if crpos == -1:
                    if nlpos == -1:
                        # Nothing found
                        start = len(line)
                    else:
                        # Found \n
                        endpos = nlpos + 1
                        break
                elif nlpos == -1:
                    # Found lone \r
                    endpos = crpos + 1
                    break
                elif nlpos < crpos:
                    # Found \n
                    endpos = nlpos + 1
                    break
                elif nlpos == crpos + 1:
                    # Found \r\n
                    endpos = crpos + 2
                    break
                else:
                    # Found \r
                    endpos = crpos + 1
                    break
            else:
                # non-universal
                pos = line.find(self._readnl)
                if pos >= 0:
                    endpos = pos + len(self._readnl)
                    break

            if size >= 0 and len(line) >= size:
                endpos = size  # reached length size
                break

            # No line ending seen yet - get more data'
            while self._read_chunk():
                if self._decoded_chars:
                    break
            if self._decoded_chars:
                line += self._get_decoded_chars()
            else:
                # temporary end of file
                self._set_decoded_chars(line)
                return None

        if size >= 0 and endpos > size:
            endpos = size  # don't exceed size

        # Rewind _decoded_chars to just after the line ending we found.
        self._rewind_decoded_chars(len(line) - endpos)
        return line[:endpos]

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line


class RunMultiple:
    @dataclass(frozen=True, slots=True)
    class Command:
        prefix: str
        argv: List[str]
        cwd: Optional[str]
        fatal: bool

    @dataclass(frozen=True, slots=True)
    class Function:
        prefix: str
        func: Callable

    @dataclass(slots=True)
    class Running:
        command: Any
        pid: int
        pid_fd: Optional[int]
        fd: int
        file: TextIO
        color: int = 0

    def __init__(self):
        self.commands = []
        self.running = []

    def add_command(self, prefix: str, argv: List[str], cwd: Optional[str] = None, fatal=False):
        self.commands.append(self.Command(prefix, argv, cwd, fatal))

    def add_function(self, prefix: str, func: Callable):
        self.commands.append(self.Function(prefix, func))

    def run(self):
        try:
            self._run()
        except KeyboardInterrupt:
            pass

    def _run(self):
        for i, command in enumerate(self.commands):
            if isinstance(command, self.Command):
                newcmd = self._run_command(command)
            elif isinstance(command, self.Function):
                newcmd = self._run_function(command)
            newcmd.color = i % len(ANSI_COLORS)
            self.running.append(newcmd)

        # Empty if pidfd_open is not available
        pid_fds = {r.pid_fd: r for r in self.running if r.pid_fd is not None}
        select_timeout = None
        if not pid_fds:
            select_timeout = 2.0
        fds = {r.fd: r for r in self.running}
        while True:
            rl, _, _ = select.select(
                list(pid_fds.keys()) + list(fds.keys()), [], [], select_timeout
            )
            for r in rl:
                if r in pid_fds:
                    siginfo = os.waitid(os.P_PIDFD, r, os.WEXITED)
                    color = ANSI_COLORS[pid_fds[r].color]
                    print(
                        f"[manager] Process {color}{pid_fds[r].command.prefix}{ANSI_RESET} exited with status code {siginfo.si_status}"
                    )
                    if pid_fds[r].command.fatal:
                        print("[manager] Exiting...")
                        sys.exit(1)
                    del pid_fds[r]
                else:
                    for line in fds[r].file:
                        color = ANSI_COLORS[fds[r].color]
                        print(
                            f"[{color}{fds[r].command.prefix}{ANSI_RESET}]",
                            re.sub(r"\x1b\[\d+[A-Za-ln-z]", "", line),
                            end="",
                            flush=True,
                        )

    def _run_command(self, command):
        try:
            pid, fd = os.forkpty()
        except (AttributeError, OSError):
            print(f"forkpty: Could not start {command.prefix}")
        else:
            if pid == 0:
                if command.cwd is not None:
                    os.chdir(command.cwd)
                os.execvp(command.argv[0], command.argv)
                print(f"execvp: Could not start {command.prefix}")
        return self.Running(
            command, pid, self._get_pid_fd(pid), fd, NonBlockingTextIO(io.open(fd, "rb"))
        )

    def _run_function(self, function):
        try:
            pid, fd = os.forkpty()
        except (AttributeError, OSError):
            print(f"forkpty: Could not start {function.prefix}")
        else:
            if pid == 0:
                try:
                    function.func()
                except Exception as e:
                    print(f"Exception running function {function.prefix}")
                    raise e
        return self.Running(
            function, pid, self._get_pid_fd(pid), fd, NonBlockingTextIO(io.open(fd, "rb"))
        )

    def _get_pid_fd(self, pid):
        pid_fd = None
        if hasattr(os, "pidfd_open"):
            pid_fd = os.pidfd_open(pid)
        return pid_fd


def get_manage_py_subcommand(argv: List[str]):
    """
    Return the executable. This contains a workaround for Windows if the
    executable is reported to not have the .exe extension which can cause bugs
    on reloading.
    """
    import __main__

    py_script = Path(sys.argv[0])
    exe_entrypoint = py_script.with_suffix(".exe")

    args = [sys.executable] + ["-W%s" % o for o in sys.warnoptions]
    if sys.implementation.name in ("cpython", "pypy"):
        args.extend(
            f"-X{key}" if value is True else f"-X{key}={value}"
            for key, value in sys._xoptions.items()
        )
    # __spec__ is set when the server was started with the `-m` option,
    # see https://docs.python.org/3/reference/import.html#main-spec
    # __spec__ may not exist, e.g. when running in a Conda env.
    if getattr(__main__, "__spec__", None) is not None and not exe_entrypoint.exists():
        spec = __main__.__spec__
        if (spec.name == "__main__" or spec.name.endswith(".__main__")) and spec.parent:
            name = spec.parent
        else:
            name = spec.name
        args += ["-m", name]
        args += argv
    elif not py_script.exists():
        # sys.argv[0] may not exist for several reasons on Windows.
        # It may exist with a .exe extension or have a -script.py suffix.
        if exe_entrypoint.exists():
            # Should be executed directly, ignoring sys.executable.
            return [exe_entrypoint, *argv]
        script_entrypoint = py_script.with_name("%s-script.py" % py_script.name)
        if script_entrypoint.exists():
            # Should be executed as usual.
            return [*args, script_entrypoint, *argv]
        raise RuntimeError("Script %s does not exist." % py_script)
    else:
        args += [sys.argv[0]]
        args += argv
    return args


class Command(BaseCommand):
    def handle(self, *args, **options):
        rm = RunMultiple()
        rm.add_command(
            "tailwind", ["npm", "run", "dev"], settings.BASE_DIR / "theme" / "static_src"
        )
        rm.add_command("startworker", get_manage_py_subcommand(["startworker"]))
        rm.add_command("runserver", get_manage_py_subcommand(["runserver"]), fatal=True)
        rm.run()
