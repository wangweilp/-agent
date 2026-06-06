"""Sync connectors — one module per external data source.

Each connector module defines a class that inherits from BaseSyncConnector
and auto-registers itself in SYNC_CONNECTOR_REGISTRY via the module-level
_register() call.
"""
