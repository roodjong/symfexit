import codecs
import errno
import io
import os
import re
import select
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management import BaseCommand, execute_from_command_line
from django.db import DEFAULT_DB_ALIAS, OperationalError, connections

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
            raise TypeError(f"illegal newline type: {type(newline)!r}")
        if newline not in (None, "", "\n", "\r", "\r\n"):
            raise ValueError(f"illegal newline value: {newline!r}")

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

    def readline(self, size=None):  # noqa: PLR0912, PLR0915
        if size is None:
            size = -1
        else:
            try:
                size_index = size.__index__
            except AttributeError:
                raise TypeError(f"{size!r} is not an integer")  # noqa: B904
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
        argv: list[str]
        cwd: str | None
        fatal: bool

    @dataclass(frozen=True, slots=True)
    class Function:
        prefix: str
        func: Callable

    @dataclass(slots=True)
    class Running:
        command: Any
        pid: int
        pid_fd: int | None
        fd: int
        file: TextIO
        color: int = 0

    def __init__(self):
        self.commands = []
        self.running = []

    def add_command(self, prefix: str, argv: list[str], cwd: str | None = None, fatal=False):
        self.commands.append(self.Command(prefix, argv, cwd, fatal))

    def add_function(self, prefix: str, func: Callable):
        self.commands.append(self.Function(prefix, func))

    def run(self):
        try:
            self._run()
        except KeyboardInterrupt:
            pass

    def _run(self):
        # Process commands and build running processes list
        for i, command in enumerate(self.commands):
            newcmd = self._run_process(command)
            newcmd.color = i % len(ANSI_COLORS)
            self.running.append(newcmd)

        # Set up process tracking collections
        pids = {r.pid: r for r in self.running}
        pid_fds = {r.pid_fd: r for r in self.running if r.pid_fd is not None}
        fds = {r.fd: r for r in self.running}

        # Configure timeout if pidfd monitoring isn't available
        select_timeout = None if pid_fds else 2.0

        while True:
            # Handle process exits when pidfd_open isn't available
            if not pid_fds:
                self._check_process_exits(pids)

            # Monitor process outputs and exits
            rl, _, _ = select.select(
                list(pid_fds.keys()) + list(fds.keys()), [], [], select_timeout
            )

            for r in rl:
                if r in pid_fds:
                    # Process exit detected via pidfd
                    process = pid_fds[r]
                    siginfo = os.waitid(os.P_PIDFD, r, os.WEXITED)
                    self._handle_process_exit(process, siginfo.si_status)
                    os.close(r)
                    del pid_fds[r]
                else:
                    # Process output available
                    process = fds[r]
                    self._handle_process_output(process)

    def _check_process_exits(self, pids):
        """Check for process exits using waitpid when pidfd isn't available."""
        while True:
            wpid, status = os.waitpid(-1, os.WNOHANG)
            if not wpid:
                break
            status = os.waitstatus_to_exitcode(status)
            self._handle_process_exit(pids[wpid], status)

    def _handle_process_exit(self, process, status):
        """Handle a process exit with consistent formatting and fatal checking."""
        color = ANSI_COLORS[process.color]
        print(
            f"[manager] Process {color}{process.command.prefix}{ANSI_RESET} exited with status code {status}"
        )
        if process.command.fatal:
            print("[manager] Exiting...")
            sys.exit(1)

    def _handle_process_output(self, process):
        """Handle process output with consistent formatting."""
        for line in process.file:
            color = ANSI_COLORS[process.color]
            print(
                f"[{color}{process.command.prefix}{ANSI_RESET}]",
                re.sub(r"\x1b\[\d+[A-Za-ln-z]", "", line),
                end="",
                flush=True,
            )

    def _run_process(self, command_obj):
        """Common process handling for both commands and functions."""
        try:
            pid, fd = os.forkpty()
        except (AttributeError, OSError) as e:
            print(f"forkpty: Could not start {command_obj.prefix}")
            raise e
        else:
            if pid == 0:  # Child process
                if isinstance(command_obj, self.Command) and command_obj.cwd is not None:
                    os.chdir(command_obj.cwd)

                # Execute the appropriate operation based on command type
                try:
                    if isinstance(command_obj, self.Command):
                        os.execvp(command_obj.argv[0], command_obj.argv)
                    elif isinstance(command_obj, self.Function):
                        command_obj.func()
                except Exception as e:
                    if isinstance(command_obj, self.Function):
                        print(f"Exception running function {command_obj.prefix}")
                    raise e

        # Parent process continues here
        return self.Running(
            command_obj, pid, self._get_pid_fd(pid), fd, NonBlockingTextIO(open(fd, "rb"))
        )

    def _get_pid_fd(self, pid):
        pid_fd = None
        if hasattr(os, "pidfd_open"):
            pid_fd = os.pidfd_open(pid)
        return pid_fd


