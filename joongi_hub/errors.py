"""JSON-RPC errors shared by both transports."""


class RpcError(Exception):
    def __init__(self, code: int, message: str, data=None):
        super().__init__(message)
        self.code = code
        self.data = data

    def as_dict(self):
        result = {"code": self.code, "message": str(self)}
        if self.data is not None:
            result["data"] = self.data
        return result
