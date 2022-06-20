from functools import wraps

from neon_utils.socket_utils import b64_to_dict


def create_mq_callback(include_callback_props: tuple = ('body',)):
    """ Creates MQ callback method by filtering relevant MQ attributes """

    if not include_callback_props:
        include_callback_props = ()

    def wrapper(f):

        @wraps(f)
        def wrapped(self, *f_args):
            mq_props = ['channel', 'method', 'properties', 'body']

            callback_kwargs = {}

            for idx in range(len(mq_props)):
                if mq_props[idx] in include_callback_props:
                    value = f_args[idx]
                    if idx == 3:
                        if value and isinstance(value, bytes):
                            dict_data = b64_to_dict(value)
                            callback_kwargs['body'] = dict_data
                        else:
                            raise TypeError(f'Invalid body received, expected: bytes string; got: {type(value)}')
                    else:
                        callback_kwargs[mq_props[idx]] = value
            return f(self, **callback_kwargs)

        return wrapped

    return wrapper
