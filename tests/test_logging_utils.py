import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.logging_utils import bind_log_context, configure_logging, log_info, reset_log_context


class LoggingUtilsTests(unittest.TestCase):
    def test_configura_console_e_arquivo_com_request_id(self):
        temp_dir = tempfile.TemporaryDirectory()
        try:
            log_path = Path(temp_dir.name) / "logs" / "app.log"
            configure_logging(force=True, log_file=log_path)

            logger = logging.getLogger("tests.logging_utils")
            token = bind_log_context(request_id="req-test-123")
            try:
                log_info(logger, "Evento de teste", etapa="unit-test")
            finally:
                reset_log_context(token)

            for handler in logging.getLogger().handlers:
                handler.flush()

            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("Evento de teste", contents)
            self.assertIn('"request_id": "req-test-123"', contents)
            self.assertIn('"etapa": "unit-test"', contents)

            root_handlers = logging.getLogger().handlers
            has_console = any(
                isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
                for handler in root_handlers
            )
            has_rotating_file = any(
                isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename).resolve() == log_path.resolve()
                for handler in root_handlers
            )
            self.assertTrue(has_console)
            self.assertTrue(has_rotating_file)
        finally:
            configure_logging(force=True)
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
