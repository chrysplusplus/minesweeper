"""Utility module by chrysplusplus"""

from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

class Invoke:# {{{
    """Class for wrapping composition of functions corresponding to a
    monadic-then"""
    __slots__ = ('_wrapped',)

    def __init__(self, fn: Callable[[], Any], *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            self._wrapped = fn
        else:
            self._wrapped = partial(fn, *args, **kwargs)

    def __call__(self):
        return self._wrapped()

    def then(self, then_fn: Callable[[], Any], *args, **kwargs) -> "Invoke":
        """Return an Invoke object representing running this, then that"""
        then = Invoke(then_fn, *args, **kwargs)
        return Invoke(make_then(self._wrapped, then._wrapped)) # }}}

T = TypeVar("T")
U = TypeVar("U")

def make_then(fn: Callable[[], Any], then_fn: Callable[[], T]) -> Callable[[], T]:# {{{
    """Compose two functions in a monadic-then-like way"""
    def result() -> T:
        fn()
        return then_fn()
    return result # }}}

def make_type(name: str) -> type:# {{{
    """Shorthand for creating a named type"""
    return type(name, (), {}) # }}}

def clamp(val: int, max_: int, clamped: int | None = None) -> int:# {{{
    """Clamp a value to a maximum value, or a sentinel clamp value if the input
    exceeds the maximum"""
    if clamped is None:
        clamped = max_
    return clamped if val > max_ else val # }}}

def pad_text(text: str, padding: int) -> str:# {{{
    """Pad a string with spaces"""
    pad = " "* padding
    return pad + text + pad # }}}

def same(this: Any, that: Any) -> bool:# {{{
    """Shorthand for ensure two variables refer to the same object"""
    return id(this) == id(that) # }}}

def label_tuple(t: tuple, *labels: str) -> str:# {{{
    """Format a string with labelled elements of a tuple"""
    return ', '.join(f"{l}={t[i]}" for i, l in enumerate(labels)) # }}}

def compose2(fn0: Callable[[Any], T], fn1: Callable[[T], U]) -> Callable[[Any], U]:
    """Return the composition of two functions"""
    return lambda *args, **kwargs: fn1(fn0(*args, **kwargs))

# vim: foldmethod=marker
