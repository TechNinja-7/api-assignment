from collections import defaultdict
from typing import Dict, List

class MetricsCollector:
    def __init__(self):
        self.http_requests_total: Dict[str, int] = defaultdict(int)
        self.webhook_requests_total: Dict[str, int] = defaultdict(int)
        self.request_latencies: List[float] = []

    def record_http_request(self, path: str, status: int) -> None:
        key = f'{{"path":"{path}","status":{status}}}'
        self.http_requests_total[key] += 1

    def record_webhook_result(self, result: str) -> None:
        key = f'{{"result":"{result}"}}'
        self.webhook_requests_total[key] += 1

    def record_latency(self, latency_ms: float) -> None:
        self.request_latencies.append(latency_ms)

    def export_prometheus(self) -> str:
        lines = []
        for key, count in self.http_requests_total.items():
            lines.append(f"http_requests_total{key} {count}")
        for key, count in self.webhook_requests_total.items():
            lines.append(f"webhook_requests_total{key} {count}")
        if self.request_latencies:
            latencies = sorted(self.request_latencies)
            lines.append(f"request_latency_ms_count {len(latencies)}")
            lines.append(f"request_latency_ms_bucket{{le=\"100\"}} {sum(1 for l in latencies if l <= 100)}")
            lines.append(f"request_latency_ms_bucket{{le=\"500\"}} {sum(1 for l in latencies if l <= 500)}")
            lines.append(f"request_latency_ms_bucket{{le=\"+Inf\"}} {len(latencies)}")
        return "\n".join(lines)

metrics = MetricsCollector()
