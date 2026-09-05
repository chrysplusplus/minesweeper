"""File: config.py
Author: chrysplusplus
Date: 2026-09-05

Module for saving and loading the config file"""

import tomllib

from pathlib import Path
from typing import Any

DEFAULT_CONFIG_LOCATION = Path("./minesweeper.toml")

class Config:
    """Contains configuration keys and values"""
    __slots__ = ("_data")

    def __init__(self, **kwargs):
        self._data: dict[str, Any] = kwargs

    def get(self, config_path: str, default: Any = None) -> Any:
        """Get the value at the given path

        Returns None if path does not exist"""
        parts = config_path.split(".")
        journey, destination = parts[:-1], parts[-1]
        walker = self._data
        for stretch in journey:
            walker = walker.get(stretch)
            if not isinstance(walker, dict):
                return default

        return walker.get(destination, default)

def load_default_config() -> Config:
    """Load configuration from default location"""
    data: dict[str, Any]
    with open(DEFAULT_CONFIG_LOCATION, "rb") as file:
        data = tomllib.load(file)

    return Config(**data)

# vim: foldmethod=indent foldnestmax=2 foldlevel=2