def get_manage_py_subcommand(argv: list[str]):
    """
    Return the executable. This contains a workaround for Windows if the
    executable is reported to not have the .exe extension which can cause bugs
    on reloading.
    """
    import __main__  # noqa: PLC0415

    py_script = Path(sys.argv[0])
    exe_entrypoint = py_script.with_suffix(".exe")

    args = [sys.executable] + [f"-W{o}" for o in sys.warnoptions]
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
        script_entrypoint = py_script.with_name(f"{py_script.name}-script.py")
        if script_entrypoint.exists():
            # Should be executed as usual.
            return [*args, script_entrypoint, *argv]
        raise RuntimeError(f"Script {py_script} does not exist.")
    else:
        args += [sys.argv[0]]
        args += argv
    return args


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--no-interaction", "-n", action="store_true", help="Don't prompt for startup questions"
        )
        parser.add_argument(
            "--no-tailwind",
            action="store_true",
            help="Don't start the tailwind watcher",
        )
        return super().add_arguments(parser)

    def handle(self, *args, **options):
        self.check_migrations()
        if not options["no_interaction"]:
            self.check_superuser()

        rm = RunMultiple()
        if not options["no_tailwind"]:
            rm.add_command(
                "tailwind", ["npm", "run", "dev"], settings.SYMFEXIT_DIR / "theme" / "static_src"
            )
        rm.add_command("startworker", get_manage_py_subcommand(["startworker"]))
        rm.add_command("runserver", get_manage_py_subcommand(["runserver"]), fatal=True)
        rm.run()

    def check_migrations(self):
        """
        Print a warning if the set of migrations on disk don't match the
        migrations in the database.
        """
        from django.db.migrations.executor import MigrationExecutor  # noqa: PLC0415

        try:
            executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        except ImproperlyConfigured:
            # No databases are configured (or the dummy one)
            self.stdout.write(
                self.style.NOTICE(
                    "\nYour database is not configured. Make sure the DATABASE_URL environment variable is set to something"
                )
            )
            sys.exit(1)
        except OperationalError as e:
            self.stdout.write("[manager] Database error:")
            self.stdout.write("\n".join([f"[manager] {s}" for s in str(e).split("\n")]))
            sys.exit(1)

        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())

        if plan:
            apps_waiting_migration = sorted({migration.app_label for migration, backwards in plan})
            self.stdout.write(
                self.style.NOTICE(
                    "\nYou have {unapplied_migration_count} unapplied migration(s). "
                    "Your project may not work properly until you apply the "
                    "migrations for app(s): {apps_waiting_migration}.".format(
                        unapplied_migration_count=len(plan),
                        apps_waiting_migration=", ".join(apps_waiting_migration),
                    )
                )
            )
            self.stdout.write(self.style.NOTICE("Run 'python manage.py migrate' to apply them."))
            sys.exit(1)

    def check_superuser(self):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            print()
            while (
                result := input(
                    "No superuser has been created yet, do you want to create one now? (This prompt can be disabled by starting with -n, --no-interaction) (Y/n) "
                )
                .lower()
                .strip()
            ) not in ["y", "n", ""]:
                print("type Y or N")
            if result in ("y", ""):
                execute_from_command_line(["", "createsuperuser"])
