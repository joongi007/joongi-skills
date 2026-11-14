"""Unit-test executor for protocol fixtures on platforms without native isolation.

Production never imports this class or selects it through config/environment.
Linux/WSL and Docker boundaries have separate real-kernel integration tests.
"""


class ProtocolExecution:
    def __init__(self, config, environment, state=None):
        self.command = [config["command"], *config.get("args", [])]
        self.environment = environment

    def cleanup(self, process=None):
        pass
