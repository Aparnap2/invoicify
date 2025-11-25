"""
Real-time performance monitoring dashboard with WebSocket support.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
import websockets
import websockets.server
from concurrent.futures import CancelledError

from ...app.services.metrics_service import metrics_service
from ...app.models.metrics import SLOPeriod, AlertSeverity
from ..core.benchmark_types import PerformanceMetric, MetricCategory, PerformanceTier

logger = logging.getLogger(__name__)


@dataclass
class DashboardMetric:
    """Dashboard-ready metric data."""
    name: str
    category: str
    value: float
    unit: str
    timestamp: str
    tier: str
    threshold_target: Optional[float]
    threshold_critical: Optional[float]


@dataclass
class DashboardAlert:
    """Dashboard-ready alert data."""
    id: str
    slo_name: str
    type: str
    severity: str
    title: str
    message: str
    created_at: str
    resolved_at: Optional[str]


@dataclass
class DashboardState:
    """Complete dashboard state for WebSocket transmission."""
    timestamp: str
    metrics: List[DashboardMetric]
    slos: Dict[str, Any]
    alerts: List[DashboardAlert]
    system_health: Dict[str, Any]
    performance_trends: Dict[str, Any]


class PerformanceMonitor:
    """Real-time performance monitoring with WebSocket dashboard."""

    def __init__(self):
        """Initialize performance monitor."""
        self.logger = logging.getLogger(__name__)
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._websocket_server: Optional[websockets.WebSocketServer] = None

        # Cache for dashboard data
        self._dashboard_cache: Optional[DashboardState] = None
        self._last_update: Optional[datetime] = None
        self.cache_duration = timedelta(seconds=5)  # Update every 5 seconds

    async def start_monitoring(
        self,
        host: str = "localhost",
        port: int = 8765,
        update_interval: int = 5
    ) -> None:
        """Start real-time monitoring and WebSocket server."""
        if self.is_running:
            self.logger.warning("Monitoring already started")
            return

        self.is_running = True
        self.update_interval = update_interval

        try:
            # Start WebSocket server
            self._websocket_server = await websockets.serve(
                self._handle_websocket_connection,
                host,
                port
            )

            # Start background monitoring task
            self._monitor_task = asyncio.create_task(self._monitoring_loop())

            self.logger.info(f"Performance monitoring started on ws://{host}:{port}")

        except Exception as e:
            self.is_running = False
            self.logger.error(f"Failed to start monitoring: {e}")
            raise

    async def stop_monitoring(self) -> None:
        """Stop monitoring and WebSocket server."""
        self.is_running = False

        # Cancel monitoring task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except CancelledError:
                pass

        # Close WebSocket server
        if self._websocket_server:
            self._websocket_server.close()
            await self._websocket_server.wait_closed()

        # Disconnect all clients
        await self._disconnect_all_clients()

        self.logger.info("Performance monitoring stopped")

    async def _handle_websocket_connection(
        self,
        websocket: websockets.WebSocketServerProtocol,
        path: str
    ) -> None:
        """Handle new WebSocket connection."""
        self.logger.info(f"New dashboard connection from {websocket.remote_address}")

        try:
            # Add to clients set
            self.clients.add(websocket)

            # Send initial dashboard state
            await self._send_dashboard_update(websocket)

            # Keep connection alive and handle messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid JSON from client {websocket.remote_address}")
                except Exception as e:
                    self.logger.error(f"Error handling message from {websocket.remote_address}: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Dashboard client disconnected: {websocket.remote_address}")
        except Exception as e:
            self.logger.error(f"WebSocket error for {websocket.remote_address}: {e}")
        finally:
            # Remove from clients set
            self.clients.discard(websocket)

    async def _handle_client_message(
        self,
        websocket: websockets.WebSocketServerProtocol,
        data: Dict[str, Any]
    ) -> None:
        """Handle messages from dashboard clients."""
        message_type = data.get("type")

        if message_type == "refresh":
            # Force refresh of dashboard data
            await self._send_dashboard_update(websocket, force_refresh=True)

        elif message_type == "get_slo_details":
            # Send detailed SLO information
            slo_id = data.get("slo_id")
            if slo_id:
                await self._send_slo_details(websocket, slo_id)

        elif message_type == "get_trends":
            # Send performance trend data
            await self._send_performance_trends(websocket, data.get("days", 7))

        else:
            self.logger.warning(f"Unknown message type: {message_type}")

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop that updates dashboard data."""
        while self.is_running:
            try:
                # Update dashboard state
                dashboard_state = await self._get_dashboard_state()

                # Cache the state
                self._dashboard_cache = dashboard_state
                self._last_update = datetime.now(timezone.utc)

                # Broadcast to all connected clients
                if self.clients:
                    await self._broadcast_dashboard_update(dashboard_state)

                # Wait for next update
                await asyncio.sleep(self.update_interval)

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.update_interval)

    async def _get_dashboard_state(self, force_refresh: bool = False) -> DashboardState:
        """Get current dashboard state."""
        # Use cached data if available and not expired
        if (not force_refresh and
            self._dashboard_cache and
            self._last_update and
            datetime.now(timezone.utc) - self._last_update < self.cache_duration):
            return self._dashboard_cache

        try:
            # Get comprehensive dashboard data
            slo_dashboard = await metrics_service.get_slo_dashboard_data(time_range_days=1)
            kpi_summary = await metrics_service.get_kpi_summary(days=1)

            # Convert SLO data to dashboard format
            dashboard_slos = self._convert_slos_for_dashboard(slo_dashboard)
            dashboard_alerts = self._convert_alerts_for_dashboard(slo_dashboard)

            # Get system health metrics
            system_health = await self._get_system_health_metrics()

            # Get performance trends
            performance_trends = await self._get_performance_trends(days=7)

            # Get current performance metrics
            current_metrics = await self._get_current_performance_metrics()

            dashboard_state = DashboardState(
                timestamp=datetime.now(timezone.utc).isoformat(),
                metrics=current_metrics,
                slos=dashboard_slos,
                alerts=dashboard_alerts,
                system_health=system_health,
                performance_trends=performance_trends
            )

            return dashboard_state

        except Exception as e:
            self.logger.error(f"Failed to get dashboard state: {e}")
            # Return minimal state
            return DashboardState(
                timestamp=datetime.now(timezone.utc).isoformat(),
                metrics=[],
                slos={"error": str(e)},
                alerts=[],
                system_health={"status": "error"},
                performance_trends={}
            )

    async def _broadcast_dashboard_update(self, dashboard_state: DashboardState) -> None:
        """Broadcast dashboard update to all connected clients."""
        if not self.clients:
            return

        message = json.dumps(asdict(dashboard_state))

        # Send to all clients
        tasks = []
        for client in list(self.clients):  # Copy to avoid modification during iteration
            try:
                tasks.append(client.send(message))
            except Exception as e:
                self.logger.warning(f"Failed to send update to client: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_dashboard_update(
        self,
        websocket: websockets.WebSocketServerProtocol,
        force_refresh: bool = False
    ) -> None:
        """Send dashboard update to specific client."""
        try:
            dashboard_state = await self._get_dashboard_state(force_refresh)
            message = json.dumps(asdict(dashboard_state))
            await websocket.send(message)
        except Exception as e:
            self.logger.error(f"Failed to send dashboard update: {e}")

    async def _disconnect_all_clients(self) -> None:
        """Disconnect all connected clients."""
        if not self.clients:
            return

        # Close all connections
        tasks = []
        for client in list(self.clients):
            try:
                tasks.append(client.close())
            except Exception:
                pass

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.clients.clear()

    def _convert_slos_for_dashboard(self, slo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert SLO data to dashboard format."""
        return {
            "summary": slo_data.get("summary", {}),
            "time_range": slo_data.get("time_range", {}),
            "slos": slo_data.get("slos", []),
            "overall_health": self._calculate_overall_health(slo_data.get("slos", []))
        }

    def _convert_alerts_for_dashboard(self, slo_data: Dict[str, Any]) -> List[DashboardAlert]:
        """Convert alerts to dashboard format."""
        alerts = []
        for alert_data in slo_data.get("alerts", []):
            alert = DashboardAlert(
                id=alert_data.get("id", ""),
                slo_name=alert_data.get("slo_name", ""),
                type=alert_data.get("type", ""),
                severity=alert_data.get("severity", ""),
                title=alert_data.get("title", ""),
                message=alert_data.get("message", ""),
                created_at=alert_data.get("created_at", ""),
                resolved_at=alert_data.get("resolved_at")
            )
            alerts.append(alert)
        return alerts

    def _calculate_overall_health(self, slos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall system health from SLO data."""
        if not slos:
            return {"status": "unknown", "score": 0, "message": "No SLO data available"}

        total_slos = len(slos)
        healthy_slos = sum(1 for slo in slos if slo.get("status") == "healthy")
        critical_slos = sum(1 for slo in slos if slo.get("status") == "critical")

        health_score = (healthy_slos / total_slos) * 100

        if critical_slos > 0:
            status = "critical"
            message = f"{critical_slos} critical SLOs"
        elif health_score >= 90:
            status = "healthy"
            message = "All systems operational"
        elif health_score >= 75:
            status = "warning"
            message = "Some performance degradation detected"
        else:
            status = "critical"
            message = "Significant performance issues"

        return {
            "status": status,
            "score": round(health_score, 1),
            "message": message,
            "total_slos": total_slos,
            "healthy_slos": healthy_slos,
            "critical_slos": critical_slos
        }

    async def _get_system_health_metrics(self) -> Dict[str, Any]:
        """Get system health metrics."""
        try:
            import psutil

            # System resource usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Application-specific health checks
            # TODO: Add application-specific health checks

            return {
                "cpu_usage": cpu_percent,
                "memory_usage": memory.percent,
                "disk_usage": (disk.used / disk.total) * 100,
                "uptime": time.time(),  # TODO: Get actual application uptime
                "status": "healthy" if cpu_percent < 80 and memory.percent < 85 else "warning"
            }

        except Exception as e:
            self.logger.error(f"Failed to get system health: {e}")
            return {"status": "error", "error": str(e)}

    async def _get_performance_trends(self, days: int = 7) -> Dict[str, Any]:
        """Get performance trend data."""
        try:
            # Get trend data from metrics service
            # TODO: Implement trend analysis in metrics service

            # Placeholder trend data
            return {
                "response_time_trend": self._generate_trend_data(days, "response_time"),
                "throughput_trend": self._generate_trend_data(days, "throughput"),
                "error_rate_trend": self._generate_trend_data(days, "error_rate"),
                "availability_trend": self._generate_trend_data(days, "availability")
            }

        except Exception as e:
            self.logger.error(f"Failed to get performance trends: {e}")
            return {"error": str(e)}

    def _generate_trend_data(self, days: int, metric_type: str) -> List[Dict[str, Any]]:
        """Generate placeholder trend data."""
        # TODO: Replace with actual trend data from metrics service
        import random

        trend_data = []
        for i in range(days):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).date()

            if metric_type == "response_time":
                value = random.uniform(200, 500)
            elif metric_type == "throughput":
                value = random.uniform(1000, 5000)
            elif metric_type == "error_rate":
                value = random.uniform(0, 5)
            elif metric_type == "availability":
                value = random.uniform(95, 100)
            else:
                value = 0

            trend_data.append({
                "date": date.isoformat(),
                "value": round(value, 2)
            })

        return list(reversed(trend_data))

    async def _get_current_performance_metrics(self) -> List[DashboardMetric]:
        """Get current performance metrics."""
        try:
            # Get real-time metrics
            # TODO: Implement real-time metric collection

            # Placeholder metrics
            return [
                DashboardMetric(
                    name="api_response_time",
                    category="latency",
                    value=245.5,
                    unit="ms",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    tier="good",
                    threshold_target=500.0,
                    threshold_critical=1000.0
                ),
                DashboardMetric(
                    name="requests_per_second",
                    category="throughput",
                    value=1234.5,
                    unit="rps",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    tier="excellent",
                    threshold_target=1000.0,
                    threshold_critical=500.0
                ),
                DashboardMetric(
                    name="error_rate",
                    category="error_rate",
                    value=0.5,
                    unit="percent",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    tier="good",
                    threshold_target=1.0,
                    threshold_critical=5.0
                )
            ]

        except Exception as e:
            self.logger.error(f"Failed to get current metrics: {e}")
            return []

    async def _send_slo_details(
        self,
        websocket: websockets.WebSocketServerProtocol,
        slo_id: str
    ) -> None:
        """Send detailed SLO information to client."""
        try:
            # TODO: Get detailed SLO information from metrics service
            details = {
                "slo_id": slo_id,
                "type": "slo_details",
                "data": {
                    "name": "Example SLO",
                    "description": "Example description",
                    "current_value": 95.5,
                    "target_value": 95.0,
                    "trend": "improving"
                }
            }

            await websocket.send(json.dumps(details))

        except Exception as e:
            self.logger.error(f"Failed to send SLO details: {e}")


# Global performance monitor instance
performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance."""
    global performance_monitor
    if performance_monitor is None:
        performance_monitor = PerformanceMonitor()
    return performance_monitor