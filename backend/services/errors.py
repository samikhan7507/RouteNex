class ApiError(Exception):
    """Raised by services/routers; app.py turns it into a JSON {detail} response. Rolls back any open tx()."""
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail
