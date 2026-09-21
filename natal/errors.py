class ChartError(ValueError):
    """A blocked calculation, with a stable code suitable for the HTTP boundary."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
