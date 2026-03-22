"""Additional proxy.py coverage tests."""
from unittest.mock import patch, MagicMock
import pytest


class TestProxyApp:
    def test_create_app(self):
        try:
            from aiohttp import web
        except ImportError:
            pytest.skip("aiohttp not installed")

        from atlast_ecp.proxy import ATLASTProxy
        proxy = ATLASTProxy(port=9999, agent="test")
        app = proxy.create_app()
        assert app is not None
        assert proxy._app is app

    def test_proxy_init_defaults(self):
        from atlast_ecp.proxy import ATLASTProxy
        proxy = ATLASTProxy()
        assert proxy.port == 8340
        assert proxy.agent == "proxy"
        assert proxy.record_count == 0

    def test_run_proxy_function_exists(self):
        from atlast_ecp.proxy import run_proxy
        assert callable(run_proxy)

    def test_run_proxy_no_aiohttp(self):
        from atlast_ecp.proxy import run_proxy
        with patch("atlast_ecp.proxy.HAS_AIOHTTP", False):
            with pytest.raises(SystemExit):
                run_proxy()
