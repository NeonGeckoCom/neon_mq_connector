from ovos_utils.log import LOG

def default_error_handler(*args):
    """
    Default handler for Consumer instances
    :param args: list of arguments for exception handling
    :raises Exception: raise with provided args
    """
    LOG.warning("Error handler not defined")
    raise Exception(*args)
