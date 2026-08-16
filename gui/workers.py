from PyQt5.QtCore import QThread, pyqtSignal

from application.analysis import AnalysisService
from application.exporting import (
    decrypt,
    export_text,
    extract_archive,
)


class AnalysisWorker(QThread):
    progress = pyqtSignal(str)
    resultReady = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            service = AnalysisService(progress=self._report_progress)
            result = service.analyze(self.path)
            if not self.isInterruptionRequested():
                self.resultReady.emit(result)
        except InterruptedError:
            return
        except Exception as exc:  # noqa: BLE001 - thread error boundary
            self.failed.emit(str(exc))

    def _report_progress(self, message: str):
        if self.isInterruptionRequested():
            raise InterruptedError
        self.progress.emit(message)


class BatchOperationWorker(QThread):
    progress = pyqtSignal(int, int, str)
    resultReady = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, operation: str, result: dict, output_dir: str,
                 fmt: str = 'raw'):
        super().__init__()
        self.operation = operation
        self.result = result
        self.output_dir = output_dir
        self.fmt = fmt

    def run(self):
        try:
            if self.operation == 'export_text':
                count, errors = export_text(
                    self.result, self.output_dir, self.fmt,
                    progress=self._report_progress)
            elif self.operation == 'decrypt':
                count, errors = decrypt(
                    self.result, self.output_dir,
                    progress=self._report_progress)
            elif self.operation == 'extract_archive':
                count, errors = extract_archive(
                    self.result, self.output_dir,
                    progress=self._report_progress)
            else:
                raise ValueError(f'未知批处理操作: {self.operation}')
            if not self.isInterruptionRequested():
                self.resultReady.emit({
                    'operation': self.operation,
                    'count': count,
                    'errors': errors,
                    'output_dir': self.output_dir,
                })
        except InterruptedError:
            return
        except Exception as exc:  # noqa: BLE001 - thread error boundary
            self.failed.emit(str(exc))

    def _report_progress(self, current: int, total: int, name: str):
        if self.isInterruptionRequested():
            raise InterruptedError
        self.progress.emit(current, total, name)
