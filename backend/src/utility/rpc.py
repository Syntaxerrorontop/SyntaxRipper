from pypresence import Presence
import time
import logging
import asyncio

class DiscordRPCManager:
    def __init__(self, client_id="1108343272522776647"): # Placeholder/Generic ID
        self.client_id = client_id
        self.rpc = None
        self.logger = logging.getLogger("DiscordRPC")
        self.connected = False

    def connect(self):
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
            self.logger.info("Connected to Discord RPC")
        except Exception as e:
            self.logger.warning(f"Discord RPC connection failed (Discord likely not running): {e}")
            self.connected = False

    def update(self, details, state=None, start_time=None):
        if not self.connected:
            self.connect()
        
        if self.connected and self.rpc:
            try:
                self.rpc.update(
                    details=details,
                    state=state,
                    start=start_time,
                    large_image="logo", # Assumes 'logo' asset exists in app's rich presence assets
                    large_text="SyntaxRipper V3"
                )
            except Exception as e:
                self.logger.error(f"Failed to update RPC: {e}")
                self.connected = False # Try reconnect next time

    def clear(self):
        if self.connected and self.rpc:
            try:
                self.rpc.clear()
            except: pass

    def close(self):
        if self.rpc:
            try: self.rpc.close()
            except: pass
        self.connected = False
