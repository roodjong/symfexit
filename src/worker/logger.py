from django.utils import timezone


class Logger:
    def __init__(self) -> None:
        self.lines = []

    def clear(self):
        self.lines = []

    def log(self, line):
        self.lines.append((timezone.now(), line))

    def get_output(self):
        return "\n".join(f"{t}: {line}" for t, line in self.lines)
