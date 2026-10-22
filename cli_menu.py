"""Line-based setup prompts with Back navigation and remembered answers."""


class _Back(Exception):
    pass


class SetupMenu:
    """Rebuild setup from accepted answers when navigating backwards.

    The supplied flow must only collect settings and inspect files. Processing
    starts after run() returns, so replaying answers never repeats real work.
    """

    def __init__(self):
        self.answers = {}
        self._replay = []
        self._visited = []

    def run(self, flow):
        self._replay = []
        while True:
            self._visited = []
            try:
                return flow(self)
            except _Back:
                if self._visited:
                    self._replay = self._visited[:-1]
                    print('\nGoing back. Press Enter to keep a previous answer.')
                else:
                    self._replay = []
                    print('\nThis is the first question. Ctrl+C cancels setup.')

    @property
    def replaying(self):
        return len(self._visited) < len(self._replay)

    def note(self, message):
        if not self.replaying:
            print(message)

    def _ask(self, key, render, default, parse, error):
        position = len(self._visited)
        if self.replaying and self._replay[position][0] == key:
            raw = self._replay[position][1]
            try:
                result = parse(raw)
                if result is not None:
                    self._visited.append((key, raw))
                    return result
            except (ValueError, TypeError, OSError):
                pass
        # A changed branch or a path that disappeared must be prompted again.
        self._replay = self._replay[:position]
        empty_default = default == ''
        default = self.answers.get(key, default)
        render(default)
        if default is None:
            keep = 'required'
        elif default == '':
            keep = 'Enter = default'
        else:
            keep = f'Enter = {default}'
        reset = '; - = default' if empty_default else ''
        while True:
            raw = input(f'[{keep}; b = Back{reset}]: ').strip()
            if raw.lower() in ('b', 'back'):
                raise _Back
            if not raw:
                if default is None:
                    print('This setting is required.')
                    continue
                raw = str(default)
            if empty_default and raw == '-':
                raw = ''
            try:
                result = parse(raw)
                if result is None:
                    raise ValueError
            except (ValueError, TypeError, OSError) as exc:
                print(f'{error} {exc}'.strip())
                continue
            self.answers[key] = raw
            self._visited.append((key, raw))
            return result

    def choices(self, key, title, options, default=1):
        def render(selected):
            print(f'\n{title}')
            for index, option in enumerate(options, 1):
                suffix = ' (Default)' if str(index) == str(selected) else ''
                print(f'  {index}) {option}{suffix}')

        def parse(raw):
            value = int(raw)
            return value if 1 <= value <= len(options) else None

        return self._ask(key, render, default, parse, f'Choose a number from 1 to {len(options)}.')

    def text(self, key, title, default=None, validator=None):
        return self._ask(key, lambda _: print(f'\n{title}'), default,
                         validator or (lambda raw: raw), 'Invalid value.')

    def confirm(self, key, title, default=True):
        def parse(raw):
            if raw.lower() in ('y', 'yes'):
                return True
            if raw.lower() in ('n', 'no'):
                return False
            return None

        return self._ask(key, lambda _: print(f'\n{title}'), 'y' if default else 'n',
                         parse, 'Choose y or n.')

    def review(self):
        def parse(raw):
            value = raw.lower()
            if value in ('2', 'b', 'back'):
                raise _Back
            if value in ('1', 's', 'start', 'y', 'yes'):
                return True
            if value in ('3', 'c', 'cancel', 'n', 'no'):
                return False
            return None

        return self._ask('review', lambda _: print('\n1) Start processing  2) Back  3) Cancel'),
                         '1', parse, 'Choose Start, Back or Cancel (1, 2 or 3).')
