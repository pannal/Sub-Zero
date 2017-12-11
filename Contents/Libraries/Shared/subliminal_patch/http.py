# coding=utf-8
from xmlrpclib import SafeTransport, ProtocolError, Fault, Transport

import certifi
import ssl
import os
import socket
from requests import Session, exceptions
from retry.api import retry_call

from subzero.lib.io import get_viable_encoding

pem_file = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(unicode(__file__, get_viable_encoding()))), "..", certifi.where()))
try:
    default_ssl_context = ssl.create_default_context(cafile=pem_file)
except AttributeError:
    # < Python 2.7.9
    default_ssl_context = None


class RetryingSession(Session):
    proxied_functions = ("get", "post")

    def __init__(self):
        super(RetryingSession, self).__init__()
        self.verify = pem_file

    def retry_method(self, method, *args, **kwargs):
        return retry_call(getattr(super(RetryingSession, self), method), fargs=args, fkwargs=kwargs, tries=3, delay=5,
                          exceptions=(exceptions.ConnectionError,
                                      exceptions.ProxyError,
                                      exceptions.SSLError,
                                      exceptions.Timeout,
                                      exceptions.ConnectTimeout,
                                      exceptions.ReadTimeout,
                                      socket.timeout))

    def get(self, *args, **kwargs):
        return self.retry_method("get", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.retry_method("post", *args, **kwargs)


class TimeoutTransport(Transport):
    """Timeout support for ``xmlrpc.client.SafeTransport``."""
    def __init__(self, timeout, *args, **kwargs):
        Transport.__init__(self, *args, **kwargs)
        self.timeout = timeout

    def make_connection(self, host):
        c = Transport.make_connection(self, host)
        c.timeout = self.timeout

        return c


class TimeoutSafeTransport(SafeTransport):
    """Timeout support for ``xmlrpc.client.SafeTransport``."""
    def __init__(self, timeout, *args, **kwargs):
        SafeTransport.__init__(self, *args, **kwargs)
        self.timeout = timeout
        self.context = default_ssl_context

    def make_connection(self, host):
        c = SafeTransport.make_connection(self, host)
        c.timeout = self.timeout

        return c

    # def single_request(self, host, handler, request_body, verbose=0):
    #     # issue XML-RPC request
    #
    #     h = self.make_connection(host)
    #     if verbose:
    #         h.set_debuglevel(1)
    #
    #     try:
    #         self.send_request(h, handler, request_body)
    #         self.send_host(h, host)
    #         self.send_user_agent(h)
    #         self.send_content(h, request_body)
    #
    #         response = h.getresponse(buffering=True)
    #
    #         if response.status == 200:
    #             self.verbose = verbose
    #             headers = response.getheaders()
    #             rsp = self.parse_response(response)
    #             rsp[0]["headers"] = dict(headers)
    #             return rsp
    #
    #     except Fault:
    #         raise
    #     except Exception:
    #         # All unexpected errors leave connection in
    #         # a strange state, so we clear it.
    #         self.close()
    #         raise
    #
    #     #discard any response data and raise exception
    #     if (response.getheader("content-length", 0)):
    #         response.read()
    #     raise ProtocolError(
    #         host + handler,
    #         response.status, response.reason,
    #         response.msg,
    #         )