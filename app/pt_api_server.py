"""
PowerTrader AI+ - Public API Server
Provides REST endpoints for external access to trading data and system status.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request
from werkzeug.serving import make_server
from flask_cors import CORS
from pt_logging import get_logger

logger = get_logger(__name__)


class PowerTraderAPIServer:
    """Public API server for PowerTrader data access."""

    def __init__(self, hub_data_dir: str, port: int = 8080, host: str = "127.0.0.1"):
        self.hub_data_dir = hub_data_dir
        self.port = port
        self.host = host
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for web access

        # Rate limiting state
        self._rate_limits = {}
        self._rate_limit_window = 60  # 1 minute window
        self._max_requests_per_minute = 100

        # Server state
        self._server_thread = None
        self._httpd = None
        self._is_running = False

        self._setup_routes()

    def _setup_routes(self):
        """Set up all API routes."""

        @self.app.before_request
        def rate_limit():
            """Simple rate limiting."""
            client_ip = request.remote_addr
            now = time.time()

            # Clean old entries
            cutoff = now - self._rate_limit_window
            self._rate_limits = {
                ip: timestamps
                for ip, timestamps in self._rate_limits.items()
                if any(ts > cutoff for ts in timestamps)
            }

            # Check current client
            if client_ip not in self._rate_limits:
                self._rate_limits[client_ip] = []

            # Remove old timestamps for this client
            self._rate_limits[client_ip] = [
                ts for ts in self._rate_limits[client_ip] if ts > cutoff
            ]

            # Check rate limit
            if len(self._rate_limits[client_ip]) >= self._max_requests_per_minute:
                return (
                    jsonify(
                        {
                            "error": "Rate limit exceeded",
                            "message": f"Maximum {self._max_requests_per_minute} requests per minute",
                        }
                    ),
                    429,
                )

            # Record this request
            self._rate_limits[client_ip].append(now)

        @self.app.route("/")
        def index():
            """API information endpoint."""
            return jsonify(
                {
                    "name": "PowerTrader AI+ Public API",
                    "version": "1.0",
                    "status": "operational",
                    "endpoints": {
                        "/status": "Current system and trading status",
                        "/positions": "Active trading positions",
                        "/history": "Trade history",
                        "/performance": "Performance metrics",
                        "/account": "Account value and portfolio",
                        "/health": "System health check",
                    },
                    "documentation": "See README.md for full API documentation",
                    "rate_limits": {
                        "requests_per_minute": self._max_requests_per_minute,
                        "window_seconds": self._rate_limit_window,
                    },
                }
            )

        @self.app.route("/api/health")
        def health():
            """Health check endpoint."""
            try:
                # Check if hub data directory is accessible
                hub_accessible = os.path.exists(self.hub_data_dir)

                # Check for recent trader status update (within last 5 minutes)
                status_path = os.path.join(self.hub_data_dir, "trader_status.json")
                status_fresh = False
                if os.path.exists(status_path):
                    mtime = os.path.getmtime(status_path)
                    status_fresh = (time.time() - mtime) < 300

                return jsonify(
                    {
                        "status": (
                            "healthy" if hub_accessible and status_fresh else "degraded"
                        ),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "checks": {
                            "hub_data_directory": "ok" if hub_accessible else "error",
                            "trader_status_fresh": "ok" if status_fresh else "stale",
                        },
                    }
                )
            except Exception as e:
                return jsonify({"status": "error", "error": str(e)}), 500

        @self.app.route("/api/status")
        def get_status():
            """Get current trading status."""
            try:
                status_path = os.path.join(self.hub_data_dir, "trader_status.json")
                if not os.path.exists(status_path):
                    return (
                        jsonify(
                            {
                                "error": "Status data not available",
                                "message": "Trader may not be running",
                            }
                        ),
                        404,
                    )

                with open(status_path, "r") as f:
                    data = json.load(f)

                # Sanitize sensitive data
                sanitized = {
                    "timestamp": data.get("timestamp"),
                    "active_positions": len(data.get("positions", [])),
                    "total_value": data.get("account_value_usd"),
                    "trading_enabled": data.get("trading_enabled", False),
                    "last_update": data.get("last_update"),
                    "system_status": data.get("status", "unknown"),
                }

                return jsonify(sanitized)
            except Exception as e:
                logger.error(f"Error reading status: {e}")
                return jsonify({"error": "Failed to read status"}), 500

        @self.app.route("/api/positions")
        def get_positions():
            """Get current trading positions."""
            try:
                status_path = os.path.join(self.hub_data_dir, "trader_status.json")
                if not os.path.exists(status_path):
                    return jsonify([])

                with open(status_path, "r") as f:
                    data = json.load(f)

                positions = []
                for pos in data.get("positions", []):
                    positions.append(
                        {
                            "symbol": pos.get("symbol"),
                            "quantity": pos.get("quantity"),
                            "market_value_usd": pos.get("market_value_usd"),
                            "average_cost": pos.get("average_cost"),
                            "pnl_percent": pos.get("gain_loss_pct"),
                            "side": (
                                "long" if float(pos.get("quantity", 0)) > 0 else "short"
                            ),
                        }
                    )

                return jsonify(positions)
            except Exception as e:
                logger.error(f"Error reading positions: {e}")
                return jsonify({"error": "Failed to read positions"}), 500

        @self.app.route("/api/history")
        def get_trade_history():
            """Get trade history with optional filters."""
            try:
                limit = min(int(request.args.get("limit", 100)), 1000)  # Cap at 1000
                symbol = request.args.get("symbol", "").upper()
                hours = request.args.get("hours")  # Time filter in hours

                history_path = os.path.join(self.hub_data_dir, "trade_history.jsonl")
                if not os.path.exists(history_path):
                    return jsonify([])

                trades = []
                cutoff_time = None
                if hours:
                    cutoff_time = time.time() - (float(hours) * 3600)

                with open(history_path, "r") as f:
                    lines = f.readlines()

                # Process in reverse order (newest first)
                for line in reversed(
                    lines[-limit * 2 :]
                ):  # Read more than limit to allow filtering
                    if len(trades) >= limit:
                        break

                    try:
                        trade = json.loads(line.strip())

                        # Apply filters
                        if symbol and not trade.get("symbol", "").startswith(symbol):
                            continue

                        if cutoff_time and trade.get("timestamp", 0) < cutoff_time:
                            continue

                        # Sanitize trade data
                        sanitized_trade = {
                            "timestamp": trade.get("timestamp"),
                            "symbol": trade.get("symbol"),
                            "side": trade.get("side"),
                            "quantity": trade.get("quantity"),
                            "price": trade.get("price"),
                            "value_usd": trade.get("value_usd"),
                            "tag": trade.get("tag"),
                            "datetime": datetime.fromtimestamp(
                                trade.get("timestamp", 0)
                            ).isoformat(),
                        }
                        trades.append(sanitized_trade)

                    except json.JSONDecodeError:
                        continue

                return jsonify(trades)
            except Exception as e:
                logger.error(f"Error reading trade history: {e}")
                return jsonify({"error": "Failed to read trade history"}), 500

        @self.app.route("/api/performance")
        def get_performance():
            """Get performance metrics."""
            try:
                # Read account value history
                value_history_path = os.path.join(
                    self.hub_data_dir, "account_value_history.jsonl"
                )
                pnl_path = os.path.join(self.hub_data_dir, "pnl_ledger.json")

                metrics = {"error": "Performance data not available"}

                if os.path.exists(pnl_path):
                    with open(pnl_path, "r") as f:
                        pnl_data = json.load(f)

                    metrics = {
                        "total_return_pct": pnl_data.get("total_return_pct"),
                        "total_pnl_usd": pnl_data.get("total_pnl_usd"),
                        "win_rate": pnl_data.get("win_rate"),
                        "total_trades": pnl_data.get("total_trades"),
                        "avg_trade_duration_hours": pnl_data.get(
                            "avg_trade_duration_hours"
                        ),
                        "last_updated": pnl_data.get("timestamp"),
                    }

                # Add recent performance if value history exists
                if os.path.exists(value_history_path):
                    try:
                        recent_values = []
                        with open(value_history_path, "r") as f:
                            lines = f.readlines()

                        # Get last 24 hours of data
                        cutoff = time.time() - 86400
                        for line in reversed(lines[-500:]):  # Check last 500 entries
                            try:
                                entry = json.loads(line.strip())
                                if entry.get("timestamp", 0) > cutoff:
                                    recent_values.append(entry)
                            except json.JSONDecodeError:
                                continue

                        if len(recent_values) >= 2:
                            recent_values.sort(key=lambda x: x.get("timestamp", 0))
                            start_value = recent_values[0].get("total_value", 0)
                            end_value = recent_values[-1].get("total_value", 0)

                            if start_value > 0:
                                daily_return_pct = (
                                    (end_value - start_value) / start_value
                                ) * 100
                                metrics["daily_return_pct"] = round(daily_return_pct, 4)
                    except Exception:
                        pass

                return jsonify(metrics)
            except Exception as e:
                logger.error(f"Error reading performance: {e}")
                return jsonify({"error": "Failed to read performance data"}), 500

        @self.app.route("/api/account")
        def get_account():
            """Get account value and portfolio summary."""
            try:
                status_path = os.path.join(self.hub_data_dir, "trader_status.json")
                if not os.path.exists(status_path):
                    return jsonify({"error": "Account data not available"}), 404

                with open(status_path, "r") as f:
                    data = json.load(f)

                account_info = {
                    "total_value_usd": data.get("account_value_usd"),
                    "cash_balance": data.get("cash_balance"),
                    "positions_count": len(data.get("positions", [])),
                    "last_updated": data.get("timestamp"),
                    "portfolio_summary": {},
                }

                # Calculate portfolio breakdown
                total_value = float(data.get("account_value_usd", 0))
                if total_value > 0:
                    for pos in data.get("positions", []):
                        symbol = pos.get("symbol", "UNKNOWN")
                        position_value = float(pos.get("market_value_usd", 0))
                        weight_pct = (position_value / total_value) * 100

                        account_info["portfolio_summary"][symbol] = {
                            "value_usd": position_value,
                            "weight_percent": round(weight_pct, 2),
                        }

                return jsonify(account_info)
            except Exception as e:
                logger.error(f"Error reading account data: {e}")
                return jsonify({"error": "Failed to read account data"}), 500

    def start_server(self):
        """Start the API server in a background thread."""
        if self._is_running:
            logger.warning("API server is already running")
            return

        def run_server():
            try:
                logger.info(
                    f"Starting PowerTrader API server on {self.host}:{self.port}"
                )
                self._httpd = make_server(self.host, self.port, self.app, threaded=True)
                self._is_running = True
                self._httpd.serve_forever()
            except Exception as e:
                logger.error(f"API server error: {e}")
            finally:
                self._is_running = False
                if self._httpd is not None:
                    try:
                        self._httpd.server_close()
                    except Exception:
                        pass
                self._httpd = None

        self._server_thread = threading.Thread(target=run_server, daemon=True)
        self._server_thread.start()
        logger.info(
            f"PowerTrader API server starting at http://{self.host}:{self.port}"
        )

    def stop_server(self):
        """Stop the API server, releasing the bound socket."""
        if not self._is_running:
            return
        try:
            if self._httpd is not None:
                self._httpd.shutdown()
        except Exception as e:
            logger.warning(f"API server shutdown error: {e}")
        self._is_running = False
        logger.info("API server stopped")

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._is_running


# Convenience function for easy integration
def create_api_server(
    hub_data_dir: str, port: int = 8080, host: str = "127.0.0.1"
) -> PowerTraderAPIServer:
    """Create and return a new API server instance."""
    return PowerTraderAPIServer(hub_data_dir, port, host)


if __name__ == "__main__":
    # Direct execution for testing
    import sys

    hub_dir = sys.argv[1] if len(sys.argv) > 1 else "hub_data"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080

    server = create_api_server(hub_dir, port)
    server.start_server()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down API server...")
        server.stop_server()
