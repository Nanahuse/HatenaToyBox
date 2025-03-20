class ControllerException(RuntimeError):  # noqa: N818
    pass


class ServiceNotHandledError(ControllerException):
    pass


class ServiceHandlerExistsError(ControllerException):
    pass
