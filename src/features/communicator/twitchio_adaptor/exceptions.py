class TwitchioAdaptorError(RuntimeError):
    pass


class NotConnectedError(TwitchioAdaptorError):
    pass


class StreamInfoUpdateError(TwitchioAdaptorError):
    pass


class UnhandledError(TwitchioAdaptorError):
    pass


class UnauthorizedError(TwitchioAdaptorError):
    pass


class ImplementationError(TwitchioAdaptorError):
    pass
