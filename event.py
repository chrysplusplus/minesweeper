"""File: event.py
Author: chrysplusplus
Date: 2026-08-30

Module containing types for creating and handling application events that
trigger callback across various part of an application"""

from dataclasses import dataclass
from collections import OrderedDict
from collections.abc import Callable

@dataclass
class BaseEvent:
    """Base class for specifying events; sub-class this to add custom messages
    to an application"""

class EventHandler:
    """Handler for processing application events"""
    __slots__ = ("callbacks", "queue")

    def __init__(self):
        self.callbacks: OrderedDict[type, Callable[[BaseEvent], None]] = OrderedDict()
        self.queue: list[BaseEvent] = []

    def bind(self, event_t: type, callback: Callable[[BaseEvent], None]) -> bool:
        """Bind event type to callback

        event_t must be a subclass of BaseEvent

        Returns False if type is already bound"""
        assert issubclass(event_t, BaseEvent)
        if event_t in self.callbacks:
            return False
        self.callbacks[event_t] = callback
        return True

    def unbind(self, event_t: type) -> bool:
        """Unbind event type

        event_t must be a subclass of BaseEvent

        Returns False if type was already unbound"""
        assert issubclass(event_t, BaseEvent)
        if event_t not in self.callbacks:
            return False
        del self.callbacks[event_t]
        return True

    def rebind(self,
               event_t: type,
               callback: Callable[[BaseEvent], None]) -> Callable[[BaseEvent], None] | None:
        """Force binding event type to callback

        event_t must be a subclass of BaseEvent

        Return previously bound callback or None"""
        assert issubclass(event_t, BaseEvent)
        previous_callback: Callable[[BaseEvent], None] | None
        if event_t in self.callbacks:
            previous_callback = self.callbacks[event_t]
            self.callbacks[event_t] = callback
        else:
            previous_callback = None
        return previous_callback

    def enqueue(self, event: BaseEvent) -> bool:
        """Enqueue event"""
        self.queue.append(event)

    def process(self):
        """Process event queue"""
        while len(self.queue) > 0:
            event = self.queue.pop(0)
            if type(event) not in self.callbacks:
                # weird scenario where the bound callback got removed before the
                # event was processed; intention in removing the callback
                # means ignore this event
                continue
            callback = self.callbacks[type(event)]
            callback(event)

# vim: foldmethod=indent foldnestmax=2 foldlevel=2
