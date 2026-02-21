# PowerTrader AI

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Status: Active](https://img.shields.io/badge/Status-Active-green.svg)]()

PowerTrader AI is a sophisticated cryptocurrency trading bot powered by artificial intelligence and machine learning algorithms. Originally designed as a personal trading system, it has evolved into a comprehensive framework that combines automated trading strategies, real-time market analysis, and enterprise-grade infrastructure.

## Complete Documentation

**[Full Documentation](docs/README.md)** - Comprehensive guides and tutorials

### Quick Navigation
- **[Getting Started](docs/getting-started/README.md)** - Installation and setup
- **[User Guide](docs/user-guide/README.md)** - How to use the application
- **[Exchange Setup](docs/exchanges/README.md)** - KuCoin and Robinhood configuration
- **[Security Guide](docs/security/README.md)** - Security best practices
- **[API Configuration](docs/api-configuration/README.md)** - Detailed API setup
- **[Troubleshooting](docs/troubleshooting/README.md)** - Common issues and solutions

### Technical Documentation
- **[Cost Analysis](docs/technical/COST_ANALYSIS.md)** - Comprehensive cost analysis framework
- **[Risk Management](docs/technical/RISK_MANAGEMENT_FRAMEWORK.md)** - Risk management system documentation

### Development Resources
- **[PR Validation](docs/development/PR_VALIDATION.md)** - Pull request validation system
- **[Implementation Guide](docs/development/IMPLEMENTATION_COMPLETE.md)** - Complete implementation documentation
- **[Release Strategy](docs/development/RELEASE_STRATEGY.md)** - Release planning and deployment

## System Architecture

PowerTrader AI has undergone extensive refactoring and enhancement through multiple development phases:

- **Phase 1**: Code Quality Foundations (Type hints, imports, error handling)
- **Phase 2**: Architecture Refactoring (Configuration classes, enhanced APIs)
- **Phase 3**: Advanced Infrastructure (Performance monitoring, logging, configuration)
- **Phase 4**: Integration & Testing (Testing framework, system orchestration)

## Important Disclaimer

**READ THIS BEFORE USING POWERTRADER AI**

- **Real Money Risk**: This software places real trades automatically with your money
- **Your Responsibility**: You are responsible for all financial and security risks
- **No Financial Advice**: This is not investment advice - do your own research
- **Security**: Keep your API keys private and secure
- **Open Source**: Code is completely open source and can be verified as non-malicious
- **Free Forever**: PowerTrader AI is completely free - never pay for this software

**You are fully responsible for:**
- Understanding how this trading system works
- All gains and losses from automated trades
- Securing your accounts and API keys
- Compliance with local regulations

For detailed security practices, see the **[Security Guide](docs/security/README.md)**.

## Quick Start

### For New Users
1. **[Install PowerTrader AI](docs/getting-started/installation.md)** - Complete installation guide
2. **[Set up Exchange Accounts](docs/exchanges/README.md)** - KuCoin & Robinhood setup
3. **[Configure API Keys](docs/api-configuration/README.md)** - Secure API configuration
4. **[Start Trading](docs/user-guide/README.md)** - Learn to use the application

### Basic Installation
```bash
# 1. Install Python 3.8+ from python.org
# 2. Clone or download PowerTrader AI
git clone https://github.com/sjackson0109/PowerTraderAI.git
cd PowerTraderAI

# 3. Install dependencies
pip install -r app/requirements.txt

# 4. Launch the application
python app/pt_desktop_app.py
```

**Important**: Follow the complete [Installation Guide](docs/getting-started/installation.md) for detailed setup instructions.

## How PowerTrader AI Works

### AI Trading Strategy

PowerTrader AI uses a unique approach to cryptocurrency trading:

- **Multi-timeframe Analysis**: Analyzes patterns across 1h to 1w timeframes
- **Instance-based Prediction**: Uses k-Nearest Neighbors (kNN) pattern matching
- **Online Learning**: Continuously adjusts based on prediction accuracy
- **DCA Strategy**: Structured Dollar Cost Averaging with intelligent entry points

### The AI Engine Explained

> *"It's an instance-based (kNN/kernel-style) predictor with online per-instance reliability weighting, used as a multi-timeframe trading signal."* - ChatGPT

**Simple Explanation**:
1. **Pattern Learning**: Analyzes historical price patterns across multiple timeframes
2. **Memory Storage**: Saves each pattern with what happened next
3. **Prediction**: Matches current patterns to historical data using weighted averages
4. **Adaptation**: Adjusts pattern weights based on accuracy over time

**Trading Logic**:
- **Entry Signal**: Buy when price drops below 3+ AI predicted lows (across timeframes)
- **DCA Triggers**: Additional purchases based on AI levels or hardcoded drawdowns
- **Exit Strategy**: Trailing profit margin (5% no DCA, 2.5% with DCA)
- **Risk Management**: Max 2 DCAs per 24-hour rolling window

For detailed strategy explanation, see the **[User Guide](docs/user-guide/README.md)**.

### Design Philosophy

#### Why This Strategy?
- **No Stop Loss**: Focus on long-term holding of quality cryptocurrencies
- **DCA Focus**: Structured buying during downtrends
- **Spot Trading Only**: No futures/margin complexity
- **Patience-Based**: Designed for gradual accumulation, not quick profits

This approach differs from common trading tactics that can be counterproductive for spot trading and long-term growth.

## Key Features

### Intelligent Trading
- **Neural Network Predictions**: Advanced ML models for price forecasting
- **Multi-timeframe Analysis**: 5m, 15m, 1h, 4h trading strategies
- **DCA Strategy**: Structured Dollar Cost Averaging system
- **Real-time Processing**: Live market data integration

### Performance Monitoring
- **Real-time Metrics**: CPU, memory, network monitoring
- **Operation Profiling**: Detailed timing analysis of trading operations
- **Statistical Analysis**: Performance trends and optimization insights
- **Export Capabilities**: JSON reports for analysis

### Configuration Management
- **Environment Support**: Separate configs for dev/staging/production
- **Hot-reloading**: Dynamic configuration updates without restarts
- **YAML Configuration**: Human-readable settings with validation
- **Type Safety**: Structured configuration with full validation

### Enterprise Logging
- **Structured JSON Logs**: Machine-readable logs with metadata
- **Specialized Streams**: Separate logs for trades, audit, performance
- **Async Processing**: Non-blocking log I/O for high performance
- **Compliance Ready**: Audit trails for regulatory requirements

### Security & Error Handling
- **Comprehensive Error Types**: Specialized exceptions for different scenarios
- **Security Modules**: Encrypted credential management
- **Input Validation**: Robust parameter validation
- **Recovery Mechanisms**: Automatic error recovery and retries

### Testing Framework
- **Strategy Testing**: Backtesting with historical data
- **Stress Testing**: High-load simulation with error injection
- **Component Testing**: Unit tests for all system components
- **Mock APIs**: Realistic trading simulation for development

### PR Validation
PowerTrader AI includes a comprehensive PR validation system for ensuring code quality before merging:

```bash
# Run PR validation tests
python .github/scripts/test_pr_validation.py
```

**Validation Categories:**
- **File Structure**: Ensures all essential files are present
- **Module Imports**: Verifies core modules import successfully
- **Risk Management**: Tests risk calculation and position sizing
- **Cost Analysis**: Validates cost calculation systems
- **Input Validation**: Tests parameter validation functions
- **Configuration**: Checks configuration system functionality

**Usage in Development:**
- Run before creating pull requests
- Integrates with existing `pt_testing.py` framework
- Provides clear pass/fail recommendations
- Windows compatible (no Unicode dependencies)

### Market Integration
- **KuCoin API**: Real-time market data and charts
- **Robinhood API**: Automated trade execution
- **Multi-Exchange Support**: Extensible architecture for additional exchanges
- **WebSocket Streams**: Low-latency real-time data feeds

For detailed feature documentation, see the **[User Guide](docs/user-guide/README.md)**.

## Technical Requirements

### System Requirements
- **Operating System**: Windows 10/11, macOS, or Linux
- **Python**: 3.8 or higher (3.10+ recommended)
- **Memory**: 4GB RAM minimum, 8GB+ recommended
- **Storage**: 2GB free space
- **Network**: Stable internet connection

### External Services
- **KuCoin Account**: For real-time market data (free)
- **Robinhood Account**: For automated trading execution
- **API Keys**: Required for both services

For complete setup instructions, see the **[Installation Guide](docs/getting-started/installation.md)**.

## Critical Safety Information

### Before You Start
1. **Read All Documentation**: Understand how the system works
2. **Start Small**: Use minimal funds while learning
3. **Test Thoroughly**: Use paper trading features first
4. **Secure Setup**: Follow all security guidelines
5. **Monitor Actively**: Watch your first trades closely

### Risk Management
- Maximum 2 DCA purchases per 24-hour window
- Configurable position size limits
- Emergency stop functionality
- Comprehensive logging and audit trails

### Emergency Procedures
- **Emergency Stop**: Red button in GUI or Ctrl+Alt+S
- **Manual Override**: Disable AI trading in settings
- **Account Recovery**: See [Troubleshooting Guide](docs/troubleshooting/README.md)

**Remember**: This system trades with real money. Always understand what it's doing before letting it run automatically.

## Support & Resources

### Documentation
- **[Complete Documentation](docs/README.md)** - Full guides and references
- **[Quick Start](docs/getting-started/README.md)** - Get up and running fast
- **[Troubleshooting](docs/troubleshooting/README.md)** - Solve common issues

### Community & Support
- **[GitHub Issues](https://github.com/sjackson0109/PowerTraderAI/issues)** - Bug reports and feature requests
- **[Discussions](https://github.com/sjackson0109/PowerTraderAI/discussions)** - Community Q&A
- **[Security Reporting](docs/security/README.md)** - Report security issues

### Important Notes
- PowerTrader AI is **completely free forever**
- No paid features or subscriptions
- Be wary of scams asking for payment
- All code is open source and verifiable

## Contributing

PowerTrader AI is open source and welcomes contributions:
- **Bug Reports**: Use GitHub issues
- **Feature Requests**: Submit enhancement proposals
- **Code Contributions**: Fork, develop, and submit pull requests
- **Documentation**: Help improve guides and tutorials

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## Legacy Setup Instructions

*Note: For complete, up-to-date setup instructions, see the **[Getting Started Guide](docs/getting-started/README.md)**.*

The following are the original setup instructions (kept for reference):

### Basic Setup Steps

1. **Install Python**: Download from python.org, check "Add Python to PATH"
2. **Download PowerTrader AI**: Clone from GitHub or download files
3. **Install Dependencies**: `pip install -r requirements.txt`
4. **Launch Application**: `python app/pt_desktop_app.py`

### Configuration in PowerTrader Hub

1. **Set Main Folder**: Point to your PowerTrader AI directory
2. **Choose Coins**: Start with BTC for initial testing
3. **Configure Robinhood**: Use the built-in API setup wizard
4. **Train Models**: Click "Train All" and wait for completion
5. **Start Trading**: Click "Start All" to begin automated trading

### Neural Levels (LONG/SHORT Numbers)

- **Neural Levels**: Signal strength from low to high (predicted price ranges)
- **LONG Signals**: Buy-direction signals (higher = stronger)
- **SHORT Signals**: No-start signals
- **Trade Trigger**: Trades start when reaching LONG level 3+ with SHORT level 0

For detailed configuration instructions, see the **[API Configuration Guide](docs/api-configuration/README.md)**.

## Support the Project

PowerTrader AI is **completely free and open source**! If you find it valuable, consider supporting continued development:

- **Cash App**: $garagesteve
- **PayPal**: @garagesteve
- **Facebook**: [Subscribe for $1/month](https://www.facebook.com/stephen.bryant.hughes)

## License

PowerTrader AI is released under the **Apache 2.0 License** - see [LICENSE](LICENSE) file for details.

---

**FINAL REMINDER**: This software trades with real money automatically. You are fully responsible for all trades, gains, losses, and security of your accounts. Always understand the system before using it with real funds.

For comprehensive guides, troubleshooting, and best practices, visit the **[Complete Documentation](docs/README.md)**.#   T e s t   p r e - c o m m i t   h o o k s 
 
 
#   C l e a n   e n d   o f   f i l e  
 
