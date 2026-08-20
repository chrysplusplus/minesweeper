from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

class Invoke:
    __slots__ = ('_wrapped')

    def __init__(self, fn: Callable[[], Any], *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            self._wrapped = fn
        else:
            self._wrapped = partial(fn, *args, **kwargs)

    def __call__(self):
        return self._wrapped()

    def then(self, then_fn: Callable[[], Any], *args, **kwargs) -> "Invoke":
        then = Invoke(then_fn, *args, **kwargs)
        return Invoke(make_then(self._wrapped, then._wrapped))

T = TypeVar("T")

def make_then(fn: Callable[[], Any], then_fn: Callable[[], T]) -> Callable[[], T]:# {{{
    def result() -> T:
        fn()
        return then_fn()
    return result
# }}}

def make_type(name: str) -> type:
    return type(name, (), {})

def clamp(val: int, max_: int, clamped: int | None = None) -> int:# {{{
    if clamped is None: clamped = max_
    return clamped if val > max_ else val
# }}}

def pad_text(text: str, padding: int) -> str:# {{{
    pad = " "* padding
    return pad + text + pad
# }}}

def set_cursor_shape():# {{{
    print("\033[2 q", end = '')
# }}}

# vim: foldmethod=marker
