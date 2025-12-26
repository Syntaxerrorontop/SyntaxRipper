class InvalidUrlException(Exception):
    def __init__(self, message="The provided URL is invalid"):
        self.message = message
        super().__init__(self.message)

class UnknownProviderException(Exception):
    def __init__(self, message="The download provider is unknown or unsupported"):
        self.message = message
        super().__init__(self.message)