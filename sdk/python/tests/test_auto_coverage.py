"""Tests for auto.py coverage gaps — lines 101,105,109-116,159-165,169-170."""
import pytest
import warnings
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_auto():
    """Reset auto module's _initialized flag before each test."""
    import atlast_ecp.auto as auto_mod
    auto_mod._initialized = False
    yield
    auto_mod._initialized = False


class TestInit:
    def test_returns_already_initialized_on_second_call(self, monkeypatch):
        import atlast_ecp.auto as auto_mod
        auto_mod._initialized = True
        mock_identity = {"did": "did:ecp:test123"}
        with patch("atlast_ecp.auto.get_identity" if False else "atlast_ecp.core.get_identity", return_value=mock_identity):
            # Patch the local import inside the function
            with patch.dict("sys.modules", {}):
                import atlast_ecp.core as core_mod
                original = getattr(core_mod, "get_identity", None)
                core_mod.get_identity = lambda: mock_identity
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        from atlast_ecp.auto import init
                        result = init()
                finally:
                    if original:
                        core_mod.get_identity = original
        assert result["status"] == "already_initialized"
        assert result["agent_did"] == "did:ecp:test123"

    def test_returns_otel_not_installed_when_missing(self):
        import sys
        # Remove otel from sys.modules to simulate not installed
        otel_keys = [k for k in sys.modules if k.startswith("opentelemetry")]
        saved = {k: sys.modules.pop(k) for k in otel_keys}
        try:
            import atlast_ecp.auto as auto_mod
            auto_mod._initialized = False

            mock_identity = {"did": "did:ecp:test"}
            import atlast_ecp.core as core_mod
            original_get = getattr(core_mod, "get_identity", None)
            core_mod.get_identity = lambda: mock_identity

            def mock_setup_otel():
                raise ImportError("opentelemetry-sdk not installed")

            try:
                with patch.object(auto_mod, "_setup_otel", side_effect=ImportError("opentelemetry-sdk not installed")):
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        result = auto_mod.init()
            finally:
                if original_get:
                    core_mod.get_identity = original_get
        finally:
            sys.modules.update(saved)

        assert result["status"] == "otel_not_installed"
        assert any("opentelemetry-sdk" in e for e in result["errors"])

    def test_returns_error_on_unexpected_exception(self):
        import atlast_ecp.auto as auto_mod
        auto_mod._initialized = False

        import atlast_ecp.core as core_mod
        original_get = getattr(core_mod, "get_identity", None)
        core_mod.get_identity = lambda: (_ for _ in ()).throw(RuntimeError("unexpected!"))

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = auto_mod.init()
        finally:
            if original_get:
                core_mod.get_identity = original_get

        assert result["status"] == "error"
        assert len(result["errors"]) > 0

    def test_collects_instrumented_and_skipped(self):
        import atlast_ecp.auto as auto_mod
        auto_mod._initialized = False

        mock_identity = {"did": "did:ecp:abc"}
        import atlast_ecp.core as core_mod
        original_get = getattr(core_mod, "get_identity", None)
        core_mod.get_identity = lambda: mock_identity

        def mock_try_instrument(lib_name, instrumentor_path):
            if lib_name == "openai":
                return "ok"
            elif lib_name == "anthropic":
                return "not_installed"
            else:
                return "error: some error"

        try:
            with patch.object(auto_mod, "_setup_otel"), \
                 patch.object(auto_mod, "_try_instrument", side_effect=mock_try_instrument):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    result = auto_mod.init()
        finally:
            if original_get:
                core_mod.get_identity = original_get

        assert result["status"] == "ok"
        assert "openai" in result["instrumented"]
        assert "anthropic" in result["skipped"]
        assert any("some error" in e for e in result["errors"])
        assert auto_mod._initialized is True


class TestTryInstrument:
    def test_not_installed_when_lib_missing(self):
        from atlast_ecp.auto import _try_instrument
        result = _try_instrument("nonexistent_lib_xyz", "some.path.Cls")
        assert result == "not_installed"

    def test_not_installed_when_instrumentor_missing(self):
        """Library exists but instrumentor package not installed."""
        import sys
        # os is always available, but fake its instrumentor
        with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (
            __import__(name, *a, **kw) if name != "some.instrumentation.module" else (_ for _ in ()).throw(ImportError())
        )):
            pass  # can't easily test this path cleanly, skip

        # Test using a real importable lib but fake instrumentor path
        from atlast_ecp.auto import _try_instrument
        # json is installed, but "json.nonexistent.Instrumentor" is not
        result = _try_instrument("json", "json.nonexistent_module.NonExistentClass")
        assert result == "not_installed"

    def test_error_on_instrumentor_exception(self):
        """Instrumentor raises an exception during instrument()."""
        import sys, types

        mock_instrumentor = MagicMock()
        mock_instrumentor.is_instrumented_by_opentelemetry = False
        mock_instrumentor.instrument.side_effect = RuntimeError("instrumentation failed")
        mock_cls = MagicMock(return_value=mock_instrumentor)

        # Register a fake instrumentor module
        fake_instr = types.ModuleType("fake_instr_pkg")
        fake_instr_sub = types.ModuleType("fake_instr_pkg.module")
        fake_instr_sub.FakeInstrumentor = mock_cls
        sys.modules["fake_instr_pkg"] = fake_instr
        sys.modules["fake_instr_pkg.module"] = fake_instr_sub

        try:
            from atlast_ecp.auto import _try_instrument
            # json is always importable (the lib), fake_instr_pkg.module.FakeInstrumentor raises
            result = _try_instrument("json", "fake_instr_pkg.module.FakeInstrumentor")
            assert result.startswith("error:")
        finally:
            del sys.modules["fake_instr_pkg"]
            del sys.modules["fake_instr_pkg.module"]

    def test_skips_already_instrumented(self):
        """If is_instrumented_by_opentelemetry is True, skip calling instrument()."""
        mock_instrumentor = MagicMock()
        mock_instrumentor.is_instrumented_by_opentelemetry = True
        mock_cls = MagicMock(return_value=mock_instrumentor)
        mock_mod = MagicMock()

        import sys
        # Use a real module name that exists, mock the instrumentor
        with patch.dict(sys.modules, {"json": sys.modules["json"]}):
            import types
            fake_mod = types.ModuleType("fake_instr_mod")
            fake_mod.FakeClass = mock_cls
            sys.modules["fake_instr_mod"] = fake_mod
            try:
                from atlast_ecp.auto import _try_instrument
                result = _try_instrument("json", "fake_instr_mod.FakeClass")
                assert result == "ok"
                mock_instrumentor.instrument.assert_not_called()
            finally:
                del sys.modules["fake_instr_mod"]


class TestReset:
    def test_reset_clears_initialized(self):
        import atlast_ecp.auto as auto_mod
        auto_mod._initialized = True
        from atlast_ecp.auto import reset
        reset()
        assert auto_mod._initialized is False
